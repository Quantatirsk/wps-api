"""HTTP client for WPS API."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from urllib.parse import urljoin

import requests

from cli_anything.wps.utils.errors import (
    ConversionTimeoutError,
    ServiceUnavailableError,
    UnsupportedFormatError,
)


class APIClient:
    """Client for WPS API endpoints."""

    def __init__(self, base_url: str = "http://127.0.0.1:18000", timeout: int = 120):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({
            "Accept": "application/json",
        })

    def _make_url(self, path: str) -> str:
        """Build full URL from path."""
        return urljoin(self.base_url + "/", path.lstrip("/"))

    def health(self) -> dict[str, Any]:
        """Check service health (liveness probe).

        Returns:
            {"ok": True} if service is alive

        Raises:
            ServiceUnavailableError: If service cannot be reached
        """
        try:
            resp = self.session.get(
                self._make_url("/api/v1/healthz"),
                timeout=5,
            )
            resp.raise_for_status()
            return resp.json()
        except requests.ConnectionError as e:
            raise ServiceUnavailableError(
                f"Cannot connect to WPS API at {self.base_url}"
            ) from e
        except requests.Timeout as e:
            raise ServiceUnavailableError("Health check timed out") from e

    def ready(self) -> dict[str, Any]:
        """Check service readiness.

        Returns:
            {
                "ok": bool,
                "checks": {...},
                "families": {...}
            }

        Raises:
            ServiceUnavailableError: If service is not ready
        """
        try:
            resp = self.session.get(
                self._make_url("/api/v1/readyz"),
                timeout=5,
            )
            data = resp.json()

            if resp.status_code == 503 or not data.get("ok"):
                raise ServiceUnavailableError(
                    f"Service not ready: {data.get('checks', {})}"
                )

            return data
        except requests.ConnectionError as e:
            raise ServiceUnavailableError(
                f"Cannot connect to WPS API at {self.base_url}"
            ) from e

    def convert_single(self, file_path: str) -> tuple[bytes, dict[str, Any]]:
        """Convert a single file to PDF.

        Args:
            file_path: Path to input document

        Returns:
            Tuple of (PDF bytes, metadata dict)

        Raises:
            UnsupportedFormatError: If file format is not supported
            ConversionTimeoutError: If conversion times out
            ServiceUnavailableError: If service is unavailable
        """
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        try:
            with open(path, "rb") as f:
                files = {"file": (path.name, f)}
                resp = self.session.post(
                    self._make_url("/api/v1/convert-to-pdf"),
                    files=files,
                    timeout=self.timeout,
                )

            if resp.status_code == 415:
                raise UnsupportedFormatError(
                    f"Unsupported file format: {path.suffix}"
                )

            resp.raise_for_status()

            metadata = {
                "input_filename": path.name,
                "output_filename": f"{path.stem}.pdf",
                "content_type": resp.headers.get("Content-Type", "application/pdf"),
                "content_length": len(resp.content),
            }

            return resp.content, metadata

        except requests.Timeout as e:
            raise ConversionTimeoutError(self.timeout) from e
        except requests.ConnectionError as e:
            raise ServiceUnavailableError("Connection lost during conversion") from e

    def convert_batch(self, file_paths: list[str]) -> tuple[bytes, dict[str, Any]]:
        """Convert multiple files to PDF ZIP.

        Args:
            file_paths: List of paths to input documents

        Returns:
            Tuple of (ZIP bytes, metadata dict)

        Raises:
            UnsupportedFormatError: If any file format is not supported
            ConversionTimeoutError: If conversion times out
            ServiceUnavailableError: If service is unavailable
        """
        if not file_paths:
            raise ValueError("at least one file is required")

        files_to_close: list[Any] = []
        try:
            files = []
            for fp in file_paths:
                path = Path(fp)
                if not path.exists():
                    raise FileNotFoundError(f"File not found: {fp}")
                f = open(path, "rb")
                files_to_close.append(f)
                files.append(("files", (path.name, f)))

            total_timeout = self.timeout * len(file_paths)
            resp = self.session.post(
                self._make_url("/api/v1/convert-to-pdf/batch"),
                files=files,
                timeout=total_timeout,
            )

            if resp.status_code == 415:
                raise UnsupportedFormatError("One or more files have unsupported format")

            resp.raise_for_status()

            metadata = {
                "input_count": len(file_paths),
                "input_files": [Path(fp).name for fp in file_paths],
                "content_type": "application/zip",
                "content_length": len(resp.content),
            }

            return resp.content, metadata

        except requests.Timeout as e:
            raise ConversionTimeoutError(self.timeout * len(file_paths)) from e
        except requests.ConnectionError as e:
            raise ServiceUnavailableError("Connection lost during batch conversion") from e
        finally:
            for f in files_to_close:
                f.close()

    def get_supported_families(self) -> dict[str, bool]:
        """Get enabled document families from ready check.

        Returns:
            Dict mapping family names to enabled status
        """
        data = self.ready()
        return data.get("families", {
            "wordEnabled": True,
            "excelEnabled": False,
            "pptEnabled": False,
        })
