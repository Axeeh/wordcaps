from wordcaps.export import to_ass, to_srt, to_vtt
from wordcaps.models import Cue, Word
from wordcaps.style import load_style

CUES = [Cue([Word("HELLO", 1.0, 1.5), Word("THERE", 1.5, 2.25)]),
        Cue([Word("WORLD", 3661.2, 3662.0)])]


def test_srt():
    assert to_srt(CUES) == (
        "1\n00:00:01,000 --> 00:00:02,250\nHELLO THERE\n\n"
        "2\n01:01:01,200 --> 01:01:02,000\nWORLD\n"
    )


def test_vtt():
    out = to_vtt(CUES)
    assert out.startswith("WEBVTT\n\n00:00:01.000 --> 00:00:02.250\nHELLO THERE\n")


def test_ass_has_one_event_per_word_with_moving_highlight():
    out = to_ass(CUES, load_style("reel"), 1080, 1920)
    events = [line for line in out.splitlines() if line.startswith("Dialogue:")]
    assert len(events) == 3
    assert events[0].startswith("Dialogue: 0,0:00:01.00,0:00:01.50,")
    hl = "{\\c&H00DDFF&}"
    assert hl + "HELLO" in events[0] and hl + "THERE" not in events[0]
    assert hl + "THERE" in events[1]
    assert "PlayResY: 1920" in out and "Montserrat" in out


def test_ass_escapes_braces():
    out = to_ass([Cue([Word("{x}", 0, 1)])], load_style("reel"))
    assert "(x)" in out
