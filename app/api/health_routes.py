from __future__ import annotations

from importlib.util import find_spec
import os
from shutil import which
import subprocess

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.config import get_settings
from app.utils.files import ensure_runtime_directories

router = APIRouter(tags=["health"])


def _is_command_ready(command: str) -> bool:
    executable = which(command)
    if executable is None:
        return False

    try:
        subprocess.run(
            [executable, "--version"],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except Exception:
        return False

    return True


@router.get("/healthz")
async def healthz() -> dict[str, bool]:
    return {"ok": True}


@router.get("/readyz")
async def readyz() -> JSONResponse:
    settings = get_settings()
    ensure_runtime_directories(settings)

    checks = {
        "jobsDirWritable": os.access(settings.jobs_dir, os.W_OK),
        "runtimeDirWritable": os.access(settings.runtime_dir, os.W_OK),
        "displayConfigured": bool(os.getenv("DISPLAY")),
        "xdgRuntimeDirConfigured": bool(os.getenv("XDG_RUNTIME_DIR")),
        "pywpsrpcInstalled": find_spec("pywpsrpc.common") is not None,
        "ghostscriptReady": (
            _is_command_ready("gs") if settings.pdf_optimize_enabled else True
        ),
    }
    ready = all(checks.values())
    status_code = 200 if ready else 503
    return JSONResponse(status_code=status_code, content={"ok": ready, "checks": checks})
