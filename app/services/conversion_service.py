from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import asyncio
import time

from fastapi import UploadFile

from app.config import Settings
from app.runtime.warm_session_manager import get_warm_session_manager
from app.utils.errors import (
    ConversionTimeoutError,
    InvalidInputError,
    PayloadTooLargeError,
    UnsupportedFormatError,
    WpsConversionError,
)
from app.utils.files import (
    BatchPaths,
    JobPaths,
    build_batch_paths,
    build_job_paths,
    cleanup_job_dir,
    cleanup_paths,
    create_zip_archive,
    get_file_size,
    get_safe_stem,
    persist_upload_file,
    write_job_metadata,
    write_json_file,
)
from app.utils.logging import get_logger


@dataclass(frozen=True)
class PreparedConversionJob:
    document_family: str
    job_paths: JobPaths
    input_filename: str
    output_filename: str
    input_size: int


@dataclass(frozen=True)
class ConversionJobResult:
    job_id: str
    job_dir: Path
    output_path: Path
    input_filename: str
    output_filename: str
    document_family: str
    queue_wait_ms: int
    convert_ms: int
    duration_ms: int
    process_pid: int | None
    warm_hit: bool | None


@dataclass(frozen=True)
class BatchConversionResult:
    batch_id: str
    zip_path: Path
    cleanup_paths: list[Path]


ROUTES_BY_SUFFIX: dict[str, str] = {
    ".doc": "writer",
    ".docx": "writer",
    ".ppt": "presentation",
    ".pptx": "presentation",
    ".xls": "spreadsheet",
    ".xlsx": "spreadsheet",
}
SUPPORTED_SUFFIXES = ", ".join(sorted(ROUTES_BY_SUFFIX))


