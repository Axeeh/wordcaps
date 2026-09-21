"""Check that every moment of speech in a video has a caption on screen.

Transcription and manual edits both go wrong in quiet ways: a phrase that got
dropped, a cue that ends before the voice does, a caption over silence. This
check re-reads the loudness envelope of the finished file and compares it
with the captions, independently of Whisper.
"""

from __future__ import annotations

from bisect import bisect_right
from dataclasses import dataclass, field

from .models import Cue

Block = tuple[float, float]


@dataclass
class CoverageReport:
    blocks: list[Block]
    uncovered: list[Block] = field(default_factory=list)
    silent_cues: list[Cue] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.uncovered

    @property
    def uncovered_seconds(self) -> float:
        return sum(e - s for s, e in self.uncovered)


def _covered(starts: list[float], cues: list[Cue], t: float, tol: float) -> bool:
    i = bisect_right(starts, t + tol) - 1
    # cues are sorted and non-overlapping in practice; look back a little
    for j in range(max(0, i - 2), i + 1):
        c = cues[j]
        if c.start - tol <= t < c.end + tol:
            return True
    return False


def check_coverage(
    blocks: list[Block], cues: list[Cue], *, step: float = 0.05, tolerance: float = 0.1
) -> CoverageReport:
    """Sample each speech block every ``step`` seconds.

    ``tolerance`` forgives captions that start or end slightly off the
    envelope edge, which is normal and invisible.
    """
    cues = sorted(cues, key=lambda c: c.start)
    starts = [c.start for c in cues]
    report = CoverageReport(blocks)
    for a, b in blocks:
        t, run_start = a, None
        while t < b:
            hit = bool(cues) and _covered(starts, cues, t, tolerance)
            if not hit and run_start is None:
                run_start = t
            if hit and run_start is not None:
                report.uncovered.append((round(run_start, 2), round(t, 2)))
                run_start = None
            t += step
        if run_start is not None:
            report.uncovered.append((round(run_start, 2), round(b, 2)))
    for c in cues:
        if not any(e > c.start + 0.1 and s < c.end - 0.1 for s, e in blocks):
            report.silent_cues.append(c)
    return report
