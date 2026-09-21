import numpy as np
import pytest

from wordcaps.models import Cue, Word
from wordcaps.render import OverlayRenderer, break_lines
from wordcaps.style import load_style

W, H = 540, 960


def cues():
    return [Cue([Word("HELLO", 1.0, 1.4), Word("THERE", 1.4, 2.0)]),
            Cue([Word("WOW", 2.0, 2.5)])]


def pixels(img):
    return np.asarray(img)


def test_break_lines():
    assert break_lines([10, 10, 10], 2, 100) == [[0, 1, 2]]
    # ties go to the shorter top line (pyramid shape)
    assert break_lines([40, 40, 40], 2, 90) == [[0], [1, 2]]
    assert break_lines([60, 10, 70], 2, 90) == [[0, 1], [2]]
    assert break_lines([50, 50, 50, 50], 2, 60) == [[0], [1], [2], [3]]
    assert break_lines([10, 10, 10], 2, 5, forced=[0, 2]) == [[0, 1], [2]]


def test_transparent_outside_cues():
    r = OverlayRenderer(cues(), load_style("reel"), W, H, 30)
    assert pixels(r.frame_image(0.5))[..., 3].max() == 0
    assert r.frame_bytes(0.5) == bytes(W * H * 4)
    assert pixels(r.frame_image(3.0))[..., 3].max() == 0


def test_active_word_uses_highlight_color():
    style = load_style("reel", {"fade_in": 0, "shadow": False})
    r = OverlayRenderer(cues(), style, W, H, 30)
    px = pixels(r.frame_image(1.2)).reshape(-1, 4)
    rgb = {tuple(p[:3]) for p in px if p[3] == 255}
    assert style.highlight in rgb and style.color in rgb


def test_caption_sits_around_baseline():
    style = load_style("reel", {"fade_in": 0})
    r = OverlayRenderer(cues(), style, W, H, 30)
    rows = np.flatnonzero(pixels(r.frame_image(1.2))[..., 3].max(axis=1))
    baseline = style.baseline * H
    assert rows.min() > baseline - 2 * r.size
    assert rows.max() < baseline + r.size


def test_fade_in():
    style = load_style("reel", {"fade_in": 0.2})
    r = OverlayRenderer(cues(), style, W, H, 30)
    early = pixels(r.frame_image(1.05))[..., 3].max()
    late = pixels(r.frame_image(1.3))[..., 3].max()
    assert 0 < early < late == 255


def test_identical_states_reuse_cached_frame():
    style = load_style("reel", {"fade_in": 0})
    r = OverlayRenderer(cues(), style, W, H, 30)
    assert r.frame_bytes(1.1) is r.frame_bytes(1.2)
    assert r.frame_bytes(1.2) is not r.frame_bytes(1.5)  # highlight moved


@pytest.mark.parametrize("preset", ["box", "pop", "ocean", "minimal", "landscape"])
def test_every_preset_renders(preset):
    style = load_style(preset, {"emphasis": ["WOW"]})
    r = OverlayRenderer(cues(), style, W, H, 30)
    for t in (1.1, 1.5, 2.1, 2.4):
        assert pixels(r.frame_image(t))[..., 3].max() > 0


def test_emphasis_word_grows_then_settles():
    style = load_style("reel", {"emphasis": ["wow"], "fade_in": 0})
    r = OverlayRenderer(cues(), style, W, H, 30)
    scale_at = [r._state(t)[2][0].scale for t in (2.0, 2.2, 2.45)]
    assert scale_at[0] == 100 and max(scale_at) > 125 >= scale_at[-1] - 1
    assert r._state(2.3)[2][0].boxed


def test_long_cue_wraps_inside_max_width():
    texts = ["A", "VERY", "LONG", "CAPTION", "LINE"]
    words = [Word(t, i * 0.3, i * 0.3 + 0.3) for i, t in enumerate(texts)]
    style = load_style("reel", {"fade_in": 0, "max_width": 0.6})
    r = OverlayRenderer([Cue(words)], style, W, H, 30)
    assert len(r.layouts[0]) >= 2
    cols = np.flatnonzero(pixels(r.frame_image(0.1))[..., 3].max(axis=0))
    assert cols.min() > 0 and cols.max() < W - 1
