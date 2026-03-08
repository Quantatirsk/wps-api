from __future__ import annotations

from pathlib import Path
from typing import Any

from app.adapters.base import BaseWpsAdapter, ConversionDetails
from app.utils.errors import (
    WpsConversionError,
    WpsOpenDocumentError,
    WpsStartupError,
)


class WriterAdapter(BaseWpsAdapter):
    def convert_to_pdf(self, input_path: Path, output_path: Path) -> ConversionDetails:
        QtApp, S_OK, create_wps_rpc_instance, wpsapi = self._load_dependencies()

        _qt_app = QtApp([])
        hr, rpc = create_wps_rpc_instance()
        if hr != S_OK:
            raise WpsStartupError(f"createWpsRpcInstance failed: {self._format_hresult(hr)}")

        process_pid = self._get_process_pid(rpc, S_OK)

        hr, app = rpc.getWpsApplication()
        if hr != S_OK:
            raise WpsStartupError(f"getWpsApplication failed: {self._format_hresult(hr)}")

        document = None
        try:
            try:
                app.Visible = False
            except Exception:
                pass
            hr, document = app.Documents.Open(str(input_path), ReadOnly=True)
            if hr != S_OK:
                raise WpsOpenDocumentError(
                    f"Documents.Open failed: {self._format_hresult(hr)}"
                )

            result = document.SaveAs2(str(output_path), wpsapi.wdFormatPDF)
            if result != S_OK:
                raise WpsConversionError(
                    f"SaveAs2 PDF failed: {self._format_hresult(result)}"
                )
        finally:
            if document is not None:
                try:
                    document.Close(wpsapi.wdDoNotSaveChanges)
                except Exception:
                    pass
            try:
                app.Quit(wpsapi.wdDoNotSaveChanges)
            except Exception:
                pass

        return ConversionDetails(process_pid=process_pid)

    def _load_dependencies(self) -> tuple[Any, int, Any, Any]:
        try:
            from pywpsrpc.common import QtApp, S_OK
            from pywpsrpc.rpcwpsapi import createWpsRpcInstance, wpsapi
        except ImportError as exc:
            raise WpsStartupError(f"pywpsrpc is not available: {exc}") from exc

        return QtApp, S_OK, createWpsRpcInstance, wpsapi
