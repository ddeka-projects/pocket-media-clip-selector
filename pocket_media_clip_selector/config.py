"""Validated app settings, independent of the launcher's working directory."""

from dataclasses import dataclass
from pathlib import Path

from .env import load_env
from .library import reject_link

REPOSITORY = Path(__file__).resolve().parents[1]
PREFIX = "POCKET_MEDIA_CLIP_SELECTOR_"


@dataclass(frozen=True)
class Settings:
    working_directory: Path
    host: str = "0.0.0.0"
    port: int = 8767


def load_settings(env_file=None, *, environ=None):
    values = load_env(
        Path(env_file) if env_file is not None else REPOSITORY / ".env", environ=environ
    )
    raw = values.get(PREFIX + "WORKING_DIRECTORY", "").strip()
    if not raw:
        raise ValueError(f"Set {PREFIX}WORKING_DIRECTORY to your existing media directory.")
    directory = Path(raw)
    if not directory.is_absolute() or not directory.is_dir():
        raise ValueError(
            f"{PREFIX}WORKING_DIRECTORY must be an absolute existing directory: {directory}"
        )
    for component in (*reversed(directory.parents), directory):
        reject_link(component)
    resolved = directory.resolve()
    if (
        resolved == REPOSITORY
        or REPOSITORY.is_relative_to(resolved)
        or resolved.is_relative_to(REPOSITORY)
    ):
        raise ValueError("Keep the repository and media working directory separate.")
    host = values.get(PREFIX + "HOST", "0.0.0.0").strip()
    if not host or any(character.isspace() for character in host):
        raise ValueError(f"{PREFIX}HOST must be a hostname or IP address.")
    try:
        port = int(values.get(PREFIX + "PORT", "8767"))
    except ValueError as error:
        raise ValueError(f"{PREFIX}PORT must be an integer between 1 and 65535.") from error
    if not 1 <= port <= 65535:
        raise ValueError(f"{PREFIX}PORT must be between 1 and 65535.")
    return Settings(resolved, host, port)
