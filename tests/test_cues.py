from wordcaps.cues import clean_text, group_words
from wordcaps.models import Word


def w(text, s, e):
    return Word(text, s, e)


def test_clean_text_keeps_inner_punctuation():
    assert clean_text("l'acqua,", uppercase=True, strip_punctuation=True) == "L'ACQUA"
    assert clean_text("3-4", uppercase=True, strip_punctuation=True) == "3-4"
    assert clean_text("«Ciao!»", uppercase=False, strip_punctuation=True) == "Ciao"
    assert clean_text("Hi,", uppercase=False, strip_punctuation=False) == "Hi,"
    assert clean_text("...", uppercase=True, strip_punctuation=True) == ""


def test_max_words():
    words = [w(str(i), i * 0.3, i * 0.3 + 0.25) for i in range(7)]
    cues = group_words(words, max_words=3, max_chars=99)
    assert [len(c.words) for c in cues] == [3, 3, 1]


def test_max_chars():
    words = [w("aaaaaa", 0, 0.2), w("bbbbbb", 0.2, 0.4), w("cccccc", 0.4, 0.6)]
    cues = group_words(words, max_words=9, max_chars=13)
    assert [c.text for c in cues] == ["AAAAAA BBBBBB", "CCCCCC"]


def test_pause_starts_new_cue():
    cues = group_words([w("a", 0, 0.2), w("b", 1.0, 1.2)], max_pause=0.35)
    assert len(cues) == 2


def test_sentence_end_starts_new_cue():
    cues = group_words([w("Ciao.", 0, 0.2), w("Oggi", 0.2, 0.4)])
    assert [c.text for c in cues] == ["CIAO", "OGGI"]


def test_comma_breaks_only_after_two_words():
    cues = group_words([w("Hi,", 0, 0.2), w("everyone,", 0.2, 0.5), w("today", 0.5, 0.7)])
    assert [c.text for c in cues] == ["HI EVERYONE", "TODAY"]


def test_words_become_contiguous_inside_cue():
    cues = group_words([w("a", 0, 0.2), w("b", 0.3, 0.5)])
    assert cues[0].words[0].end == 0.3


def test_small_gaps_between_cues_are_filled():
    words = [w("a", 0, 0.2), w("b", 0.2, 0.4), w("c", 0.4, 0.6), w("d", 0.75, 0.9)]
    cues = group_words(words, max_words=3, gap_fill=0.3)
    assert cues[0].end == cues[1].start == 0.75


def test_empty_words_are_skipped():
    cues = group_words([w("...", 0, 0.1), w("ok", 0.1, 0.3)])
    assert [c.text for c in cues] == ["OK"]
