from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import shutil
import subprocess

from app.utils.logging import get_logger

logger = get_logger(__name__)

PDF_COMPATIBILITY_LEVEL = "1.7"
PDF_IMAGE_RESOLUTION = 150


@dataclass(frozen=True)
class PdfOptimizationOptions:
    enabled: bool = True


def optimize_pdf_in_place(
    pdf_path: Path,
    options: PdfOptimizationOptions | None = None,
) -> None:
    settings = options or PdfOptimizationOptions()
    if not settings.enabled or not pdf_path.exists():
        return

    ghostscript = shutil.which("gs")
    if ghostscript is None:
        return

    optimized_path = pdf_path.with_suffix(".optimized.pdf")
    command = [
        ghostscript,
        "-sDEVICE=pdfwrite",
        f"-dCompatibilityLevel={PDF_COMPATIBILITY_LEVEL}",
        "-dNOPAUSE",
        "-dBATCH",
        "-dSAFER",
        "-dDetectDuplicateImages=true",
        "-dCompressFonts=true",
        "-dSubsetFonts=true",
        "-dEmbedAllFonts=true",
        "-dColorImageDownsampleType=/Bicubic",
        f"-dColorImageResolution={PDF_IMAGE_RESOLUTION}",
        "-dGrayImageDownsampleType=/Bicubic",
        f"-dGrayImageResolution={PDF_IMAGE_RESOLUTION}",
        "-dMonoImageDownsampleType=/Subsample",
        f"-dMonoImageResolution={PDF_IMAGE_RESOLUTION}",
        "-dDownsampleColorImages=true",
        "-dDownsampleGrayImages=true",
        "-dDownsampleMonoImages=true",
        f"-sOutputFile={optimized_path}",
        str(pdf_path),
    ]
    before_size = pdf_path.stat().st_size

    try:
        subprocess.run(
            command,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
    except subprocess.CalledProcessError as exc:
        error_tail = exc.stderr.strip().splitlines()[-1] if exc.stderr else str(exc)
        logger.warning("pdf_optimize_failed path=%s error=%s", pdf_path, error_tail)
        optimized_path.unlink(missing_ok=True)
        return
    except Exception as exc:
        logger.warning("pdf_optimize_failed path=%s error=%s", pdf_path, exc)
        optimized_path.unlink(missing_ok=True)
        return

    if not optimized_path.exists():
        return

    after_size = optimized_path.stat().st_size
    if after_size < before_size:
        optimized_path.replace(pdf_path)
        logger.info(
            "pdf_optimized path=%s before_bytes=%s after_bytes=%s",
            pdf_path,
            before_size,
            after_size,
        )
        return

    optimized_path.unlink(missing_ok=True)
    logger.info(
        "pdf_optimization_skipped path=%s before_bytes=%s after_bytes=%s",
        pdf_path,
        before_size,
        after_size,
    )
