"""Font lookup: bundled fonts, file paths, or system font names."""

from __future__ import annotations

import shutil
import subprocess
from functools import cache
from importlib import resources
from pathlib import Path

from PIL import ImageFont

from .models import WordcapsError

BUNDLED = {
    "montserrat-black": "Montserrat-Black.ttf",
    "montserrat-extrabold": "Montserrat-ExtraBold.ttf",
}


@cache
def font_file(spec: str) -> str:
    """Resolve a font spec to a file path.

    ``spec`` is a bundled font name, a path to a .ttf/.otf/.ttc file, or a
    system family name looked up with fontconfig (``fc-match``) when present.
    """
    if spec in BUNDLED:
        res = resources.files("wordcaps").joinpath("fonts", BUNDLED[spec])
        with resources.as_file(res) as p:
            return str(p)
    p = Path(spec).expanduser()
    if p.is_file():
        return str(p)
    if p.suffix.lower() in (".ttf", ".otf", ".ttc"):
        raise WordcapsError(f"font file not found: {p}")
    if shutil.which("fc-match"):
        res = subprocess.run(["fc-match", "-f", "%{file}", spec], capture_output=True, text=True)
        found = res.stdout.strip()
        if res.returncode == 0 and found and Path(found).is_file():
            return found
    raise WordcapsError(
        f"font '{spec}' not found. Use a bundled font ({', '.join(BUNDLED)}) "
        "or a path to a .ttf/.otf/.ttc file."
    )


@cache
def load_font(spec: str, size: int, index: int = 0) -> ImageFont.FreeTypeFont:
    try:
        return ImageFont.truetype(font_file(spec), max(1, size), index=index)
    except OSError as e:
        raise WordcapsError(f"cannot open font '{spec}' (index {index}): {e}") from e
