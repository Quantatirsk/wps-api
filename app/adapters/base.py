from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ConversionDetails:
    process_pid: int | None


class BaseWpsAdapter:
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
