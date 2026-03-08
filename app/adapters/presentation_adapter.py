from __future__ import annotations

from pathlib import Path
from typing import Any

from app.adapters.base import BaseWpsAdapter, ConversionDetails
from app.utils.errors import (
    WpsConversionError,
    WpsOpenDocumentError,
    WpsStartupError,
)


class PresentationAdapter(BaseWpsAdapter):
    def convert_to_pdf(self, input_path: Path, output_path: Path) -> ConversionDetails:
        QtApp, S_OK, create_wpp_rpc_instance, wppapi = self._load_dependencies()

        _qt_app = QtApp([])
        hr, rpc = create_wpp_rpc_instance()
        if hr != S_OK:
            raise WpsStartupError(f"createWppRpcInstance failed: {self._format_hresult(hr)}")

        process_pid = self._get_process_pid(rpc, S_OK)

        hr, app = rpc.getWppApplication()
        if hr != S_OK:
            raise WpsStartupError(f"getWppApplication failed: {self._format_hresult(hr)}")

        presentation = None
        try:
            try:
                app.Visible = False
            except Exception:
                pass
            hr, presentation = app.Presentations.Open(
                str(input_path),
                wppapi.msoTrue,
                wppapi.msoFalse,
                wppapi.msoFalse,
            )
            if hr != S_OK:
                raise WpsOpenDocumentError(
                    f"Presentations.Open failed: {self._format_hresult(hr)}"
                )

            result = presentation.ExportAsFixedFormat(
                str(output_path),
                wppapi.ppFixedFormatTypePDF,
                wppapi.ppFixedFormatIntentScreen,
                wppapi.msoFalse,
                wppapi.ppPrintHandoutVerticalFirst,
                wppapi.ppPrintOutputSlides,
                wppapi.msoFalse,
                None,
                wppapi.ppPrintAll,
                "",
                False,
                True,
                True,
                True,
                False,
            )
            if result != S_OK:
                raise WpsConversionError(
                    f"Presentation.ExportAsFixedFormat failed: {self._format_hresult(result)}"
                )
        finally:
            if presentation is not None:
                try:
                    presentation.Close()
                except Exception:
                    pass
            try:
                app.Quit()
            except Exception:
                pass

        return ConversionDetails(process_pid=process_pid)

    def _load_dependencies(self) -> tuple[Any, int, Any, Any]:
        try:
            from pywpsrpc.common import QtApp, S_OK
            from pywpsrpc.rpcwppapi import createWppRpcInstance, wppapi
        except ImportError as exc:
            raise WpsStartupError(f"pywpsrpc is not available: {exc}") from exc

        return QtApp, S_OK, createWppRpcInstance, wppapi
