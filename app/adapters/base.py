from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from app.utils.errors import WpsStartupError


@dataclass(frozen=True)
class ConversionDetails:
    process_pid: int | None


@dataclass(frozen=True)
class WpsSession:
    qt_app: Any
    rpc: Any
    app: Any
    process_pid: int | None


class BaseWpsAdapter(ABC):
    @abstractmethod
    def start_session(self) -> WpsSession:
        raise NotImplementedError

    @abstractmethod
    def convert_with_session(
        self,
        session: WpsSession,
        input_path: Path,
        output_path: Path,
    ) -> ConversionDetails:
        raise NotImplementedError

    @abstractmethod
    def stop_session(self, session: WpsSession) -> None:
        raise NotImplementedError

    def _start_session(
        self,
        qt_app_factory: Callable[[list[str]], Any],
        success_code: int,
        create_rpc_instance: Callable[[], tuple[int, Any]],
        get_application: Callable[[Any], tuple[int, Any]],
        create_rpc_instance_name: str,
        get_application_name: str,
    ) -> WpsSession:
        qt_app = qt_app_factory([])
        hr, rpc = create_rpc_instance()
        if hr != success_code:
            raise WpsStartupError(
                f"{create_rpc_instance_name} failed: {self._format_hresult(hr)}"
            )

        process_pid = self._get_process_pid(rpc, success_code)

        hr, app = get_application(rpc)
        if hr != success_code:
            raise WpsStartupError(
                f"{get_application_name} failed: {self._format_hresult(hr)}"
            )

        self._hide_application(app)
        return WpsSession(
            qt_app=qt_app,
            rpc=rpc,
            app=app,
            process_pid=process_pid,
        )

    def _get_process_pid(self, rpc: Any, success_code: int) -> int | None:
        try:
            hr, pid = rpc.getProcessPid()
        except Exception:
            return None
        if hr != success_code:
            return None
        try:
            return int(pid)
        except (TypeError, ValueError):
            return None

    def _format_hresult(self, value: int) -> str:
        return hex(value & 0xFFFFFFFF)

    def _hide_application(self, app: Any) -> None:
        try:
            app.Visible = False
        except Exception:
            pass

    def _close_safely(self, close_action: Callable[[], Any]) -> None:
        try:
            close_action()
        except Exception:
            pass
