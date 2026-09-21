"""Locate and download whisper.cpp (ggml) models."""

from __future__ import annotations

import os
import sys
import urllib.request
from pathlib import Path

from .models import WordcapsError

BASE_URL = "https://huggingface.co/ggerganov/whisper.cpp/resolve/main"

# name -> approximate download size, for the listing
KNOWN = {
    "tiny": "75 MB",
    "tiny.en": "75 MB",
    "base": "142 MB",
    "base.en": "142 MB",
    "small": "466 MB",
    "small.en": "466 MB",
    "medium": "1.5 GB",
    "large-v3-turbo": "1.6 GB",
    "large-v3": "2.9 GB",
}


def models_dir() -> Path:
    if env := os.environ.get("WORDCAPS_MODELS"):
        return Path(env).expanduser()
    base = os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache"
    return Path(base) / "wordcaps" / "models"


def model_path(name: str) -> Path:
    return models_dir() / f"ggml-{name}.bin"


def resolve(name_or_path: str) -> Path:
    """Accept a model name (``base``) or a path to a ``.bin`` file."""
    p = Path(name_or_path).expanduser()
    if p.suffix == ".bin" or os.sep in name_or_path:
        if not p.is_file():
            raise WordcapsError(f"model file not found: {p}")
        return p
    p = model_path(name_or_path)
    if not p.is_file():
        raise WordcapsError(
            f"whisper.cpp model '{name_or_path}' is not downloaded yet.\n"
            f"  wordcaps models download {name_or_path}"
        )
    return p


def installed() -> list[Path]:
    d = models_dir()
    return sorted(d.glob("ggml-*.bin")) if d.is_dir() else []


def download(name: str, *, force: bool = False, retries: int = 5) -> Path:
    if name not in KNOWN:
        raise WordcapsError(f"unknown model '{name}'. Known: {', '.join(KNOWN)}")
    dest = model_path(name)
    if dest.is_file() and not force:
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_suffix(".part")
    url = f"{BASE_URL}/ggml-{name}.bin"
    print(f"downloading {url} ({KNOWN[name]})", file=sys.stderr)
    error: Exception | None = None
    for _ in range(retries):
        try:
            if _fetch(url, part):
                part.replace(dest)
                return dest
        except OSError as e:  # includes URLError and dropped connections
            error = e
            print(f"\n  interrupted ({e}), resuming...", file=sys.stderr)
    raise WordcapsError(f"download failed: {error or 'incomplete file'}. "
                        "Run the same command again to resume.")


def _fetch(url: str, part: Path) -> bool:
    """Download into ``part``, resuming it if it exists. True when complete."""
    have = part.stat().st_size if part.exists() else 0
    req = urllib.request.Request(url, headers={"Range": f"bytes={have}-"} if have else {})
    with urllib.request.urlopen(req) as r:
        if have and r.status != 206:  # server ignored the range: start over
            have = 0
        total = have + int(r.headers.get("Content-Length") or 0)
        done = have
        with open(part, "ab" if have else "wb") as f:
            while chunk := r.read(1 << 20):
                f.write(chunk)
                done += len(chunk)
                if total:
                    print(f"\r  {done * 100 // total:3d}%", end="", file=sys.stderr, flush=True)
    print(file=sys.stderr)
    return total == 0 or done == total
