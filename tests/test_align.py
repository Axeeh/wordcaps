from wordcaps.align import plan_segments, refine_words
from wordcaps.models import Word


def test_plan_segments_pads_and_splits_on_long_pauses():
    blocks = [(1.0, 2.0), (2.5, 3.0), (6.0, 7.0)]
    assert plan_segments(blocks, pad=0.15, split_gap=1.5) == [(0.85, 3.15), (5.85, 7.15)]


def test_plan_segments_never_negative():
    assert plan_segments([(0.05, 1.0)]) == [(0.0, 1.15)]


def test_start_in_silence_snaps_to_onset():
    words, log = refine_words([Word("ciao", 0.4, 1.2)], [(1.0, 2.0)])
    assert (words[0].start, words[0].end) == (1.0, 1.2)
    assert "onset" in log[0].note


def test_end_in_silence_snaps_to_offset():
    words, _ = refine_words([Word("ragazzi", 1.5, 2.6)], [(1.0, 2.0)])
    assert (words[0].start, words[0].end) == (1.5, 2.0)


def test_words_inside_speech_are_untouched():
    src = [Word("a", 1.1, 1.3), Word("b", 1.3, 1.8)]
    words, log = refine_words(src, [(1.0, 2.0)])
    assert [(w.start, w.end) for w in words] == [(1.1, 1.3), (1.3, 1.8)]
    assert log == []


def test_overlaps_removed_and_min_duration_enforced():
    words, _ = refine_words([Word("a", 1.0, 1.5), Word("b", 1.4, 1.42)], [(1.0, 2.0)],
                            min_duration=0.08)
    assert words[1].start == 1.5
    assert words[1].end >= words[1].start + 0.08


def test_word_far_from_speech_is_flagged_not_removed():
    words, log = refine_words([Word("grazie", 5.0, 5.5)], [(1.0, 2.0)])
    assert len(words) == 1
    assert "check" in log[0].note


def test_input_is_not_mutated():
    src = [Word("ciao", 0.4, 1.2)]
    refine_words(src, [(1.0, 2.0)])
    assert src[0].start == 0.4


def test_no_blocks_returns_copy():
    words, log = refine_words([Word("x", 1, 2)], [])
    assert words[0].start == 1 and log == []
