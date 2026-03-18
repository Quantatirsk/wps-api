"""Health check commands for WPS CLI."""

from __future__ import annotations

from typing import Any

import click

from cli_anything.wps.core.state import load_config
from cli_anything.wps.utils.errors import handle_errors
from cli_anything.wps.utils.http_client import APIClient
from cli_anything.wps.utils.output import (
    output_health_status,
    output_ready_status,
    output_result,
)


@click.group(name="health")
def health_cmds() -> None:
    """Health check commands."""
    pass


@health_cmds.command(name="check")
@click.pass_context
@handle_errors
def health_check(ctx: click.Context) -> None:
    """Quick health check (liveness probe).

    Verifies that the service is running and responding.
    This is a lightweight check suitable for load balancers.

    Examples:
        wps health check
        wps health check --json
    """
    config = load_config(ctx.obj.get("config_path") if ctx.obj else None)
    client = APIClient(config.api_url, config.timeout)

    result = client.health()

    def formatter(data: dict[str, Any]) -> None:
        output_health_status(data)

    output_result(ctx, result, formatter)


@click.group(name="ready")
def ready_cmds() -> None:
    """Readiness check commands."""
    pass


@ready_cmds.command(name="check")
@click.pass_context
@handle_errors
def ready_check(ctx: click.Context) -> None:
    """Detailed readiness check.

    Verifies that the service is ready to accept conversions,
    including system checks and document family status.

    Examples:
        wps ready check
        wps ready check --json
    """
    config = load_config(ctx.obj.get("config_path") if ctx.obj else None)
    client = APIClient(config.api_url, config.timeout)

    result = client.ready()

    def formatter(data: dict[str, Any]) -> None:
        output_ready_status(data)

    output_result(ctx, result, formatter)


# Also provide direct commands for convenience


@click.command(name="health")
@click.pass_context
@handle_errors
def health_cmd(ctx: click.Context) -> None:
    """Quick health check (liveness probe).

    Examples:
        wps health
        wps health --json
    """
    config = load_config(ctx.obj.get("config_path") if ctx.obj else None)
    client = APIClient(config.api_url, config.timeout)
    result = client.health()

    def formatter(data: dict[str, Any]) -> None:
        output_health_status(data)

    output_result(ctx, result, formatter)


@click.command(name="ready")
@click.pass_context
@handle_errors
def ready_cmd(ctx: click.Context) -> None:
    """Detailed readiness check.

    Examples:
        wps ready
        wps ready --json
    """
    config = load_config(ctx.obj.get("config_path") if ctx.obj else None)
    client = APIClient(config.api_url, config.timeout)
    result = client.ready()

    def formatter(data: dict[str, Any]) -> None:
        output_ready_status(data)

    output_result(ctx, result, formatter)
