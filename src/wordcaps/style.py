"""Caption styles: built-in presets and user TOML files.

Sizes and positions are relative to the video, so one style works at any
resolution and aspect ratio:

* ``size``, ``max_width``: fractions of the video **width**
* ``baseline``: fraction of the video **height**, where the last line sits
* ``stroke``, ``shadow_offset``: fractions of the font size
* ``line_spacing``: multiple of the font size
"""

from __future__ import annotations

import tomllib
from dataclasses import asdict, dataclass, field, fields
from importlib import resources
from pathlib import Path

from .models import WordcapsError

RGB = tuple[int, int, int]
HIGHLIGHT_MODES = ("color", "box", "pop")


def parse_color(value) -> RGB:
    if isinstance(value, str):
        h = value.lstrip("#")
        if len(h) == 3:
            h = "".join(c * 2 for c in h)
        if len(h) != 6:
            raise WordcapsError(f"bad color {value!r}, use #RRGGBB")
        try:
            return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]
        except ValueError as e:
            raise WordcapsError(f"bad color {value!r}, use #RRGGBB") from e
    if isinstance(value, list | tuple) and len(value) == 3:
        return tuple(int(v) for v in value)  # type: ignore[return-value]
    raise WordcapsError(f"bad color {value!r}, use #RRGGBB")


@dataclass
class Style:
    name: str = "custom"
    description: str = ""

    # type
    font: str = "montserrat-black"
    font_index: int = 0
    size: float = 0.058
    uppercase: bool = True
    strip_punctuation: bool = True

    # colors
    color: RGB = (255, 255, 255)
    highlight: RGB = (255, 221, 0)
    highlight_mode: str = "color"
    box_text_color: RGB = (0, 0, 0)
    stroke: float = 0.14
    stroke_color: RGB = (0, 0, 0)
    shadow: bool = True
    shadow_offset: float = 0.12
    shadow_opacity: float = 0.6
    shadow_blur: float = 0.0

    # layout
    baseline: float = 0.70
    line_spacing: float = 1.25
    max_width: float = 0.80

    # grouping
    max_words: int = 3
    max_chars: int = 22
    max_pause: float = 0.35

    # motion
    fade_in: float = 0.10
    pop_scale: float = 1.15
    emphasis: list[str] = field(default_factory=list)
    emphasis_scale: float = 1.25

    def validate(self) -> Style:
        if self.highlight_mode not in HIGHLIGHT_MODES:
            raise WordcapsError(
                f"highlight_mode must be one of {', '.join(HIGHLIGHT_MODES)}, "
                f"got {self.highlight_mode!r}"
            )
        for name in ("size", "max_width", "baseline"):
            v = getattr(self, name)
            if not 0 < v <= 1:
                raise WordcapsError(f"{name} is a fraction of the video, got {v}")
        if self.max_words < 1 or self.max_chars < 1:
            raise WordcapsError("max_words and max_chars must be at least 1")
        return self

    def to_toml(self) -> str:
        lines = []
        for k, v in asdict(self).items():
            if isinstance(v, tuple):
                v = "#{:02X}{:02X}{:02X}".format(*v)
            if isinstance(v, bool):
                lines.append(f"{k} = {str(v).lower()}")
            elif isinstance(v, str):
                lines.append(f'{k} = "{v}"')
            elif isinstance(v, list):
                lines.append(f"{k} = [{', '.join(repr(x).replace(chr(39), chr(34)) for x in v)}]")
            else:
                lines.append(f"{k} = {v}")
        return "\n".join(lines) + "\n"


_COLOR_FIELDS = {"color", "highlight", "box_text_color", "stroke_color"}
_FIELDS = {f.name for f in fields(Style)}


def style_from_dict(data: dict, base: Style | None = None, source: str = "style") -> Style:
    unknown = set(data) - _FIELDS - {"extends"}
    if unknown:
        raise WordcapsError(
            f"{source}: unknown option(s) {', '.join(sorted(unknown))}. "
            f"Valid options: {', '.join(sorted(_FIELDS))}"
        )
    values = asdict(base) if base else {}
    for k, v in data.items():
        if k == "extends":
            continue
        values[k] = parse_color(v) if k in _COLOR_FIELDS else v
    return Style(**values).validate()


def preset_names() -> list[str]:
    files = resources.files("wordcaps").joinpath("presets").iterdir()
    return sorted(p.name[:-5] for p in files if p.name.endswith(".toml"))


def _read_preset(name: str) -> dict:
    res = resources.files("wordcaps").joinpath("presets", f"{name}.toml")
    if not res.is_file():
        raise WordcapsError(f"unknown style '{name}'. Presets: {', '.join(preset_names())}")
    return tomllib.loads(res.read_text(encoding="utf-8"))


def load_style(spec: str = "reel", overrides: dict | None = None) -> Style:
    """Load a preset by name or a ``.toml`` file, then apply overrides.

    A TOML file can start from a preset with ``extends = "reel"``.
    """
    path = Path(spec).expanduser()
    if path.suffix == ".toml":
        if not path.is_file():
            raise WordcapsError(f"style file not found: {path}")
        try:
            data = tomllib.loads(path.read_text(encoding="utf-8"))
        except tomllib.TOMLDecodeError as e:
            raise WordcapsError(f"{path}: {e}") from e
        base = load_style(data["extends"]) if "extends" in data else None
        data.setdefault("name", path.stem)
        style = style_from_dict(data, base, str(path))
    else:
        style = style_from_dict({"name": spec, **_read_preset(spec)}, None, f"preset {spec}")
    if overrides:
        style = style_from_dict(overrides, style, "command line")
    return style
