#!/usr/bin/env python3
"""Main CLI entry point for the WPS CLI."""

from __future__ import annotations

from typing import Optional

import click

from cli_anything.wps import __version__
from cli_anything.wps.core.config import config_cmds
from cli_anything.wps.core.convert import convert_cmds, convert_cmd
from cli_anything.wps.core.health import health_cmd, ready_cmd
from cli_anything.wps.core.repl import repl_cmd


@click.group(
    name="wps",
    invoke_without_command=True,
)
@click.version_option(version=__version__, prog_name="wps")
@click.option(
    "--json",
    "json_output",
    is_flag=True,
    help="Output in JSON format",
)
@click.option(
    "--config",
    "config_path",
    type=click.Path(),
    help="Path to configuration file",
)
@click.pass_context
def cli(
    ctx: click.Context,
    json_output: bool,
    config_path: Optional[str],
) -> None:
    """CLI for WPS API - Office to PDF conversion.

    A command-line interface for the WPS API headless PDF conversion service.
    Supports converting Word, Excel, and PowerPoint documents to PDF.

    Quick Start:
        wps health                  # Check service health
        wps ready                   # Check service readiness
        wps convert doc.docx        # Convert a single document
        wps convert batch *.docx    # Convert multiple documents
        wps repl                    # Interactive mode

    For more help:
        wps <command> --help

    Documentation:
        https://github.com/Quantatirsk/wps-api
    """
    ctx.ensure_object(dict)
    ctx.obj["json_output"] = json_output
    ctx.obj["config_path"] = config_path

    # If no subcommand invoked, show help
    if ctx.invoked_subcommand is None:
        click.echo(ctx.get_help())


# Add command groups
cli.add_command(health_cmd)
cli.add_command(ready_cmd)
cli.add_command(convert_cmds)
cli.add_command(convert_cmd)
cli.add_command(config_cmds)
cli.add_command(repl_cmd)


if __name__ == "__main__":
    cli()
