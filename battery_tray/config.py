import os
import tomllib
from dataclasses import dataclass, fields
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    poll_interval_seconds: int = 60
    low_battery_percent: int = 15  # desktop notification
    warning_percent: int = 20  # red, blinks every 10 minutes
    critical_percent: int = 10  # red, blinks every minute


def default_path() -> Path:
    base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return base / "battery-tray" / "config.toml"


def load(path: Path | None = None) -> Settings:
    """Read the optional TOML config; every missing key keeps its default."""
    path = path or default_path()
    try:
        data = tomllib.loads(path.read_text())
    except FileNotFoundError:
        return Settings()
    known = {field.name for field in fields(Settings)}
    return Settings(**{key: int(value) for key, value in data.items() if key in known})
