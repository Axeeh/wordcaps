"""Core data types and the editable captions file format."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

FORMAT_VERSION = 1


class WordcapsError(RuntimeError):
    """An error meant to be shown to the user as-is, without a traceback."""


@dataclass
class Word:
    text: str
    start: float
    end: float

    @property
    def duration(self) -> float:
        return self.end - self.start


@dataclass
class Cue:
    """A caption shown on screen as one unit, highlighted word by word.

    ``lines`` optionally forces the line breaks: it lists the index of the
    first word of each line, e.g. ``[0, 2]`` puts words 0-1 on the first line
    and the rest on the second. ``None`` lets the renderer decide.
    """

    words: list[Word]
    lines: list[int] | None = None

    @property
    def start(self) -> float:
        return self.words[0].start

    @property
    def end(self) -> float:
        return self.words[-1].end

    @property
    def text(self) -> str:
        return " ".join(w.text for w in self.words)


def cues_to_dict(cues: list[Cue], language: str | None = None) -> dict:
    out: dict = {"wordcaps": FORMAT_VERSION}
    if language:
        out["language"] = language
    items = []
    for c in cues:
        item: dict = {"words": [[w.text, round(w.start, 4), round(w.end, 4)] for w in c.words]}
        if c.lines is not None:
            item["lines"] = c.lines
        items.append(item)
    out["cues"] = items
    return out


def save_captions(path: str | Path, cues: list[Cue], language: str | None = None) -> None:
    """Write captions as JSON, one word per ``[text, start, end]`` triple.

    The layout keeps one cue per line so the file stays easy to fix by hand.
    """
    data = cues_to_dict(cues, language)
    lines = ["{", f'  "wordcaps": {data["wordcaps"]},']
    if "language" in data:
        lines.append(f'  "language": {json.dumps(data["language"])},')
    lines.append('  "cues": [')
    for i, item in enumerate(data["cues"]):
        sep = "," if i < len(data["cues"]) - 1 else ""
        lines.append("    " + json.dumps(item, ensure_ascii=False) + sep)
    lines += ["  ]", "}"]
    Path(path).write_text("\n".join(lines) + "\n", encoding="utf-8")


def _parse_word(raw, where: str) -> Word:
    if isinstance(raw, dict):
        raw = [raw.get("text"), raw.get("start"), raw.get("end")]
    if not (isinstance(raw, list | tuple) and len(raw) == 3):
        raise WordcapsError(f"{where}: a word must be [text, start, end], got {raw!r}")
    text, start, end = raw
    try:
        w = Word(str(text), float(start), float(end))
    except (TypeError, ValueError) as e:
        raise WordcapsError(f"{where}: bad word {raw!r}") from e
    if w.end < w.start:
        raise WordcapsError(f"{where}: word {w.text!r} ends before it starts")
    return w


def load_captions(path: str | Path) -> tuple[list[Cue], list[Word], str | None]:
    """Read a captions file.

    Returns ``(cues, loose_words, language)``. A file may hold ready-made
    ``cues`` or a flat ``words`` list that still has to be grouped.
    """
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError as e:
        raise WordcapsError(f"captions file not found: {path}") from e
    except json.JSONDecodeError as e:
        raise WordcapsError(f"{path}: invalid JSON ({e})") from e

    cues: list[Cue] = []
    for i, item in enumerate(data.get("cues", [])):
        words = [_parse_word(w, f"{path}: cue {i}") for w in item.get("words", [])]
        if not words:
            continue
        lines = item.get("lines")
        if lines is not None and (
            not lines or lines[0] != 0 or sorted(set(lines)) != lines or lines[-1] >= len(words)
        ):
            raise WordcapsError(
                f"{path}: cue {i} has invalid lines {lines!r} "
                "(first-word indexes, starting at 0, increasing)"
            )
        cues.append(Cue(words, lines))
    loose = [_parse_word(w, f"{path}: words") for w in data.get("words", [])]
    if not cues and not loose:
        raise WordcapsError(f"{path}: no cues or words found")
    return cues, loose, data.get("language")
