"""Export captions to standard subtitle formats (SRT, WebVTT, ASS)."""

from __future__ import annotations

from .models import Cue
from .render import OverlayRenderer
from .style import Style


def _ts(t: float, sep: str) -> str:
    ms = max(0, round(t * 1000))
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d}{sep}{ms:03d}"


def to_srt(cues: list[Cue]) -> str:
    blocks = [
        f"{i}\n{_ts(c.start, ',')} --> {_ts(c.end, ',')}\n{c.text}\n"
        for i, c in enumerate(cues, 1)
    ]
    return "\n".join(blocks)


def to_vtt(cues: list[Cue]) -> str:
    body = "\n".join(f"{_ts(c.start, '.')} --> {_ts(c.end, '.')}\n{c.text}\n" for c in cues)
    return "WEBVTT\n\n" + body


def _ass_time(t: float) -> str:
    cs = max(0, round(t * 100))
    h, cs = divmod(cs, 360_000)
    m, cs = divmod(cs, 6000)
    s, cs = divmod(cs, 100)
    return f"{h:d}:{m:02d}:{s:02d}.{cs:02d}"


def _ass_color(rgb: tuple[int, int, int], alpha: int = 0) -> str:
    r, g, b = rgb
    return f"&H{alpha:02X}{b:02X}{g:02X}{r:02X}"


def _ass_inline_color(rgb: tuple[int, int, int]) -> str:
    r, g, b = rgb
    return f"{{\\c&H{b:02X}{g:02X}{r:02X}&}}"


def _ass_escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace("{", "(").replace("}", ")")


def to_ass(cues: list[Cue], style: Style, width: int = 1080, height: int = 1920) -> str:
    """ASS with one event per spoken word, so the highlight moves exactly as
    in the burned-in version. Box and pop animations are not reproduced."""
    r = OverlayRenderer(cues, style, width, height, fps=30)
    family = r.font.getname()[0]
    stroke = round(style.stroke * r.size)
    shadow = round(style.shadow_offset * r.size) if style.shadow else 0
    margin_v = max(0, round(height - style.baseline * height - 0.2 * r.size))
    head = [
        "[Script Info]",
        "ScriptType: v4.00+",
        f"PlayResX: {width}",
        f"PlayResY: {height}",
        "WrapStyle: 2",
        "ScaledBorderAndShadow: yes",
        "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, "
        "BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, "
        "BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
        f"Style: Default,{family},{r.size},{_ass_color(style.color)},"
        f"{_ass_color(style.highlight)},{_ass_color(style.stroke_color)},"
        f"{_ass_color((0, 0, 0), 255 - round(255 * style.shadow_opacity))},"
        f"0,0,0,0,100,100,0,0,1,{stroke},{shadow},2,20,20,{margin_v},1",
        "",
        "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
    ]
    hl, reset = _ass_inline_color(style.highlight), _ass_inline_color(style.color)
    events = []
    for ci, cue in enumerate(r.cues):
        lines = [[wi for wi, _ in row] for row in r.layouts[ci]]
        for wi, w in enumerate(cue.words):
            if w.end <= w.start:
                continue
            text = "\\N".join(
                " ".join(
                    (hl + _ass_escape(cue.words[j].text) + reset) if j == wi
                    else _ass_escape(cue.words[j].text)
                    for j in line
                )
                for line in lines
            )
            events.append(
                f"Dialogue: 0,{_ass_time(w.start)},{_ass_time(w.end)},Default,,0,0,0,,{text}"
            )
    return "\n".join(head + events) + "\n"
