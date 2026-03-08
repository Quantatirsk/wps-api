from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol
import asyncio

from app.adapters.base import ConversionDetails


class PdfAdapter(Protocol):
    def convert_to_pdf(self, input_path: Path, output_path: Path) -> ConversionDetails: ...


@dataclass(frozen=True)
class ConversionRoute:
    document_family: str
    supported_suffixes: frozenset[str]
    adapter: PdfAdapter
    lock: asyncio.Lock

    def supports(self, filename: str | None) -> bool:
        suffix = Path(filename or "").suffix.lower()
        return suffix in self.supported_suffixes


class ConversionRegistry:
    def __init__(self, routes: list[ConversionRoute]) -> None:
        self.routes = routes

    def get_route(self, filename: str | None) -> ConversionRoute:
        for route in self.routes:
            if route.supports(filename):
                return route
        supported = ", ".join(sorted(self.get_supported_suffixes()))
        raise ValueError(f"unsupported file format, supported formats: {supported}")

    def is_supported(self, filename: str | None) -> bool:
        return any(route.supports(filename) for route in self.routes)

    def get_supported_suffixes(self) -> set[str]:
        suffixes: set[str] = set()
        for route in self.routes:
            suffixes.update(route.supported_suffixes)
        return suffixes
