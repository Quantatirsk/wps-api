from __future__ import annotations

from pathlib import Path
from typing import Any

from app.adapters.base import BaseWpsAdapter, ConversionDetails, WpsSession
from app.utils.errors import (
    WpsConversionError,
    WpsOpenDocumentError,
    WpsStartupError,
)


class WriterAdapter(BaseWpsAdapter):
    def start_session(self) -> WpsSession:
        QtApp, S_OK, create_wps_rpc_instance, _ = self._load_dependencies()
        return self._start_session(
            qt_app_factory=QtApp,
            success_code=S_OK,
            create_rpc_instance=create_wps_rpc_instance,
            get_application=lambda rpc: rpc.getWpsApplication(),
            create_rpc_instance_name="createWpsRpcInstance",
            get_application_name="getWpsApplication",
        )

    def convert_with_session(
        self,
        session: WpsSession,
        input_path: Path,
        output_path: Path,
    ) -> ConversionDetails:
        _, S_OK, _, wpsapi = self._load_dependencies()

        document = None
        try:
            hr, document = session.app.Documents.Open(str(input_path), ReadOnly=True)
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
                self._close_safely(lambda: document.Close(wpsapi.wdDoNotSaveChanges))

        return ConversionDetails(process_pid=session.process_pid)

    def stop_session(self, session: WpsSession) -> None:
        _, _, _, wpsapi = self._load_dependencies()
        self._close_safely(lambda: session.app.Quit(wpsapi.wdDoNotSaveChanges))

    def _load_dependencies(self) -> tuple[Any, int, Any, Any]:
        try:
            from pywpsrpc.common import QtApp, S_OK
            from pywpsrpc.rpcwpsapi import createWpsRpcInstance, wpsapi
        except ImportError as exc:
            raise WpsStartupError(f"pywpsrpc is not available: {exc}") from exc

        return QtApp, S_OK, createWpsRpcInstance, wpsapi
