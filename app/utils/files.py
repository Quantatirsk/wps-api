from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
import json
import os
import shutil
import uuid
import zipfile

from fastapi import UploadFile

from app.config import Settings


@dataclass(frozen=True)
class JobPaths:
    job_id: str
    job_dir: Path
    input_path: Path
    output_path: Path
    metadata_path: Path


@dataclass(frozen=True)
class BatchPaths:
    batch_id: str
    batch_dir: Path
    zip_path: Path
    manifest_path: Path


def ensure_runtime_directories(settings: Settings) -> None:
    settings.workspace_root.mkdir(parents=True, exist_ok=True)
    settings.jobs_dir.mkdir(parents=True, exist_ok=True)
    settings.runtime_dir.mkdir(parents=True, exist_ok=True)


def build_job_paths(settings: Settings, original_filename: str | None) -> JobPaths:
    suffix = get_safe_suffix(original_filename)
    job_id = uuid.uuid4().hex
    job_dir = settings.jobs_dir / job_id
    job_dir.mkdir(parents=True, exist_ok=True)
    return JobPaths(
        job_id=job_id,
        job_dir=job_dir,
        input_path=job_dir / f"input{suffix}",
        output_path=job_dir / "output.pdf",
        metadata_path=job_dir / "meta.json",
    )


def build_batch_paths(settings: Settings) -> BatchPaths:
    batch_id = f"batch-{uuid.uuid4().hex}"
    batch_dir = settings.jobs_dir / batch_id
    batch_dir.mkdir(parents=True, exist_ok=True)
    return BatchPaths(
        batch_id=batch_id,
        batch_dir=batch_dir,
        zip_path=batch_dir / "outputs.zip",
        manifest_path=batch_dir / "manifest.json",
    )


async def persist_upload_file(upload_file: UploadFile, destination: Path) -> int:
    size = 0
    with destination.open("wb") as output_file:
        while True:
            chunk = await upload_file.read(1024 * 1024)
            if not chunk:
                break
            output_file.write(chunk)
            size += len(chunk)
    await upload_file.close()
    return size


def write_job_metadata(job_paths: JobPaths, payload: dict[str, object]) -> None:
    write_json_file(job_paths.metadata_path, payload)


def write_json_file(path: Path, payload: dict[str, object]) -> None:
    with path.open("w", encoding="utf-8") as output_file:
        json.dump(payload, output_file, ensure_ascii=False, indent=2)


def create_zip_archive(zip_path: Path, files: list[tuple[Path, str]]) -> None:
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for source_path, archive_name in files:
            archive.write(source_path, arcname=archive_name)


def cleanup_job_dir(job_dir: Path) -> None:
    shutil.rmtree(job_dir, ignore_errors=True)


def cleanup_paths(paths: list[Path]) -> None:
    seen: set[Path] = set()
    for path in paths:
        if path in seen:
            continue
        seen.add(path)
        if path.is_dir():
            shutil.rmtree(path, ignore_errors=True)
        else:
            path.unlink(missing_ok=True)


def cleanup_expired_jobs(jobs_dir: Path, max_age_seconds: int) -> int:
    if not jobs_dir.exists():
        return 0

    threshold = datetime.now(timezone.utc) - timedelta(seconds=max_age_seconds)
    deleted_count = 0
    for child in jobs_dir.iterdir():
        if not child.is_dir():
            continue
        modified_at = datetime.fromtimestamp(child.stat().st_mtime, tz=timezone.utc)
        if modified_at < threshold:
            shutil.rmtree(child, ignore_errors=True)
            deleted_count += 1
    return deleted_count


def get_safe_suffix(filename: str | None) -> str:
    suffix = Path(filename or "").suffix.lower()
    return suffix


def get_safe_stem(filename: str | None, default: str = "output") -> str:
    stem = Path(filename or default).stem.strip()
    safe = "".join(char if char.isalnum() or char in {"-", "_"} else "_" for char in stem)
    return safe or default


def get_file_size(path: Path) -> int:
    return os.path.getsize(path)
