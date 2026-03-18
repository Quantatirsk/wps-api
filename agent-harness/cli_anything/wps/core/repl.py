"""REPL mode for WPS CLI."""

from __future__ import annotations

import cmd
import shlex
import sys
from typing import Any

import click
from rich.console import Console

from cli_anything.wps.core.state import load_config
from cli_anything.wps.utils.http_client import APIClient
from cli_anything.wps.utils.output import output_ready_status

console = Console()


class ReplShell(cmd.Cmd):
    """Interactive REPL shell for WPS CLI."""

    intro = """
╔═══════════════════════════════════════════════════════════╗
║  WPS CLI - Interactive Mode                               ║
║  Type 'help' for commands, 'exit' to quit                ║
╚═══════════════════════════════════════════════════════════╝
"""
    prompt = "wps> "

    def __init__(self, ctx_obj: dict[str, Any]):
        super().__init__()
        self.ctx_obj = ctx_obj
        self.config = load_config(ctx_obj.get("config_path"))
        self.client: APIClient | None = None

    def preloop(self) -> None:
        """Initialize before starting the loop."""
        try:
            self.client = APIClient(self.config.api_url, self.config.timeout)
            console.print(f"[dim]Connected to: {self.config.api_url}[/dim]")
        except Exception as e:
            console.print(f"[yellow]Warning: Could not connect to {self.config.api_url}: {e}[/yellow]")

    def do_health(self, _arg: str) -> None:
        """Check service health: health"""
        if not self.client:
            console.print("[red]Not connected to service[/red]")
            return
        try:
            result = self.client.health()
            if result.get("ok"):
                console.print("[green]✓ Service is healthy[/green]")
            else:
                console.print("[red]✗ Service is unhealthy[/red]")
        except Exception as e:
            console.print(f"[red]Error: {e}[/red]")

    def do_ready(self, _arg: str) -> None:
        """Check service readiness: ready"""
        if not self.client:
            console.print("[red]Not connected to service[/red]")
            return
        try:
            result = self.client.ready()
            output_ready_status(result)
        except Exception as e:
            console.print(f"[red]Error: {e}[/red]")

    def do_convert(self, arg: str) -> None:
        """Convert document(s): convert <file> [--output <path>]"""
        if not self.client:
            console.print("[red]Not connected to service[/red]")
            return

        args = shlex.split(arg)
        if not args:
            console.print("[red]Error: No file specified[/red]")
            console.print("Usage: convert <file> [--output <path>]")
            return

        input_file = args[0]
        output_path = None

        # Parse optional --output
        if "--output" in args:
            try:
                idx = args.index("--output")
                output_path = args[idx + 1]
            except IndexError:
                console.print("[red]Error: --output requires a path[/red]")
                return

        from pathlib import Path

        path = Path(input_file)
        if not path.exists():
            console.print(f"[red]Error: File not found: {input_file}[/red]")
            return

        if not output_path:
            output_path = str(path.with_suffix(".pdf"))

        try:
            console.print(f"[dim]Converting {path.name}...[/dim]")
            pdf_bytes, metadata = self.client.convert_single(input_file)
            Path(output_path).write_bytes(pdf_bytes)
            console.print(f"[green]✓ Converted: {path.name} -> {output_path}[/green]")
            console.print(f"[dim]  Size: {metadata['content_length']} bytes[/dim]")
        except Exception as e:
            console.print(f"[red]Error: {e}[/red]")

    def do_batch(self, arg: str) -> None:
        """Batch convert documents: batch <file1> [file2 ...] [--output <path>]"""
        if not self.client:
            console.print("[red]Not connected to service[/red]")
            return

        args = shlex.split(arg)
        if not args:
            console.print("[red]Error: No files specified[/red]")
            console.print("Usage: batch <file1> [file2 ...] [--output <path>]")
            return

        # Separate files from options
        files = []
        output_path = None
        i = 0
        while i < len(args):
            if args[i] == "--output":
                if i + 1 < len(args):
                    output_path = args[i + 1]
                    i += 2
                else:
                    console.print("[red]Error: --output requires a path[/red]")
                    return
            else:
                files.append(args[i])
                i += 1

        from pathlib import Path
        from datetime import datetime

        if not output_path:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_path = f"batch_{timestamp}.zip"

        # Check all files exist
        for f in files:
            if not Path(f).exists():
                console.print(f"[red]Error: File not found: {f}[/red]")
                return

        try:
            console.print(f"[dim]Converting {len(files)} files...[/dim]")
            zip_bytes, metadata = self.client.convert_batch(files)
            Path(output_path).write_bytes(zip_bytes)
            console.print(f"[green]✓ Batch complete: {output_path}[/green]")
            console.print(f"[dim]  Files: {metadata['input_count']}, Size: {metadata['content_length']} bytes[/dim]")
        except Exception as e:
            console.print(f"[red]Error: {e}[/red]")

    def do_config(self, _arg: str) -> None:
        """Show configuration: config"""
        output_ready_status({
            "ok": True,
            "checks": {},
            "config": {
                "api_url": self.config.api_url,
                "timeout": self.config.timeout,
                "default_output_dir": self.config.default_output_dir,
            }
        })

    def do_help(self, arg: str) -> None:
        """Show help: help [command]"""
        if arg:
            # Show help for specific command
            cmd = arg.strip()
            if hasattr(self, f"do_{cmd}"):
                func = getattr(self, f"do_{cmd}")
                doc = func.__doc__ or "No help available"
                console.print(f"[bold]{cmd}[/bold]: {doc}")
            else:
                console.print(f"[red]Unknown command: {cmd}[/red]")
        else:
            # Show general help
            console.print("\n[bold]Available Commands:[/bold]\n")
            commands = [
                ("health", "Check service health"),
                ("ready", "Check service readiness"),
                ("convert <file>", "Convert a single document"),
                ("batch <files...>", "Convert multiple documents"),
                ("config", "Show configuration"),
                ("exit", "Exit REPL"),
                ("help [cmd]", "Show help"),
            ]
            for cmd, desc in commands:
                console.print(f"  [cyan]{cmd:<20}[/cyan] {desc}")
            console.print()

    def do_exit(self, _arg: str) -> bool:
        """Exit the REPL: exit"""
        console.print("Goodbye!")
        return True

    def do_quit(self, _arg: str) -> bool:
        """Exit the REPL: quit"""
        return self.do_exit("")

    def do_EOF(self, _arg: str) -> bool:
        """Handle Ctrl+D"""
        console.print()
        return self.do_exit("")

    def default(self, line: str) -> None:
        """Handle unknown commands."""
        console.print(f"[red]Unknown command: {line}[/red]")
        console.print("Type 'help' for available commands")


@click.command(name="repl")
@click.pass_context
def repl_cmd(ctx: click.Context) -> None:
    """Start interactive REPL mode.

    Provides an interactive shell for executing commands
    without retyping the 'wps' prefix each time.

    Examples:
        wps repl
    """
    shell = ReplShell(ctx.obj if ctx.obj else {})
    try:
        shell.cmdloop()
    except KeyboardInterrupt:
        console.print("\nGoodbye!")
        sys.exit(0)
