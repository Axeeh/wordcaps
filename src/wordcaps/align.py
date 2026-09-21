"""Make Whisper's word timings agree with what the audio actually contains.

Two things go wrong with raw Whisper timestamps, and both show up on screen
as captions that lead or lag the voice:

1. **Leading silence.** When a clip starts with dead air, Whisper tends to
   spread the first words across it, so they appear up to a second early.
   The fix is upstream: :func:`plan_segments` cuts the audio so every
   transcribed segment starts ~0.15 s before the first sound.
2. **Word edges in silence.** A word may start before the voice does or end
   after it stopped. :func:`refine_words` snaps those edges onto the speech
   blocks found in the loudness envelope.
"""

from __future__ import annotations

from bisect import bisect_right
from dataclasses import dataclass

from .models import Word

Block = tuple[float, float]


def plan_segments(
    blocks: list[Block], pad: float = 0.15, split_gap: float = 1.5
) -> list[Block]:
    """Group speech blocks into segments to transcribe one at a time.

    Every segment starts ``pad`` seconds before its first sound, so Whisper
    never sees a long stretch of leading silence. Pauses longer than
    ``split_gap`` start a new segment.
    """
    segments: list[list[float]] = []
    for s, e in blocks:
        if segments and s - segments[-1][1] < split_gap:
            segments[-1][1] = e
        else:
            segments.append([s, e])
    return [(max(0.0, s - pad), e + pad) for s, e in segments]


@dataclass
class Adjustment:
    word: str
    before: tuple[float, float]
    after: tuple[float, float]
    note: str


class _Blocks:
    def __init__(self, blocks: list[Block], tolerance: float):
        self.blocks = sorted(blocks)
        self.starts = [s for s, _ in self.blocks]
        self.tol = tolerance

    def containing(self, t: float) -> Block | None:
        i = bisect_right(self.starts, t + self.tol) - 1
        if i >= 0:
            s, e = self.blocks[i]
            if s - self.tol <= t <= e + self.tol:
                return self.blocks[i]
        return None

    def next_start_after(self, t: float) -> float | None:
        i = bisect_right(self.starts, t)
        return self.starts[i] if i < len(self.starts) else None

    def prev_end_before(self, t: float) -> float | None:
        ends = [e for _, e in self.blocks if e <= t]
        return ends[-1] if ends else None

    def distance(self, s: float, e: float) -> float:
        """0 if [s, e] touches speech, else the gap to the nearest block."""
        return min(
            (max(0.0, bs - e, s - be) for bs, be in self.blocks), default=float("inf")
        )


def refine_words(
    words: list[Word],
    blocks: list[Block],
    *,
    tolerance: float = 0.05,
    min_duration: float = 0.08,
    suspect_gap: float = 0.3,
) -> tuple[list[Word], list[Adjustment]]:
    """Snap word edges that fall in silence onto the nearest speech edge.

    Returns the corrected words (new objects, input untouched) and a log of
    every change. Words more than ``suspect_gap`` seconds away from any speech
    are kept but reported: they are usually Whisper hallucinations worth checking.
    """
    if not blocks:
        return [Word(w.text, w.start, w.end) for w in words], []
    idx = _Blocks(blocks, tolerance)
    out: list[Word] = []
    log: list[Adjustment] = []
    prev_end = 0.0
    for w in words:
        s, e = w.start, w.end
        notes = []
        if idx.containing(s) is None:
            nxt = idx.next_start_after(s)
            if nxt is not None and nxt < e:
                s = nxt
                notes.append("start moved to speech onset")
        if idx.containing(e) is None:
            prv = idx.prev_end_before(e)
            if prv is not None and prv > s:
                e = prv
                notes.append("end moved to speech offset")
        if idx.distance(s, e) > suspect_gap:
            notes.append("no speech near this word, check it")
        s = max(s, prev_end)
        e = max(e, s + min_duration)
        if notes or (s, e) != (w.start, w.end):
            log.append(
                Adjustment(w.text, (w.start, w.end), (round(s, 3), round(e, 3)),
                           ", ".join(notes) or "overlap with previous word removed")
            )
        out.append(Word(w.text, round(s, 4), round(e, 4)))
        prev_end = e
    return out, log
