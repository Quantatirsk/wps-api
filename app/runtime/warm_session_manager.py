from __future__ import annotations

import asyncio
from dataclasses import dataclass
from itertools import count
import multiprocessing
from multiprocessing.connection import Connection
from pathlib import Path
import time
from typing import Any

from app.adapters.base import BaseWpsAdapter
from app.adapters.presentation_adapter import PresentationAdapter
from app.adapters.spreadsheet_adapter import SpreadsheetAdapter
from app.adapters.writer_adapter import WriterAdapter
from app.config import Settings
from app.utils.errors import (
    AppError,
    ConversionTimeoutError,
    WpsConversionError,
    WpsOpenDocumentError,
    WpsStartupError,
)
from app.utils.logging import get_logger


FAMILY_WRITER = "writer"
FAMILY_PRESENTATION = "presentation"
FAMILY_SPREADSHEET = "spreadsheet"

ERROR_TYPES: dict[str, type[AppError]] = {
    "WpsStartupError": WpsStartupError,
    "WpsOpenDocumentError": WpsOpenDocumentError,
    "WpsConversionError": WpsConversionError,
    "ConversionTimeoutError": ConversionTimeoutError,
}
PREWARM_FAMILY_ORDER = (
    FAMILY_WRITER,
    FAMILY_SPREADSHEET,
    FAMILY_PRESENTATION,
)

_MANAGER: WarmSessionManager | None = None


@dataclass(frozen=True)
class WarmConversionResult:
    process_pid: int | None
    warm_hit: bool


