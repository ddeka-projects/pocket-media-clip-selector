"""Small literal .env reader; Windows backslashes are never interpreted."""

from dataclasses import dataclass
import os
from pathlib import Path

REPOSITORY = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class Settings:
    working_dir: Path
    host: str = "0.0.0.0"
    port: int = 8767


def load_settings(env_file: Path = REPOSITORY / ".env") -> Settings:
    values = {}
    if env_file.exists():
        for number, line in enumerate(env_file.read_text(encoding="utf-8-sig").splitlines(), 1):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                raise ValueError(f"Invalid .env line {number}; expected NAME=value.")
            key, value = line.split("=", 1)
            value = value.strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
                value = value[1:-1]
            values[key.strip()] = value
    values.update({key: os.environ[key] for key in ("WORKING_DIR", "HOST", "PORT") if key in os.environ})
    raw = values.get("WORKING_DIR", "")
    if not raw:
        raise ValueError("Set WORKING_DIR in .env to your existing media directory.")
    working_dir = Path(raw)
    if not working_dir.is_absolute():
        raise ValueError("WORKING_DIR must be an absolute path, such as D:\\MediaProjects.")
    if not working_dir.is_dir():
        raise ValueError(f"WORKING_DIR does not exist or is not readable: {working_dir}")
    resolved = working_dir.resolve()
    if resolved == REPOSITORY or REPOSITORY.is_relative_to(resolved) or resolved.is_relative_to(REPOSITORY):
        raise ValueError("Keep the repository and WORKING_DIR in separate directories.")
    host = values.get("HOST", "0.0.0.0").strip()
    if not host:
        raise ValueError("HOST cannot be empty.")
    try:
        port = int(values.get("PORT", "8767"))
    except ValueError as error:
        raise ValueError("PORT must be an integer between 1 and 65535.") from error
    if not 1 <= port <= 65535:
        raise ValueError("PORT must be between 1 and 65535.")
    return Settings(working_dir, host, port)
