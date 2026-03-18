"""Configuration management commands for WPS CLI."""

from __future__ import annotations

from typing import Any

import click

from cli_anything.wps.core.state import (
    Config,
    load_config,
    resolve_config_path,
    save_config,
)
from cli_anything.wps.utils.errors import handle_errors
from cli_anything.wps.utils.output import output_config, output_result, output_success


@click.group(name="config")
def config_cmds() -> None:
    """Configuration management commands."""
    pass


@config_cmds.command(name="show")
@click.pass_context
@handle_errors
def config_show(ctx: click.Context) -> None:
    """Display current configuration.

    Shows merged configuration from file and environment variables.

    Examples:
        wps config show
        wps config show --json
    """
    config_path = ctx.obj.get("config_path") if ctx.obj else None
    config = load_config(config_path)
    config_source = resolve_config_path(config_path)

    result = config.to_dict()
    result["_config_source"] = str(config_source)

    def formatter(_: dict[str, Any]) -> None:
        output_config(config.to_dict())

    output_result(ctx, result, formatter)


@config_cmds.command(name="set")
@click.argument("key")
@click.argument("value")
@click.pass_context
@handle_errors
def config_set(ctx: click.Context, key: str, value: str) -> None:
    """Set a configuration value.

    Valid keys: api_url, timeout, default_output_dir

    Examples:
        wps config set api_url http://192.168.1.100:18000
        wps config set timeout 300
    """
    valid_keys = {"api_url", "timeout", "default_output_dir"}
    if key not in valid_keys:
        raise click.UsageError(f"Invalid key: {key}. Valid keys: {', '.join(valid_keys)}")

    config_path = ctx.obj.get("config_path") if ctx.obj else None
    config = load_config(config_path)

    # Update config
    if key == "timeout":
        try:
            setattr(config, key, int(value))
        except ValueError:
            raise click.UsageError(f"timeout must be an integer, got: {value}")
    else:
        setattr(config, key, value)

    # Save config
    save_config(config, config_path)

    result = {
        "success": True,
        "key": key,
        "value": value,
        "config_path": str(resolve_config_path(config_path)),
    }

    def formatter(_: dict[str, Any]) -> None:
        output_success(f"Set {key} = {value}")

    output_result(ctx, result, formatter)


@config_cmds.command(name="init")
@click.option(
    "--api-url",
    default="http://127.0.0.1:18000",
    help="WPS API base URL",
)
@click.option(
    "--timeout",
    default=120,
    type=int,
    help="Request timeout in seconds",
)
@click.pass_context
@handle_errors
def config_init(
    ctx: click.Context,
    api_url: str,
    timeout: int,
) -> None:
    """Initialize configuration file.

    Creates a new configuration file with the specified values.

    Examples:
        wps config init
        wps config init --api-url http://192.168.1.100:18000 --timeout 300
    """
    config_path = ctx.obj.get("config_path") if ctx.obj else None

    config = Config(
        api_url=api_url,
        timeout=timeout,
    )

    save_config(config, config_path)

    result = {
        "success": True,
        "config": config.to_dict(),
        "config_path": str(resolve_config_path(config_path)),
    }

    def formatter(_: dict[str, Any]) -> None:
        output_success("Configuration initialized")
        output_config(config.to_dict())

    output_result(ctx, result, formatter)
