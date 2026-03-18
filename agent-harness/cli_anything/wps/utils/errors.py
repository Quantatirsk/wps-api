"""Error handling for WPS CLI."""

from __future__ import annotations

import json
import sys
from typing import Any, Optional

import click


class CLIError(Exception):
    """Base CLI error with structured output."""

    def __init__(
        self,
        message: str,
        code: str = "ERROR",
        exit_code: int = 1,
        details: Optional[dict[str, Any]] = None,
    ):
        self.message = message
        self.code = code
        self.exit_code = exit_code
        self.details = details or {}
        super().__init__(message)

    def to_json(self) -> dict[str, Any]:
        return {
            "error": self.message,
            "code": self.code,
            "details": self.details,
        }

    def show(self, json_output: bool = False) -> None:
        if json_output:
            click.echo(json.dumps(self.to_json(), indent=2), err=True)
        else:
            click.echo(f"Error [{self.code}]: {self.message}", err=True)
            if self.details:
                for key, value in self.details.items():
                    click.echo(f"  {key}: {value}", err=True)
        sys.exit(self.exit_code)


class UnsupportedFormatError(CLIError):
    """Raised when file format is not supported."""

    def __init__(self, message: str = "Unsupported file format"):
        super().__init__(
            message=message,
            code="UNSUPPORTED_FORMAT",
            exit_code=2,
        )


class FamilyDisabledError(CLIError):
    """Raised when document family is disabled."""

    def __init__(self, family: str):
        super().__init__(
            message=f"Document family is disabled: {family}",
            code="FAMILY_DISABLED",
            exit_code=2,
            details={"family": family},
        )


class ServiceUnavailableError(CLIError):
    """Raised when service is not available."""

    def __init__(self, message: str = "Service unavailable"):
        super().__init__(
            message=message,
            code="SERVICE_UNAVAILABLE",
            exit_code=3,
        )


class ConversionTimeoutError(CLIError):
    """Raised when conversion times out."""

    def __init__(self, timeout: int):
        super().__init__(
            message=f"Conversion timed out after {timeout}s",
            code="CONVERSION_TIMEOUT",
            exit_code=1,
            details={"timeout": timeout},
        )


class PayloadTooLargeError(CLIError):
    """Raised when file exceeds size limit."""

    def __init__(self, max_size: int):
        super().__init__(
            message=f"File exceeds maximum size of {max_size} bytes",
            code="PAYLOAD_TOO_LARGE",
            exit_code=2,
            details={"max_size": max_size},
        )


def handle_errors(func: Any) -> Any:
    """Decorator for consistent error handling."""

    def wrapper(*args: Any, **kwargs: Any) -> Any:
        try:
            return func(*args, **kwargs)
        except CLIError as e:
            ctx = click.get_current_context()
            json_output = ctx.obj.get("json_output", False) if ctx and ctx.obj else False
            e.show(json_output)
        except click.ClickException:
            raise
        except Exception as e:
            err = CLIError(str(e), code="UNEXPECTED", exit_code=1)
            ctx = click.get_current_context()
            json_output = ctx.obj.get("json_output", False) if ctx and ctx.obj else False
            err.show(json_output)

    return wrapper
