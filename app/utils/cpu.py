from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os
import subprocess
import time


def resolve_auto_writer_worker_count(cpu_core_count: int) -> int:
    if cpu_core_count < 8:
        return cpu_core_count
    if cpu_core_count <= 16:
        return cpu_core_count - 2
    return 16


def detect_cpu_core_count(fallback: int) -> int:
    return (
        _detect_cpu_cores_from_lscpu()
        or _detect_cpu_cores_from_proc_cpuinfo()
        or _detect_cpu_cores_from_sysctl()
        or os.cpu_count()
        or fallback
    )


def supports_process_cpu_sampling() -> bool:
    return Path("/proc").exists()


@dataclass(frozen=True)
class ProcessCpuSample:
    captured_monotonic: float
    total_cpu_seconds: float


def sample_process_cpu_percent(
    pid: int,
    previous: ProcessCpuSample | None,
) -> tuple[ProcessCpuSample | None, float | None]:
    current = _read_process_cpu_sample(pid)
    if current is None:
        return None, None
    if previous is None:
        return current, None

    elapsed_seconds = current.captured_monotonic - previous.captured_monotonic
    if elapsed_seconds <= 0:
        return current, None

    cpu_seconds = current.total_cpu_seconds - previous.total_cpu_seconds
    if cpu_seconds < 0:
        return current, None

    return current, (cpu_seconds / elapsed_seconds) * 100.0


def _parse_positive_int(raw_value: str) -> int | None:
    value = raw_value.strip()
    if not value.isdigit():
        return None

    parsed = int(value)
    if parsed <= 0:
        return None
    return parsed


def _detect_cpu_cores_from_lscpu() -> int | None:
    try:
        result = subprocess.run(
            ["lscpu", "-p=core,socket"],
            check=True,
            capture_output=True,
            text=True,
        )
    except (FileNotFoundError, subprocess.CalledProcessError):
        return None

    pairs = {
        line.strip()
        for line in result.stdout.splitlines()
        if line.strip() and not line.startswith("#")
    }
    return len(pairs) or None


def _detect_cpu_cores_from_proc_cpuinfo() -> int | None:
    cpuinfo_path = Path("/proc/cpuinfo")
    if not cpuinfo_path.exists():
        return None

    socket_cores: dict[str, int] = {}
    current_socket: str | None = None
    current_cores: int | None = None

    for line in cpuinfo_path.read_text(encoding="utf-8", errors="ignore").splitlines():
        if not line.strip():
            if current_cores is not None:
                socket_key = current_socket or "socket-0"
                socket_cores[socket_key] = current_cores
            current_socket = None
            current_cores = None
            continue

        key, _, raw_value = line.partition(":")
        value = raw_value.strip()
        normalized_key = key.strip().lower()
        if normalized_key == "physical id":
            current_socket = value or "socket-0"
        elif normalized_key == "cpu cores":
            current_cores = _parse_positive_int(value)

    if current_cores is not None:
        socket_key = current_socket or "socket-0"
        socket_cores[socket_key] = current_cores

    if socket_cores:
        return sum(socket_cores.values())
    return None


def _detect_cpu_cores_from_sysctl() -> int | None:
    try:
        result = subprocess.run(
            ["sysctl", "-n", "hw.physicalcpu"],
            check=True,
            capture_output=True,
            text=True,
        )
    except (FileNotFoundError, subprocess.CalledProcessError):
        return None

    return _parse_positive_int(result.stdout)


def _read_process_cpu_sample(pid: int) -> ProcessCpuSample | None:
    stat_path = Path(f"/proc/{pid}/stat")
    if not stat_path.exists():
        return None

    try:
        stat_content = stat_path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return None

    closing_paren_index = stat_content.rfind(")")
    if closing_paren_index < 0:
        return None

    fields = stat_content[closing_paren_index + 2 :].split()
    if len(fields) < 15:
        return None

    try:
        utime_ticks = int(fields[11])
        stime_ticks = int(fields[12])
    except ValueError:
        return None

    clock_ticks_per_second = os.sysconf("SC_CLK_TCK")
    total_cpu_seconds = (utime_ticks + stime_ticks) / clock_ticks_per_second
    return ProcessCpuSample(
        captured_monotonic=time.monotonic(),
        total_cpu_seconds=total_cpu_seconds,
    )
