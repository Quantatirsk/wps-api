# cli-anything Harness Methodology

This document defines the complete methodology, architecture standards, and implementation patterns for building production-ready CLI harnesses for any GUI application.

## Overview

The cli-anything harness transforms GUI applications into scriptable, automatable CLI tools while preserving all original functionality. The harness provides:

- **Command-line interface** matching the app's domain model
- **Stateful sessions** for multi-step workflows
- **REPL mode** for interactive use
- **JSON output** for agent/programmatic consumption
- **Complete test coverage** with unit and E2E tests

## Architecture Principles

### 1. Domain-Driven Command Groups

Commands are organized by domain (e.g., `convert`, `health`, `config`) rather than by implementation detail. Each command group reflects a distinct functional area of the application.

### 2. State Management

The harness maintains state through:
- **Session files**: JSON files storing the current operational context
- **Project files**: Named collections of related operations
- **Configuration**: Environment-aware defaults and user overrides

### 3. Output Modes

All commands support two output modes:
- **Human-readable** (default): Formatted tables, colors, progress indicators
- **JSON** (`--json`): Machine-parseable output for scripting and agents

### 4. Error Handling

- Use exit codes: 0 (success), 1 (general error), 2 (usage error), 3 (state error)
- JSON errors include structured error objects with `error`, `code`, and `details` fields
- Human errors show clear messages with suggested fixes

## Directory Structure

```
agent-harness/
├── <SOFTWARE>.md              # Software-specific SOP
├── setup.py                   # PyPI package config
└── cli_anything/              # Namespace package (NO __init__.py)
    └── <software>/            # Sub-package (HAS __init__.py)
        ├── README.md          # Installation and usage guide
        ├── <software>_cli.py  # Main CLI entry point
        ├── core/              # Core modules
        │   ├── __init__.py
        │   ├── project.py     # Project state management
        │   ├── session.py     # Session lifecycle
        │   ├── convert.py     # Domain-specific operations
        │   ├── health.py      # Health/ready checks
        │   ├── config.py      # Configuration management
        │   └── state.py       # State persistence
        ├── utils/             # Utilities
        │   ├── __init__.py
        │   ├── output.py      # Output formatting (table/json)
        │   ├── errors.py      # Error definitions
        │   └── http_client.py # API client
        └── tests/
            ├── TEST.md        # Test plan and results
            ├── test_core.py   # Unit tests
            └── test_full_e2e.py # E2E tests
```

## Implementation Standards

### Package Structure (PEP 420 Namespace)

```python
# setup.py
from setuptools import setup, find_namespace_packages

setup(
    name="<software>",
    version="1.0.0",
    packages=find_namespace_packages(include=["cli_anything.*"]),
    entry_points={
        "console_scripts": [
            "<software>=cli_anything.<software>.<software>_cli:cli",
        ],
    },
)
```

```
cli_anything/                  # NO __init__.py (namespace root)
└── <software>/                # HAS __init__.py (sub-package)
    ├── __init__.py
    └── ...
```

### CLI Framework (Click)

```python
# <software>_cli.py
import click
from typing import Optional

@click.group()
@click.option("--json", "json_output", is_flag=True, help="Output in JSON format")
@click.option("--config", type=click.Path(), help="Path to config file")
@click.pass_context
def cli(ctx: click.Context, json_output: bool, config: Optional[str]) -> None:
    """CLI for <Software> - description here."""
    ctx.ensure_object(dict)
    ctx.obj["json_output"] = json_output
    ctx.obj["config_path"] = config

@cli.command()
@click.pass_context
def repl(ctx: click.Context) -> None:
    """Start interactive REPL mode."""
    # REPL implementation

# Add command groups
cli.add_command(convert_cmds)
cli.add_command(health_cmds)
cli.add_command(config_cmds)
```

### Command Group Pattern

```python
# core/convert.py
import click
from typing import Any

@click.group(name="convert")
def convert_cmds() -> None:
    """Document conversion commands."""
    pass

@convert_cmds.command(name="single")
@click.argument("input_file", type=click.Path(exists=True))
@click.option("--output", "-o", type=click.Path(), help="Output path")
@click.option("--format", "output_format", default="pdf", help="Output format")
@click.pass_context
def convert_single(ctx: click.Context, input_file: str, output: str, output_format: str) -> None:
    """Convert a single document."""
    result = perform_conversion(input_file, output, output_format)
    if ctx.obj.get("json_output"):
        click.echo(json.dumps(result, indent=2))
    else:
        display_result_table(result)
```

### State Persistence

