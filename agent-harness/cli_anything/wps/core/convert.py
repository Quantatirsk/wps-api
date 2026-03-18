"""Document conversion commands for WPS CLI."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import click

from cli_anything.wps.core.state import load_config
from cli_anything.wps.utils.errors import handle_errors
from cli_anything.wps.utils.http_client import APIClient
from cli_anything.wps.utils.output import (
    output_batch_result,
    output_conversion_result,
    output_result,
)


@click.group(name="convert")
def convert_cmds() -> None:
    """Document conversion commands."""
    pass


@convert_cmds.command(name="single")
@click.argument("input_file", type=click.Path(exists=True, readable=True))
@click.option(
    "--output",
    "-o",
    type=click.Path(),
    help="Output path (default: <input>.pdf in same directory)",
)
@click.option(
    "--format",
    "output_format",
    default="pdf",
    type=click.Choice(["pdf"], case_sensitive=False),
    help="Output format (only pdf supported)",
)
@click.pass_context
@handle_errors
def convert_single(
    ctx: click.Context,
    input_file: str,
    output: str | None,
    output_format: str,
) -> None:
    """Convert a single document to PDF.

    Supported formats: .doc, .docx, .ppt, .pptx, .xls, .xlsx

    Examples:
        wps convert single document.docx
        wps convert single document.docx --output /path/to/output.pdf
        wps convert single document.docx --json
    """
    config = load_config(ctx.obj.get("config_path") if ctx.obj else None)
    client = APIClient(config.api_url, config.timeout)

    # Determine output path
    input_path = Path(input_file)
    if output:
        output_path = Path(output)
    else:
        output_path = input_path.with_suffix(".pdf")

    # Perform conversion
    pdf_bytes, metadata = client.convert_single(input_file)

    # Write output
    output_path.write_bytes(pdf_bytes)

    # Prepare result data
    result = {
        "success": True,
        "input_file": str(input_path.absolute()),
        "output_file": str(output_path.absolute()),
        "output_format": output_format,
        **metadata,
    }

    def formatter(_: dict[str, Any]) -> None:
        output_conversion_result(metadata, str(output_path.absolute()))

    output_result(ctx, result, formatter)


@convert_cmds.command(name="batch")
@click.argument("input_files", nargs=-1, required=True, type=click.Path(exists=True))
@click.option(
    "--output",
    "-o",
    type=click.Path(),
    help="Output ZIP path (default: batch_<timestamp>.zip)",
)
@click.pass_context
@handle_errors
def convert_batch(
    ctx: click.Context,
    input_files: tuple[str, ...],
    output: str | None,
) -> None:
    """Convert multiple documents to PDF ZIP archive.

    Supports mixed document types. Each file is converted to PDF
    and packaged into a ZIP archive with a manifest.

    Examples:
        wps convert batch *.docx
        wps convert batch file1.docx file2.pptx --output output.zip
    """
    config = load_config(ctx.obj.get("config_path") if ctx.obj else None)
    client = APIClient(config.api_url, config.timeout)

    if not input_files:
        raise click.UsageError("At least one input file is required")

    # Determine output path
    if output:
        output_path = Path(output)
    else:
        from datetime import datetime

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = Path(f"batch_{timestamp}.zip")

    # Perform batch conversion
    zip_bytes, metadata = client.convert_batch(list(input_files))

    # Write output
    output_path.write_bytes(zip_bytes)

    # Prepare result data
    result = {
        "success": True,
        "input_files": [str(Path(f).absolute()) for f in input_files],
        "output_file": str(output_path.absolute()),
        **metadata,
    }

    def formatter(_: dict[str, Any]) -> None:
        output_batch_result(metadata, str(output_path.absolute()))

    output_result(ctx, result, formatter)


# Convenience direct commands


@click.command(name="convert")
@click.argument("input_file", type=click.Path(exists=True))
@click.option(
    "--output",
    "-o",
    type=click.Path(),
    help="Output path (default: <input>.pdf)",
)
@click.pass_context
@handle_errors
def convert_cmd(
    ctx: click.Context,
    input_file: str,
    output: str | None,
) -> None:
    """Convert a document to PDF (shortcut for 'convert single').

    Examples:
        wps convert document.docx
        wps convert document.docx -o /path/to/output.pdf
    """
    # Delegate to convert_single
    ctx.invoke(convert_single, input_file=input_file, output=output, output_format="pdf")
