from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
import os

from app.utils.cpu import detect_cpu_core_count, resolve_auto_writer_worker_count


MIN_WRITER_WORKER_COUNT = 1
MAX_WRITER_WORKER_COUNT = 32
FAMILY_WRITER = "writer"
FAMILY_SPREADSHEET = "spreadsheet"
FAMILY_PRESENTATION = "presentation"


def _clamp_writer_worker_count(value: int) -> int:
    return max(MIN_WRITER_WORKER_COUNT, min(MAX_WRITER_WORKER_COUNT, value))


def _parse_bool_env(name: str, default: bool) -> bool:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default

    normalized_value = raw_value.strip().lower()
    if normalized_value in {"1", "true", "yes", "on"}:
        return True
    if normalized_value in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"{name} must be a boolean value")


def resolve_writer_worker_count() -> int:
    raw_value = os.getenv("WPS_WORKER_COUNT", "").strip().lower()
    if raw_value in {"", "auto"}:
        detected_count = detect_cpu_core_count(fallback=MIN_WRITER_WORKER_COUNT)
        return _clamp_writer_worker_count(
            resolve_auto_writer_worker_count(detected_count)
        )

    try:
        configured_count = int(raw_value)
    except ValueError as exc:
        raise ValueError("WPS_WORKER_COUNT must be an integer or 'auto'") from exc

    return _clamp_writer_worker_count(configured_count)


@dataclass(frozen=True)
class Settings:
    api_prefix: str
    service_name: str
    workspace_root: Path
    jobs_dir: Path
    runtime_dir: Path
    conversion_timeout_seconds: int
    cleanup_max_age_seconds: int
    max_upload_size_bytes: int
    batch_max_files: int
    writer_worker_count: int
    warm_session_max_jobs: int
    warm_session_prewarm_enabled: bool
    enable_word: bool
    enable_excel: bool
    enable_ppt: bool

    def is_family_enabled(self, family: str) -> bool:
        family_flags = {
            FAMILY_WRITER: self.enable_word,
            FAMILY_SPREADSHEET: self.enable_excel,
            FAMILY_PRESENTATION: self.enable_ppt,
        }
        return family_flags.get(family, False)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    workspace_root = Path(os.getenv("WPS_WORKSPACE_ROOT", "/workspace"))
    jobs_dir = workspace_root / "jobs"
    runtime_dir = workspace_root / "runtime"
    writer_worker_count = resolve_writer_worker_count()
    return Settings(
        api_prefix="/api/v1",
        service_name="wps-api",
        workspace_root=workspace_root,
        jobs_dir=jobs_dir,
        runtime_dir=runtime_dir,
        conversion_timeout_seconds=int(
            os.getenv("WPS_CONVERSION_TIMEOUT_SECONDS", "120")
        ),
        cleanup_max_age_seconds=int(
            os.getenv("WPS_CLEANUP_MAX_AGE_SECONDS", str(24 * 60 * 60))
        ),
        max_upload_size_bytes=int(
            os.getenv("WPS_MAX_UPLOAD_SIZE_BYTES", str(50 * 1024 * 1024))
        ),
        batch_max_files=int(os.getenv("WPS_BATCH_MAX_FILES", "10")),
        writer_worker_count=writer_worker_count,
        warm_session_max_jobs=int(
            os.getenv("WPS_WARM_SESSION_MAX_JOBS", "100")
        ),
        warm_session_prewarm_enabled=(
            os.getenv("WPS_WARM_SESSION_PREWARM_ENABLED", "true").strip().lower()
            not in {"0", "false", "no", "off"}
        ),
        enable_word=_parse_bool_env("ENABLE_WORD", default=True),
        enable_excel=_parse_bool_env("ENABLE_EXCEL", default=False),
        enable_ppt=_parse_bool_env("ENABLE_PPT", default=False),
    )