class FamilyWorker:
    def __init__(
        self,
        family: str,
        worker_index: int,
        settings: Settings,
        startup_lock: Any,
    ) -> None:
        self.family = family
        self.settings = settings
        self._startup_lock = startup_lock
        self.worker_name = f"{family}-{worker_index}"
        self.logger = get_logger(f"{__name__}.{self.worker_name}")
        self._ctx = multiprocessing.get_context("spawn")
        self._lock = asyncio.Lock()
        self._parent_conn: Connection | None = None
        self._process: multiprocessing.Process | None = None
        self._last_used_monotonic: float | None = None

    async def convert(
        self,
        input_path: Path,
        output_path: Path,
        timeout_seconds: int,
    ) -> WarmConversionResult:
        async with self._lock:
            self._recycle_if_idle()
            self._ensure_process()
            started_at = time.perf_counter()
            try:
                response = await asyncio.to_thread(
                    self._send_convert_request,
                    input_path,
                    output_path,
                    timeout_seconds,
                )
            except AppError:
                self.logger.exception(
                    "warm_convert_failed family=%s input=%s output=%s",
                    self.family,
                    input_path,
                    output_path,
                )
                self._shutdown_process(force=True)
                raise
            except Exception as exc:
                self.logger.exception(
                    "warm_convert_failed family=%s input=%s output=%s",
                    self.family,
                    input_path,
                    output_path,
                )
                self._shutdown_process(force=True)
                raise WpsConversionError(
                    f"{self.family} warm session failed: {exc}"
                ) from exc

            self._last_used_monotonic = time.monotonic()
            duration_ms = int((time.perf_counter() - started_at) * 1000)
            self.logger.info(
                "warm_convert_succeeded family=%s warm_hit=%s duration_ms=%s process_pid=%s",
                self.family,
                response["warmHit"],
                duration_ms,
                response["processPid"],
            )
            return WarmConversionResult(
                process_pid=response["processPid"],
                warm_hit=response["warmHit"],
            )

    async def prewarm(self, timeout_seconds: int) -> None:
        async with self._lock:
            self._recycle_if_idle()
            self._ensure_process()
            started_at = time.perf_counter()
            try:
                await asyncio.to_thread(self._send_prewarm_request, timeout_seconds)
            except AppError:
                self.logger.exception("warm_prewarm_failed family=%s", self.family)
                self._shutdown_process(force=True)
                raise
            except Exception as exc:
                self.logger.exception("warm_prewarm_failed family=%s", self.family)
                self._shutdown_process(force=True)
                raise WpsStartupError(
                    f"{self.family} warm prewarm failed: {exc}"
                ) from exc

            self._last_used_monotonic = time.monotonic()
            duration_ms = int((time.perf_counter() - started_at) * 1000)
            self.logger.info(
                "warm_prewarm_succeeded family=%s duration_ms=%s",
                self.family,
                duration_ms,
            )

    def close(self) -> None:
        self._shutdown_process(force=False)

    def _ensure_process(self) -> None:
        if (
            self._process is not None
            and self._process.is_alive()
            and self._parent_conn is not None
        ):
            return

        self._shutdown_process(force=True)
        parent_conn, child_conn = self._ctx.Pipe()
        process = self._ctx.Process(
            target=run_warm_session_worker,
            args=(
                self.family,
                self.worker_name,
                child_conn,
                self.settings.warm_session_max_jobs,
                self._startup_lock,
            ),
            daemon=True,
        )
        process.start()
        child_conn.close()
        self._parent_conn = parent_conn
        self._process = process
        self.logger.info(
            "warm_worker_started family=%s worker_name=%s worker_pid=%s",
            self.family,
            self.worker_name,
            process.pid,
        )

    def _send_convert_request(
        self,
        input_path: Path,
        output_path: Path,
        timeout_seconds: int,
    ) -> dict[str, Any]:
        response = self._send_request(
            {
                "type": "convert",
                "inputPath": str(input_path),
                "outputPath": str(output_path),
            },
            timeout_seconds,
        )
        if not response.get("ok", False):
            error_type = str(response.get("errorType", "WpsConversionError"))
            message = str(response.get("message", "warm worker conversion failed"))
            raise self._build_error(error_type, message)

        return response

    def _send_prewarm_request(self, timeout_seconds: int) -> None:
        response = self._send_request({"type": "prewarm"}, timeout_seconds)
        if not response.get("ok", False):
            error_type = str(response.get("errorType", "WpsStartupError"))
            message = str(response.get("message", "warm worker prewarm failed"))
            raise self._build_error(error_type, message)

    def _send_request(
        self,
        payload: dict[str, str],
        timeout_seconds: int,
    ) -> dict[str, Any]:
        conn = self._require_connection()
        process = self._require_process()
        if not process.is_alive():
            raise WpsStartupError(f"{self.family} warm worker is not running")

        try:
            conn.send(payload)
        except (BrokenPipeError, EOFError, OSError) as exc:
            raise WpsStartupError(
                f"{self.family} warm worker request channel is unavailable"
            ) from exc

        if not conn.poll(timeout_seconds):
            raise ConversionTimeoutError(
                f"{self.family} request timed out after {timeout_seconds} seconds"
            )

        try:
            response = conn.recv()
        except EOFError as exc:
            raise WpsStartupError(
                f"{self.family} warm worker exited before replying"
            ) from exc

        if not isinstance(response, dict):
            raise WpsConversionError(
                f"{self.family} warm worker returned an invalid response"
            )

        return response

    def _build_error(self, error_type: str, message: str) -> AppError:
        error_cls = ERROR_TYPES.get(error_type, WpsConversionError)
        return error_cls(message)

    def _recycle_if_idle(self) -> None:
        if self._last_used_monotonic is None:
            return
        idle_seconds = time.monotonic() - self._last_used_monotonic
        if idle_seconds <= self.settings.warm_session_idle_ttl_seconds:
            return
        self.logger.info(
            "warm_worker_recycled_idle family=%s idle_seconds=%.2f",
            self.family,
            idle_seconds,
        )
        self._shutdown_process(force=False)

    def _shutdown_process(self, force: bool) -> None:
        conn = self._parent_conn
        process = self._process
        self._parent_conn = None
        self._process = None
        self._last_used_monotonic = None

        if conn is not None:
            if not force:
                try:
                    conn.send({"type": "shutdown"})
                except (BrokenPipeError, EOFError, OSError):
                    pass
            conn.close()

        if process is None:
            return

        process.join(timeout=1 if not force else 0.2)
        if process.is_alive():
            process.terminate()
            process.join(timeout=2)
        if process.is_alive():
            process.kill()
            process.join(timeout=2)

    def _require_connection(self) -> Connection:
        if self._parent_conn is None:
            raise WpsStartupError(f"{self.family} warm worker connection is missing")
        return self._parent_conn

    def _require_process(self) -> multiprocessing.Process:
        if self._process is None:
            raise WpsStartupError(f"{self.family} warm worker process is missing")
        return self._process


