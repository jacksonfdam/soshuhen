"""Where dropped PDFs wait between the preview and the import.

api reads them to build the preview and worker-download reads them again to
write the library; reader-cache is the one volume both mount. An abandoned drop
is removed the next time anyone drops, so nothing needs a cron of its own.
"""

import json
import secrets
import shutil
import time
from pathlib import Path

from app.config import get_settings

_MAX_AGE_SECONDS = 24 * 3600
_MANIFEST = "manifest.json"


def _root() -> Path:
    return Path(get_settings().reader_cache_path) / "imports"


def _sweep(root: Path) -> None:
    cutoff = time.time() - _MAX_AGE_SECONDS
    for directory in root.iterdir():
        if directory.is_dir() and directory.stat().st_mtime < cutoff:
            shutil.rmtree(directory, ignore_errors=True)


def stage(files: list[tuple[str, str, bytes]]) -> str:
    """Keep (name, sha256, data) for a later import; returns the drop's token."""
    root = _root()
    root.mkdir(parents=True, exist_ok=True)
    _sweep(root)
    token = secrets.token_urlsafe(16)
    directory = root / token
    directory.mkdir()
    manifest: list[list[str]] = []
    for name, sha256, data in files:
        (directory / f"{sha256}.pdf").write_bytes(data)
        manifest.append([name, sha256])
    (directory / _MANIFEST).write_text(json.dumps(manifest))
    return token


def _directory(token: str) -> Path | None:
    # The token arrives in a URL; it must never walk out of the imports folder.
    if not token or "/" in token or "\\" in token or token.startswith("."):
        return None
    directory = _root() / token
    return directory if (directory / _MANIFEST).is_file() else None


def staged(token: str) -> list[tuple[str, str, bytes]] | None:
    directory = _directory(token)
    if directory is None:
        return None
    try:
        manifest = json.loads((directory / _MANIFEST).read_text())
        return [(name, sha256, (directory / f"{sha256}.pdf").read_bytes()) for name, sha256 in manifest]
    except (OSError, ValueError):
        return None


def discard(token: str) -> None:
    directory = _directory(token)
    if directory is not None:
        shutil.rmtree(directory, ignore_errors=True)
