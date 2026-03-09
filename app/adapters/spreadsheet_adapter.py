from __future__ import annotations

from pathlib import Path
from time import sleep
from typing import Any

from app.adapters.base import BaseWpsAdapter, ConversionDetails, WpsSession
from app.utils.errors import (
    WpsConversionError,
    WpsOpenDocumentError,
    WpsStartupError,
)


class SpreadsheetAdapter(BaseWpsAdapter):
    def start_session(self) -> WpsSession:
        QtApp, S_OK, create_et_rpc_instance, _ = self._load_dependencies()
        return self._start_session(
            qt_app_factory=QtApp,
            success_code=S_OK,
            create_rpc_instance=create_et_rpc_instance,
            get_application=lambda rpc: rpc.getEtApplication(),
            create_rpc_instance_name="createEtRpcInstance",
            get_application_name="getEtApplication",
        )

    def convert_with_session(
        self,
        session: WpsSession,
        input_path: Path,
        output_path: Path,
    ) -> ConversionDetails:
        _, S_OK, _, etapi = self._load_dependencies()

        workbook = None
        try:
            workbooks = self._get_workbooks_with_retry(session.app)
            hr, workbook = workbooks.Open(str(input_path), None, True)
            if hr != S_OK:
                raise WpsOpenDocumentError(
                    f"Workbooks.Open failed: {self._format_hresult(hr)}"
                )

            result = workbook.ExportAsFixedFormat(
                etapi.xlTypePDF,
                str(output_path),
            )
            if result != S_OK:
                raise WpsConversionError(
                    f"Workbook.ExportAsFixedFormat failed: {self._format_hresult(result)}"
                )
        finally:
            if workbook is not None:
                self._close_workbook(workbook, etapi)

        return ConversionDetails(process_pid=session.process_pid)

    def stop_session(self, session: WpsSession) -> None:
        self._close_safely(session.app.Quit)

    def _get_workbooks_with_retry(self, app: Any) -> Any:
        last_error: Exception | None = None
        for delay_seconds in (0, 1, 2):
            if delay_seconds:
                sleep(delay_seconds)
            try:
                return app.Workbooks
            except Exception as exc:
                last_error = exc
        raise WpsStartupError(str(last_error) if last_error else "failed to get Workbooks")

    def _load_dependencies(self) -> tuple[Any, int, Any, Any]:
        try:
            from pywpsrpc.common import QtApp, S_OK
            from pywpsrpc.rpcetapi import createEtRpcInstance, etapi
        except ImportError as exc:
            raise WpsStartupError(f"pywpsrpc is not available: {exc}") from exc

        return QtApp, S_OK, createEtRpcInstance, etapi

    def _close_workbook(self, workbook: Any, etapi: Any) -> None:
        try:
            workbook.Close(False)
        except Exception:
            self._close_safely(lambda: workbook.Close(etapi.xlDoNotSaveChanges))