class FamilyWorkerPool:
    def __init__(
        self,
        family: str,
        worker_count: int,
        settings: Settings,
        startup_lock: Any,
    ) -> None:
        self.family = family
        self.logger = get_logger(f"{__name__}.{family}.pool")
        self._workers = [
            FamilyWorker(family, worker_index, settings, startup_lock)
            for worker_index in range(1, worker_count + 1)
        ]
        self._cursor = count()

    async def convert(
        self,
        input_path: Path,
        output_path: Path,
        timeout_seconds: int,
    ) -> WarmConversionResult:
        worker = self._workers[next(self._cursor) % len(self._workers)]
        self.logger.info(
            "warm_pool_dispatch family=%s worker_name=%s input=%s",
            self.family,
            worker.worker_name,
            input_path.name,
        )
        return await worker.convert(input_path, output_path, timeout_seconds)

    async def prewarm_all(self, timeout_seconds: int) -> None:
        for worker in self._workers:
            await worker.prewarm(timeout_seconds)

    def close(self) -> None:
        for worker in self._workers:
            worker.close()


class WarmSessionManager:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        ctx = multiprocessing.get_context("spawn")
        startup_lock = ctx.Lock()
        self._pools = {
            FAMILY_WRITER: FamilyWorkerPool(
                FAMILY_WRITER,
                settings.writer_worker_count,
                settings,
                startup_lock,
            ),
            FAMILY_PRESENTATION: FamilyWorkerPool(
                FAMILY_PRESENTATION,
                1,
                settings,
                startup_lock,
            ),
            FAMILY_SPREADSHEET: FamilyWorkerPool(
                FAMILY_SPREADSHEET,
                1,
                settings,
                startup_lock,
            ),
        }

    async def convert(
        self,
        family: str,
        input_path: Path,
        output_path: Path,
        timeout_seconds: int,
    ) -> WarmConversionResult:
        pool = self._pools.get(family)
        if pool is None:
            raise WpsConversionError(f"unsupported warm session family: {family}")
        return await pool.convert(input_path, output_path, timeout_seconds)

    async def prewarm_all(self, timeout_seconds: int) -> None:
        for family in PREWARM_FAMILY_ORDER:
            await self._pools[family].prewarm_all(timeout_seconds)

    def close(self) -> None:
        for pool in self._pools.values():
            pool.close()


def get_warm_session_manager(settings: Settings) -> WarmSessionManager:
    global _MANAGER
    if _MANAGER is None:
        _MANAGER = WarmSessionManager(settings)
    return _MANAGER


def close_warm_session_manager() -> None:
    global _MANAGER
    if _MANAGER is None:
        return
    _MANAGER.close()
    _MANAGER = None


def run_warm_session_worker(
    family: str,
    worker_name: str,
    connection: Connection,
    max_jobs_per_session: int,
    startup_lock: Any,
) -> None:
    logger = get_logger(f"{__name__}.worker.{worker_name}")
    adapter = _build_adapter(family)
    session = None
    jobs_completed = 0
    logger.info("warm_worker_booted family=%s worker_name=%s", family, worker_name)
    try:
        while True:
            try:
                command = connection.recv()
            except EOFError:
                break

            command_type = command.get("type")
            if command_type == "shutdown":
                break
            if command_type == "prewarm":
                session, jobs_completed = _handle_prewarm_command(
                    adapter=adapter,
                    connection=connection,
                    startup_lock=startup_lock,
                    logger=logger,
                    family=family,
                    worker_name=worker_name,
                    session=session,
                    jobs_completed=jobs_completed,
                )
                continue
            if command_type != "convert":
                _send_worker_error_response(
                    connection=connection,
                    error_type="WpsConversionError",
                    message=f"unsupported command: {command_type}",
                )
                continue

            session, jobs_completed = _handle_convert_command(
                adapter=adapter,
                connection=connection,
                startup_lock=startup_lock,
                logger=logger,
                family=family,
                worker_name=worker_name,
                command=command,
                session=session,
                jobs_completed=jobs_completed,
                max_jobs_per_session=max_jobs_per_session,
            )
    finally:
        if session is not None:
            _stop_session_safely(adapter, session)
        connection.close()
        logger.info("warm_worker_stopped family=%s worker_name=%s", family, worker_name)


def _build_adapter(family: str) -> BaseWpsAdapter:
    if family == FAMILY_WRITER:
        return WriterAdapter()
    if family == FAMILY_PRESENTATION:
        return PresentationAdapter()
    if family == FAMILY_SPREADSHEET:
        return SpreadsheetAdapter()
    raise WpsConversionError(f"unsupported family: {family}")


def _stop_session_safely(adapter: BaseWpsAdapter, session: Any) -> None:
    try:
        adapter.stop_session(session)
    except Exception:
        pass


