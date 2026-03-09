from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class ConversionDetails:
    process_pid: int | None


class BaseWpsAdapter(ABC):
    @abstractmethod
    def convert_to_pdf(
        self,
        input_path: Path,
        output_path: Path,
    ) -> ConversionDetails:
        raise NotImplementedError

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
