"""Group words into on-screen captions (cues)."""

from __future__ import annotations

import re

from .models import Cue, Word

_SENTENCE_END = re.compile(r"[.!?…]+[\"'”»)]*$")
_CLAUSE_END = re.compile(r"[,;:–]+[\"'”»)]*$")
_PUNCT_EDGES = re.compile(r"^[\"'“”«»(\[¿¡]+|[\"'“”«»)\].,;:!?…]+$")


def clean_text(text: str, *, uppercase: bool, strip_punctuation: bool) -> str:
    text = text.strip()
    if strip_punctuation:
        # only at the edges: keeps "3-4", "l'acqua", "e-mail"
        prev = None
        while prev != text:
            prev, text = text, _PUNCT_EDGES.sub("", text)
    return text.upper() if uppercase else text


def group_words(
    words: list[Word],
    *,
    max_words: int = 3,
    max_chars: int = 22,
    max_pause: float = 0.35,
    gap_fill: float = 0.3,
    uppercase: bool = True,
    strip_punctuation: bool = True,
) -> list[Cue]:
    """Split a word stream into cues.

    A new cue starts when the current one would exceed ``max_words`` or
    ``max_chars``, after a pause longer than ``max_pause``, after the end of a
    sentence, or after a comma once the cue has at least two words.

    Inside a cue each word is stretched to the start of the next, so the
    karaoke highlight never blinks off between words; between cues, gaps
    shorter than ``gap_fill`` are closed for the same reason.
    """
    groups: list[list[Word]] = []
    cur: list[Word] = []
    cur_chars = 0
    prev_raw = ""
    for w in words:
        text = clean_text(w.text, uppercase=uppercase, strip_punctuation=strip_punctuation)
        if not text:
            continue
        if cur and (
            len(cur) >= max_words
            or cur_chars + 1 + len(text) > max_chars
            or w.start - cur[-1].end > max_pause
            or _SENTENCE_END.search(prev_raw)
            or (len(cur) >= 2 and _CLAUSE_END.search(prev_raw))
        ):
            groups.append(cur)
            cur, cur_chars = [], 0
        cur.append(Word(text, w.start, w.end))
        cur_chars += len(text) + (1 if cur_chars else 0)
        prev_raw = w.text.strip()
    if cur:
        groups.append(cur)

    for g in groups:
        for a, b in zip(g, g[1:], strict=False):
            a.end = max(a.start, b.start)
    for a, b in zip(groups, groups[1:], strict=False):
        gap = b[0].start - a[-1].end
        if 0 < gap <= gap_fill:
            a[-1].end = b[0].start
        elif gap < 0:
            a[-1].end = max(a[-1].start, b[0].start)
    return [Cue(g) for g in groups]

