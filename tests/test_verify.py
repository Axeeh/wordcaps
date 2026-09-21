from wordcaps.models import Cue, Word
from wordcaps.verify import check_coverage


def test_all_covered():
    rep = check_coverage([(1.0, 2.0)], [Cue([Word("a", 0.95, 2.02)])])
    assert rep.ok and rep.silent_cues == []


def test_uncovered_stretch_is_reported():
    cues = [Cue([Word("a", 1.0, 1.5)]), Cue([Word("b", 2.5, 3.0)])]
    rep = check_coverage([(1.0, 3.0)], cues)
    assert not rep.ok
    assert len(rep.uncovered) == 1
    s, e = rep.uncovered[0]
    assert 1.55 <= s <= 1.65 and 2.35 <= e <= 2.45


def test_tolerance_forgives_tiny_offsets():
    assert check_coverage([(1.0, 2.0)], [Cue([Word("a", 1.08, 1.95)])]).ok
    assert not check_coverage([(1.0, 2.0)], [Cue([Word("a", 1.3, 2.0)])]).ok


def test_caption_over_silence_is_flagged():
    rep = check_coverage([(1.0, 2.0)], [Cue([Word("a", 1.0, 2.0)]), Cue([Word("b", 5, 6)])])
    assert [c.text for c in rep.silent_cues] == ["b"]


def test_no_cues_at_all():
    assert not check_coverage([(0.5, 1.0)], []).ok