```python
# core/state.py
import json
from pathlib import Path
from dataclasses import dataclass, asdict
from typing import Optional, Any

STATE_DIR = Path.home() / ".config" / "<software>"

@dataclass
class SessionState:
    session_id: str
    api_url: str
    current_project: Optional[str] = None
    last_operation: Optional[dict] = None
    metadata: dict = None

    def save(self) -> None:
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        path = STATE_DIR / f"session_{self.session_id}.json"
        with open(path, "w") as f:
            json.dump(asdict(self), f, indent=2)

    @classmethod
    def load(cls, session_id: str) -> Optional["SessionState"]:
        path = STATE_DIR / f"session_{session_id}.json"
        if not path.exists():
            return None
        with open(path) as f:
            return cls(**json.load(f))
```

### HTTP Client

```python
# utils/http_client.py
import requests
from typing import Any, Optional
import json

class APIClient:
    def __init__(self, base_url: str, timeout: int = 120):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.session = requests.Session()

    def health(self) -> dict:
        """Check service health."""
        resp = self.session.get(f"{self.base_url}/api/v1/healthz", timeout=5)
        resp.raise_for_status()
        return resp.json()

    def ready(self) -> dict:
        """Check service readiness."""
        resp = self.session.get(f"{self.base_url}/api/v1/readyz", timeout=5)
        resp.raise_for_status()
        return resp.json()

    def convert_single(self, file_path: str) -> bytes:
        """Convert single file to PDF."""
        with open(file_path, "rb") as f:
            files = {"file": f}
            resp = self.session.post(
                f"{self.base_url}/api/v1/convert-to-pdf",
                files=files,
                timeout=self.timeout
            )
        resp.raise_for_status()
        return resp.content

    def convert_batch(self, file_paths: list[str]) -> bytes:
        """Convert multiple files to PDF ZIP."""
        files = [("files", open(fp, "rb")) for fp in file_paths]
        try:
            resp = self.session.post(
                f"{self.base_url}/api/v1/convert-to-pdf/batch",
                files=files,
                timeout=self.timeout * len(file_paths)
            )
            resp.raise_for_status()
            return resp.content
        finally:
            for _, f in files:
                f.close()
```

### Output Formatting

```python
# utils/output.py
import json
from typing import Any
from rich.table import Table
from rich.console import Console

console = Console()

def output_json(data: Any) -> None:
    """Output as JSON."""
    click.echo(json.dumps(data, indent=2, default=str))

def output_table(headers: list[str], rows: list[list[Any]], title: str = "") -> None:
    """Output as formatted table."""
    table = Table(title=title)
    for h in headers:
        table.add_column(h)
    for row in rows:
        table.add_row(*[str(c) for c in row])
    console.print(table)

def output_result(ctx: click.Context, data: Any, formatter: callable) -> None:
    """Route output based on context."""
    if ctx.obj.get("json_output"):
        output_json(data)
    else:
        formatter(data)
```

### Error Handling

```python
# utils/errors.py
import click
from typing import Optional
import json
import sys

class CLIError(Exception):
    """Base CLI error with structured output."""
    def __init__(self, message: str, code: str = "ERROR", details: Optional[dict] = None):
        self.message = message
        self.code = code
        self.details = details or {}
        super().__init__(message)

    def to_json(self) -> dict:
        return {
            "error": self.message,
            "code": self.code,
            "details": self.details
        }

    def show(self, json_output: bool = False) -> None:
        if json_output:
            click.echo(json.dumps(self.to_json(), indent=2), err=True)
        else:
            click.echo(f"Error [{self.code}]: {self.message}", err=True)
        sys.exit(1)

def handle_errors(func):
    """Decorator for consistent error handling."""
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except CLIError as e:
            ctx = click.get_current_context()
            e.show(ctx.obj.get("json_output", False))
        except Exception as e:
            err = CLIError(str(e), code="UNEXPECTED")
            ctx = click.get_current_context()
            err.show(ctx.obj.get("json_output", False))
    return wrapper
```

### REPL Mode

```python
# core/repl.py
import cmd
import shlex
from typing import Any

class ReplShell(cmd.Cmd):
    intro = """
╔═══════════════════════════════════════════════════════════╗
║  <software> REPL                                          ║
║  Type 'help' for commands, 'exit' to quit                ║
╚═══════════════════════════════════════════════════════════╝
"""
    prompt = "wps> "

    def __init__(self, ctx_obj: dict):
        super().__init__()
        self.ctx_obj = ctx_obj

    def do_convert(self, arg: str) -> None:
        """Convert document: convert <file> [--output <path>]"""
        args = shlex.split(arg)
        # Dispatch to convert command

    def do_health(self, arg: str) -> None:
        """Check service health."""
        # Dispatch to health command

    def do_exit(self, arg: str) -> bool:
        """Exit the REPL."""
        click.echo("Goodbye!")
        return True

    def do_EOF(self, arg: str) -> bool:
        """Handle Ctrl+D."""
        return self.do_exit(arg)

    def default(self, line: str) -> None:
        click.echo(f"Unknown command: {line}")
        click.echo("Type 'help' for available commands")
```

## Testing Standards

### Test Structure