class ConversionService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.logger = get_logger(__name__)
        self.session_manager = get_warm_session_manager(settings)

    async def convert_file_to_pdf(self, upload_file: UploadFile) -> ConversionJobResult:
        prepared_job = await self._prepare_job(upload_file)
        return await self._run_conversion(prepared_job)

    async def convert_files_to_pdf_batch(
        self,
        upload_files: list[UploadFile],
    ) -> BatchConversionResult:
        if not upload_files:
            raise InvalidInputError("at least one file is required")
        if len(upload_files) > self.settings.batch_max_files:
            raise InvalidInputError(
                f"batch supports at most {self.settings.batch_max_files} files"
            )

        prepared_jobs = [
            await self._prepare_job(upload_file) for upload_file in upload_files
        ]
        results = await asyncio.gather(
            *(self._run_conversion(prepared_job) for prepared_job in prepared_jobs),
            return_exceptions=True,
        )
        return self._build_batch_result(results)

    async def _prepare_job(self, upload_file: UploadFile) -> PreparedConversionJob:
        document_family = self._get_document_family_or_raise(upload_file.filename)
        job_paths = build_job_paths(self.settings, upload_file.filename)
        output_filename = f"{get_safe_stem(upload_file.filename)}.pdf"

        try:
            size = await persist_upload_file(upload_file, job_paths.input_path)
            self._validate_file_size(size, job_paths)
            return PreparedConversionJob(
                document_family=document_family,
                job_paths=job_paths,
                input_filename=upload_file.filename or job_paths.input_path.name,
                output_filename=output_filename,
                input_size=size,
            )
        except Exception:
            if job_paths.job_dir.exists() and not job_paths.output_path.exists():
                cleanup_job_dir(job_paths.job_dir)
            raise

    async def _run_conversion(
        self,
        prepared_job: PreparedConversionJob,
    ) -> ConversionJobResult:
        started_at = time.perf_counter()
        self.logger.info(
            "conversion_started job_id=%s family=%s file=%s size=%s",
            prepared_job.job_paths.job_id,
            prepared_job.document_family,
            prepared_job.input_filename,
            prepared_job.input_size,
        )
        try:
            warm_result = await self.session_manager.convert(
                prepared_job.document_family,
                prepared_job.job_paths.input_path,
                prepared_job.job_paths.output_path,
                self.settings.conversion_timeout_seconds,
            )
        except ConversionTimeoutError:
            cleanup_job_dir(prepared_job.job_paths.job_dir)
            raise
        except Exception as exc:
            cleanup_job_dir(prepared_job.job_paths.job_dir)
            self.logger.exception(
                "conversion_failed job_id=%s family=%s file=%s",
                prepared_job.job_paths.job_id,
                prepared_job.document_family,
                prepared_job.input_filename,
            )
            raise WpsConversionError(str(exc)) from exc

        if not prepared_job.job_paths.output_path.exists():
            cleanup_job_dir(prepared_job.job_paths.job_dir)
            raise WpsConversionError("conversion completed without output file")

        finished_at = time.perf_counter()
        queue_wait_ms = 0
        convert_ms = int((finished_at - started_at) * 1000)
        duration_ms = convert_ms
        result = ConversionJobResult(
            job_id=prepared_job.job_paths.job_id,
            job_dir=prepared_job.job_paths.job_dir,
            output_path=prepared_job.job_paths.output_path,
            input_filename=prepared_job.input_filename,
            output_filename=prepared_job.output_filename,
            document_family=prepared_job.document_family,
            queue_wait_ms=queue_wait_ms,
            convert_ms=convert_ms,
            duration_ms=duration_ms,
            process_pid=warm_result.process_pid,
            warm_hit=warm_result.warm_hit,
        )
        write_job_metadata(prepared_job.job_paths, self._build_job_metadata(result))
        self.logger.info(
            "conversion_succeeded job_id=%s family=%s warm_hit=%s queue_wait_ms=%s convert_ms=%s total_ms=%s",
            result.job_id,
            result.document_family,
            result.warm_hit,
            result.queue_wait_ms,
            result.convert_ms,
            result.duration_ms,
        )
        return result

    def _build_batch_result(
        self,
        results: list[ConversionJobResult | Exception],
    ) -> BatchConversionResult:
        exceptions = [result for result in results if isinstance(result, Exception)]
        successful_results = [
            result for result in results if isinstance(result, ConversionJobResult)
        ]
        if exceptions:
            cleanup_paths([result.job_dir for result in successful_results])
            raise exceptions[0]

        batch_paths = build_batch_paths(self.settings)
        cleanup_targets = [
            batch_paths.batch_dir,
            *[result.job_dir for result in successful_results],
        ]

        try:
            write_json_file(
                batch_paths.manifest_path,
                self._build_batch_manifest(batch_paths.batch_id, successful_results),
            )
            create_zip_archive(
                batch_paths.zip_path,
                self._build_batch_archive_entries(successful_results, batch_paths),
            )
        except Exception:
            cleanup_paths(cleanup_targets)
            raise

        self.logger.info(
            "batch_conversion_succeeded batch_id=%s item_count=%s",
            batch_paths.batch_id,
            len(successful_results),
        )
        return BatchConversionResult(
            batch_id=batch_paths.batch_id,
            zip_path=batch_paths.zip_path,
            cleanup_paths=cleanup_targets,
        )

    def _get_document_family_or_raise(self, filename: str | None) -> str:
        suffix = Path(filename or "").suffix.lower()
        document_family = ROUTES_BY_SUFFIX.get(suffix)
        if document_family is None:
            raise UnsupportedFormatError(
                f"unsupported file format, supported formats: {SUPPORTED_SUFFIXES}"
            )
        return document_family

    def _validate_file_size(self, size: int, job_paths: JobPaths) -> None:
        if size > self.settings.max_upload_size_bytes:
            cleanup_job_dir(job_paths.job_dir)
            raise PayloadTooLargeError("uploaded file exceeds configured size limit")

    def _build_batch_manifest(
        self,
        batch_id: str,
        results: list[ConversionJobResult],
    ) -> dict[str, object]:
        return {
            "batchId": batch_id,
            "itemCount": len(results),
            "items": [self._build_result_payload(result) for result in results],
        }

    def _build_batch_archive_entries(
        self,
        results: list[ConversionJobResult],
        batch_paths: BatchPaths,
    ) -> list[tuple[Path, str]]:
        used_names: set[str] = set()
        entries: list[tuple[Path, str]] = []
        for index, result in enumerate(results, start=1):
            archive_name = self._dedupe_archive_name(
                f"outputs/{result.output_filename}",
                used_names,
                index,
            )
            entries.append((result.output_path, archive_name))
        entries.append((batch_paths.manifest_path, "manifest.json"))
        return entries

    def _dedupe_archive_name(
        self,
        candidate: str,
        used_names: set[str],
        index: int,
    ) -> str:
        if candidate not in used_names:
            used_names.add(candidate)
            return candidate

        path = Path(candidate)
        deduped = f"{path.parent}/{path.stem}_{index}{path.suffix}"
        used_names.add(deduped)
        return deduped

    def _build_job_metadata(self, result: ConversionJobResult) -> dict[str, object]:
        payload = self._build_result_payload(result)
        payload["mode"] = "local"
        payload["fileSize"] = get_file_size(result.output_path)
        return payload

    def _build_result_payload(self, result: ConversionJobResult) -> dict[str, object]:
        return {
            "jobId": result.job_id,
            "documentFamily": result.document_family,
            "inputFilename": result.input_filename,
            "outputFilename": result.output_filename,
            "queueWaitMs": result.queue_wait_ms,
            "convertMs": result.convert_ms,
            "durationMs": result.duration_ms,
            "processPid": result.process_pid,
            "warmHit": result.warm_hit,
            "status": "succeeded",
        }