def _handle_prewarm_command(
    adapter: BaseWpsAdapter,
    connection: Connection,
    startup_lock: Any,
    logger: Any,
    family: str,
    worker_name: str,
    session: Any,
    jobs_completed: int,
) -> tuple[Any, int]:
    try:
        if session is None:
            session = _start_worker_session(
                adapter=adapter,
                startup_lock=startup_lock,
                logger=logger,
                family=family,
                worker_name=worker_name,
                phase="prewarm",
            )
            jobs_completed = 0
        else:
            logger.info(
                "warm_worker_prewarm_hit family=%s worker_name=%s",
                family,
                worker_name,
            )
        connection.send({"ok": True})
        return session, jobs_completed
    except AppError as exc:
        logger.exception("warm_worker_prewarm_failed family=%s", family)
        _send_worker_error_response(connection, exc.__class__.__name__, str(exc))
    except Exception as exc:
        logger.exception("warm_worker_prewarm_failed family=%s", family)
        _send_worker_error_response(connection, "WpsStartupError", str(exc))

    return _recycle_worker_session(adapter, session)


def _handle_convert_command(
    adapter: BaseWpsAdapter,
    connection: Connection,
    startup_lock: Any,
    logger: Any,
    family: str,
    worker_name: str,
    command: dict[str, str],
    session: Any,
    jobs_completed: int,
    max_jobs_per_session: int,
) -> tuple[Any, int]:
    input_path = Path(str(command["inputPath"]))
    output_path = Path(str(command["outputPath"]))
    warm_hit = session is not None

    try:
        if session is None:
            session = _start_worker_session(
                adapter=adapter,
                startup_lock=startup_lock,
                logger=logger,
                family=family,
                worker_name=worker_name,
                phase="cold_start",
                input_name=input_path.name,
            )
            jobs_completed = 0
            details = adapter.convert_with_session(session, input_path, output_path)
        else:
            details = adapter.convert_with_session(session, input_path, output_path)

        jobs_completed += 1
        connection.send(
            {
                "ok": True,
                "processPid": details.process_pid,
                "warmHit": warm_hit,
            }
        )
        if jobs_completed >= max_jobs_per_session:
            logger.info(
                "warm_worker_recycled_jobs family=%s worker_name=%s jobs_completed=%s",
                family,
                worker_name,
                jobs_completed,
            )
            return _recycle_worker_session(adapter, session)
        return session, jobs_completed
    except AppError as exc:
        logger.exception(
            "warm_worker_convert_failed family=%s warm_hit=%s input=%s",
            family,
            warm_hit,
            input_path,
        )
        _send_worker_error_response(connection, exc.__class__.__name__, str(exc))
    except Exception as exc:
        logger.exception(
            "warm_worker_convert_failed family=%s warm_hit=%s input=%s",
            family,
            warm_hit,
            input_path,
        )
        _send_worker_error_response(connection, "WpsConversionError", str(exc))

    return _recycle_worker_session(adapter, session)


def _recycle_worker_session(adapter: BaseWpsAdapter, session: Any) -> tuple[None, int]:
    if session is not None:
        _stop_session_safely(adapter, session)
    return None, 0


def _start_worker_session(
    adapter: BaseWpsAdapter,
    startup_lock: Any,
    logger: Any,
    family: str,
    worker_name: str,
    phase: str,
    input_name: str | None = None,
) -> Any:
    _log_worker_session_event(
        logger=logger,
        action=f"{phase}_wait",
        family=family,
        worker_name=worker_name,
        input_name=input_name,
    )
    with startup_lock:
        _log_worker_session_event(
            logger=logger,
            action=f"{phase}_begin",
            family=family,
            worker_name=worker_name,
            input_name=input_name,
        )
        session = adapter.start_session()
    _log_worker_session_event(
        logger=logger,
        action=f"{phase}_complete",
        family=family,
        worker_name=worker_name,
        input_name=input_name,
    )
    return session


def _log_worker_session_event(
    logger: Any,
    action: str,
    family: str,
    worker_name: str,
    input_name: str | None = None,
) -> None:
    event_name = f"warm_worker_{action}"
    if input_name is None:
        logger.info("%s family=%s worker_name=%s", event_name, family, worker_name)
        return
    logger.info(
        "%s family=%s worker_name=%s input=%s",
        event_name,
        family,
        worker_name,
        input_name,
    )


def _send_worker_error_response(
    connection: Connection,
    error_type: str,
    message: str,
) -> None:
    connection.send(
        {
            "ok": False,
            "errorType": error_type,
            "message": message,
        }
    )
