from __future__ import annotations

from pathlib import Path
from time import sleep
from typing import Any

from app.adapters.base import BaseWpsAdapter, ConversionDetails
from app.utils.errors import (
    WpsConversionError,
    WpsOpenDocumentError,
    WpsStartupError,
)


class SpreadsheetAdapter(BaseWpsAdapter):
    def convert_to_pdf(self, input_path: Path, output_path: Path) -> ConversionDetails:
        QtApp, S_OK, create_et_rpc_instance, etapi = self._load_dependencies()

        _qt_app = QtApp([])
        hr, rpc = create_et_rpc_instance()
        if hr != S_OK:
            raise WpsStartupError(f"createEtRpcInstance failed: {self._format_hresult(hr)}")

        process_pid = self._get_process_pid(rpc, S_OK)

        hr, app = rpc.getEtApplication()
        if hr != S_OK:
            raise WpsStartupError(f"getEtApplication failed: {self._format_hresult(hr)}")

        workbook = None
        try:
            try:
                app.Visible = False
            except Exception:
                pass

            workbooks = self._get_workbooks_with_retry(app)
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
                try:
                    workbook.Close(False)
                except Exception:
                    try:
                        workbook.Close(etapi.xlDoNotSaveChanges)
                    except Exception:
                        pass
            try:
                app.Quit()
            except Exception:
                pass

        return ConversionDetails(process_pid=process_pid)

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
