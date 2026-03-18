"""Output formatting utilities for WPS CLI."""

from __future__ import annotations

import json
from typing import Any, Callable

import click
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

console = Console()


def output_json(data: Any) -> None:
    """Output as JSON."""
    click.echo(json.dumps(data, indent=2, default=str))


def output_table(headers: list[str], rows: list[list[Any]], title: str = "") -> None:
    """Output as formatted table."""
    table = Table(title=title if title else None)
    for h in headers:
        table.add_column(h, overflow="fold")
    for row in rows:
        table.add_row(*[str(c) for c in row])
    console.print(table)


def output_success(message: str) -> None:
    """Output success message."""
    console.print(f"[green]✓[/green] {message}")


def output_warning(message: str) -> None:
    """Output warning message."""
    console.print(f"[yellow]⚠[/yellow] {message}")


def output_error(message: str) -> None:
    """Output error message."""
    console.print(f"[red]✗[/red] {message}")


def output_info(label: str, value: Any) -> None:
    """Output labeled info line."""
    console.print(f"[bold]{label}:[/bold] {value}")


def output_panel(title: str, content: str, style: str = "blue") -> None:
    """Output content in a panel."""
    panel = Panel(content, title=title, border_style=style)
    console.print(panel)


def output_health_status(data: dict[str, Any]) -> None:
    """Output health check result."""
    ok = data.get("ok", False)
    if ok:
        output_success("Service is healthy")
    else:
        output_error("Service is unhealthy")


def output_ready_status(data: dict[str, Any]) -> None:
    """Output ready check result with detailed checks."""
    ok = data.get("ok", False)
    checks = data.get("checks", {})
    families = data.get("families", {})

    # Overall status
    if ok:
        output_panel("Service Status", "[green]✓ Ready[/green]", style="green")
    else:
        output_panel("Service Status", "[red]✗ Not Ready[/red]", style="red")

    # Checks table
    if checks:
        click.echo()
        headers = ["Check", "Status"]
        rows = []
        for name, status in checks.items():
            icon = "[green]✓[/green]" if status else "[red]✗[/red]"
            display_name = name.replace("Configured", "").replace("Writable", " writable")
            rows.append([display_name, icon])
        output_table(headers, rows, title="System Checks")

    # Families table
    if families:
        click.echo()
        headers = ["Document Family", "Status"]
        rows = [
            ["Word (.doc, .docx)", "[green]Enabled[/green]" if families.get("wordEnabled") else "[red]Disabled[/red]"],
            ["Excel (.xls, .xlsx)", "[green]Enabled[/green]" if families.get("excelEnabled") else "[red]Disabled[/red]"],
            ["PowerPoint (.ppt, .pptx)", "[green]Enabled[/green]" if families.get("pptEnabled") else "[red]Disabled[/red]"],
        ]
        output_table(headers, rows, title="Document Families")


def output_conversion_result(metadata: dict[str, Any], output_path: str) -> None:
    """Output conversion result."""
    output_success(f"Converted: {metadata['input_filename']}")
    output_info("Output", output_path)
    output_info("Size", f"{metadata['content_length']} bytes")


def output_batch_result(metadata: dict[str, Any], output_path: str) -> None:
    """Output batch conversion result."""
    output_success(f"Batch conversion complete")
    output_info("Files", metadata['input_count'])
    output_info("Output", output_path)
    output_info("Size", f"{metadata['content_length']} bytes")


def output_config(config: dict[str, Any]) -> None:
    """Output configuration as table."""
    headers = ["Setting", "Value"]
    rows = [[k, str(v)] for k, v in sorted(config.items())]
    output_table(headers, rows, title="Configuration")


def output_result(ctx: click.Context, data: Any, formatter: Callable[[Any], None]) -> None:
    """Route output based on context.

    Args:
        ctx: Click context containing json_output flag
        data: Data to output
        formatter: Function to format for human-readable output
    """
    if ctx.obj and ctx.obj.get("json_output"):
        output_json(data)
    else:
        formatter(data)
