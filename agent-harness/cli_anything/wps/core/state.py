"""State persistence for WPS CLI."""

from __future__ import annotations

import json
import os
import shutil
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Optional

from cli_anything.wps.utils.errors import CLIError

# State directory in user's home
STATE_DIR = Path.home() / ".config" / "wps"
LEGACY_STATE_DIR = Path.home() / ".config" / "cli-anything-wps"
DEFAULT_CONFIG_PATH = STATE_DIR / "config.json"
LEGACY_CONFIG_PATH = LEGACY_STATE_DIR / "config.json"


def ensure_state_dir() -> None:
    """Create the new state directory and migrate legacy state when present."""
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    if not LEGACY_STATE_DIR.exists():
        return

    legacy_files = [
        LEGACY_CONFIG_PATH,
        LEGACY_STATE_DIR / "default_session",
        *LEGACY_STATE_DIR.glob("session_*.json"),
    ]
    for legacy_path in legacy_files:
        if not legacy_path.exists():
            continue
        target_path = STATE_DIR / legacy_path.name
        if target_path.exists():
            continue
        try:
            shutil.copy2(legacy_path, target_path)
        except OSError as exc:
            raise CLIError(
                f"Failed to migrate legacy state from {legacy_path} to {target_path}: {exc}",
                code="CONFIG_ERROR",
            ) from exc


def resolve_config_path(config_path: Optional[str] = None) -> Path:
    """Resolve the config path, preferring the new location and falling back to legacy."""
    if config_path:
        return Path(config_path).expanduser()

    ensure_state_dir()
    if DEFAULT_CONFIG_PATH.exists():
        return DEFAULT_CONFIG_PATH
    if LEGACY_CONFIG_PATH.exists():
        return LEGACY_CONFIG_PATH
    return DEFAULT_CONFIG_PATH


@dataclass
class Config:
    """CLI configuration."""

    api_url: str = "http://127.0.0.1:18000"
    timeout: int = 120
    default_output_dir: str = "."

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Config":
        """Create Config from dictionary."""
        return cls(
            api_url=data.get("api_url", cls.api_url),
            timeout=data.get("timeout", cls.timeout),
            default_output_dir=data.get("default_output_dir", cls.default_output_dir),
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert Config to dictionary."""
        return asdict(self)


@dataclass
class SessionState:
    """Session state for tracking operations."""

    session_id: str
    api_url: str
    last_command: Optional[str] = None
    last_result: Optional[dict[str, Any]] = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def save(self) -> None:
        """Save session state to disk."""
        ensure_state_dir()
        path = STATE_DIR / f"session_{self.session_id}.json"
        with open(path, "w") as f:
            json.dump(asdict(self), f, indent=2)

    @classmethod
    def load(cls, session_id: str) -> Optional["SessionState"]:
        """Load session state from disk."""
        path = STATE_DIR / f"session_{session_id}.json"
        if not path.exists():
            return None
        with open(path) as f:
            return cls(**json.load(f))


def load_config(config_path: Optional[str] = None) -> Config:
    """Load configuration from file.

    Args:
        config_path: Optional path to config file. If not provided,
                    uses default location or environment variables.

    Returns:
        Config object with merged values (env vars override file)
    """
    # Start with defaults
    config = Config()

    # Load from file if exists
    path = resolve_config_path(config_path)
    if path.exists():
        try:
            with open(path) as f:
                file_data = json.load(f)
                config = Config.from_dict(file_data)
        except (json.JSONDecodeError, IOError) as e:
            raise CLIError(f"Failed to load config: {e}", code="CONFIG_ERROR")

    # Environment variables override file
    env_api_url = os.getenv("WPS_API_URL")
    if env_api_url:
        config.api_url = env_api_url
    env_timeout = os.getenv("WPS_TIMEOUT")
    if env_timeout:
        try:
            config.timeout = int(env_timeout)
        except ValueError:
            pass

    return config


def save_config(config: Config, config_path: Optional[str] = None) -> None:
    """Save configuration to file.

    Args:
        config: Config object to save
        config_path: Optional path to config file. If not provided,
                    uses default location.
    """
    path = resolve_config_path(config_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    try:
        with open(path, "w") as f:
            json.dump(config.to_dict(), f, indent=2)
    except IOError as e:
        raise CLIError(f"Failed to save config: {e}", code="CONFIG_ERROR")


def get_default_session_id() -> str:
    """Get or create default session ID."""
    ensure_state_dir()
    session_file = STATE_DIR / "default_session"
    if session_file.exists():
        return session_file.read_text().strip()

    import uuid

    session_id = uuid.uuid4().hex[:8]
    session_file.write_text(session_id)
    return session_id
