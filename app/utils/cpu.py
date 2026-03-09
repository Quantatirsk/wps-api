from __future__ import annotations

from pathlib import Path
import os
import subprocess


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