```
tests/
├── TEST.md              # Test plan and results
├── test_core.py         # Unit tests (synthetic data)
└── test_full_e2e.py     # E2E tests (real files)
```

### Unit Test Pattern

```python
# tests/test_core.py
import pytest
from unittest.mock import Mock, patch
from cli_anything.<software>.core.convert import perform_conversion
from cli_anything.<software>.utils.errors import CLIError

class TestConvertUnit:
    """Unit tests with mocked dependencies."""

    @patch("cli_anything.<software>.core.convert.APIClient")
    def test_convert_single_success(self, mock_client_class):
        mock_client = Mock()
        mock_client.convert_single.return_value = b"PDF content"
        mock_client_class.return_value = mock_client

        result = perform_conversion("test.docx", "out.pdf", "pdf")

        assert result["success"] is True
        assert result["output_path"] == "out.pdf"

    @patch("cli_anything.<software>.core.convert.APIClient")
    def test_convert_unsupported_format(self, mock_client_class):
        with pytest.raises(CLIError) as exc_info:
            perform_conversion("test.xyz", "out.pdf", "pdf")
        assert "unsupported" in str(exc_info.value).lower()
```

### E2E Test Pattern

```python
# tests/test_full_e2e.py
import pytest
import subprocess
import tempfile
from pathlib import Path

class TestCLISubprocess:
    """Tests via subprocess with installed CLI."""

    def _resolve_cli(self, cmd_name: str = "<software>") -> str:
        """Resolve CLI command, respecting override for testing."""
        import os
        if os.getenv("CLI_ANYTHING_FORCE_INSTALLED"):
            return cmd_name
        # Find in PATH
        result = subprocess.run(
            ["which", cmd_name],
            capture_output=True,
            text=True
        )
        if result.returncode == 0:
            return result.stdout.strip()
        raise RuntimeError(f"CLI not found: {cmd_name}")

    def test_help_command(self):
        cli = self._resolve_cli()
        result = subprocess.run(
            [cli, "--help"],
            capture_output=True,
            text=True
        )
        assert result.returncode == 0
        assert "Usage:" in result.stdout

    def test_convert_single_e2e(self):
        cli = self._resolve_cli()
        with tempfile.NamedTemporaryFile(suffix=".docx", delete=False) as f:
            # Create minimal docx...
            f.write(b"...")
            input_path = f.name

        result = subprocess.run(
            [cli, "convert", "single", input_path, "--output", "/tmp/out.pdf"],
            capture_output=True,
            text=True
        )
        assert result.returncode == 0
```

### Test Documentation (TEST.md)

```markdown
# Test Plan

## Unit Tests (test_core.py)

| Test | Description | Status |
|------|-------------|--------|
| test_convert_single_success | Mocked single file conversion | PASS |
| test_convert_batch_success | Mocked batch conversion | PASS |
| test_health_check | Mocked health endpoint | PASS |
| test_error_handling | Error propagation | PASS |

## E2E Tests (test_full_e2e.py)

| Test | Description | Status |
|------|-------------|--------|
| test_help_command | CLI --help works | PASS |
| test_convert_docx | Real docx -> pdf conversion | PASS |
| test_convert_batch | Real batch conversion | PASS |
| test_json_output | --json flag works | PASS |

## Test Results

```bash
$ pytest -v --tb=no
============================= test session starts ==============================
tests/test_core.py::TestConvertUnit::test_convert_single_success PASSED
tests/test_core.py::TestConvertUnit::test_convert_batch_success PASSED
tests/test_full_e2e.py::TestCLISubprocess::test_help_command PASSED
tests/test_full_e2e.py::TestCLISubprocess::test_convert_docx PASSED
============================= 10 passed in 5.2s ================================
```
```

## Build and Release

### Local Installation

```bash
# Development install
pip install -e .

# Verify CLI is in PATH
which <software>

# Test
<software> --help
```

### PyPI Publishing

```bash
# Build
python -m build

# Upload
python -m twine upload dist/*
```

## Phase Summary

| Phase | Description | Output |
|-------|-------------|--------|
| 0 | Source acquisition | Local source verified |
| 1 | Codebase analysis | Architecture documented |
| 2 | CLI architecture design | <SOFTWARE>.md SOP |
| 3 | Implementation | Core modules + CLI |
| 4 | Test planning | TEST.md plan |
| 5 | Test implementation | All tests passing |
| 6 | Test documentation | Results in TEST.md |
| 7 | PyPI publishing | Package installable |

## Success Criteria

The harness is complete when:

1. All core modules implemented and functional
2. CLI supports one-shot commands and REPL mode
3. `--json` output mode works for all commands
4. All tests pass (100% pass rate)
5. Subprocess tests use `_resolve_cli()` and pass
6. TEST.md contains plan and results
7. README.md documents installation and usage
8. Local installation works: `pip install -e .`
9. CLI available in PATH: `which <software>`
