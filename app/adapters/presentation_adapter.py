from __future__ import annotations

from pathlib import Path
from typing import Any

from app.adapters.base import BaseWpsAdapter, ConversionDetails, WpsSession
from app.utils.errors import (
    WpsConversionError,
    WpsOpenDocumentError,
    WpsStartupError,
)


class PresentationAdapter(BaseWpsAdapter):
    def start_session(self) -> WpsSession:
        QtApp, S_OK, create_wpp_rpc_instance, _ = self._load_dependencies()
        return self._start_session(
            qt_app_factory=QtApp,
            success_code=S_OK,
            create_rpc_instance=create_wpp_rpc_instance,
            get_application=lambda rpc: rpc.getWppApplication(),
            create_rpc_instance_name="createWppRpcInstance",
            get_application_name="getWppApplication",
        )

    def convert_with_session(
        self,
        session: WpsSession,
        input_path: Path,
        output_path: Path,
    ) -> ConversionDetails:
        _, S_OK, _, wppapi = self._load_dependencies()

        presentation = None
        try:
            hr, presentation = session.app.Presentations.Open(
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
                self._close_safely(presentation.Close)

        return ConversionDetails(process_pid=session.process_pid)

    def stop_session(self, session: WpsSession) -> None:
        self._close_safely(session.app.Quit)

    def _load_dependencies(self) -> tuple[Any, int, Any, Any]:
        try:
            from pywpsrpc.common import QtApp, S_OK
            from pywpsrpc.rpcwppapi import createWppRpcInstance, wppapi
        except ImportError as exc:
            raise WpsStartupError(f"pywpsrpc is not available: {exc}") from exc

        return QtApp, S_OK, createWppRpcInstance, wppapi
