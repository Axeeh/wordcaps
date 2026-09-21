import pytest

from wordcaps.models import WordcapsError
from wordcaps.style import load_style, parse_color, preset_names


def test_all_presets_load():
    names = preset_names()
    assert {"reel", "landscape", "box", "pop", "ocean", "minimal"} <= set(names)
    for name in names:
        style = load_style(name)
        assert style.name == name and style.description


def test_parse_color():
    assert parse_color("#33A9F4") == (51, 169, 244)
    assert parse_color("fff") == (255, 255, 255)
    assert parse_color([1, 2, 3]) == (1, 2, 3)
    with pytest.raises(WordcapsError):
        parse_color("#12")


def test_overrides_and_validation():
    style = load_style("reel", {"highlight": "#00FF00", "max_words": 5})
    assert style.highlight == (0, 255, 0) and style.max_words == 5
    with pytest.raises(WordcapsError, match="unknown option"):
        load_style("reel", {"colour": "#fff"})
    with pytest.raises(WordcapsError, match="highlight_mode"):
        load_style("reel", {"highlight_mode": "blink"})
    with pytest.raises(WordcapsError, match="fraction"):
        load_style("reel", {"baseline": 1290})


def test_toml_file_extends_preset(tmp_path):
    f = tmp_path / "brand.toml"
    f.write_text('extends = "landscape"\nhighlight = "#FF0055"\n')
    style = load_style(str(f))
    assert style.name == "brand"
    assert style.highlight == (255, 0, 85)
    assert style.uppercase is False  # inherited from landscape


def test_unknown_preset():
    with pytest.raises(WordcapsError, match="unknown style"):
        load_style("nope")


def test_to_toml_roundtrip(tmp_path):
    f = tmp_path / "s.toml"
    f.write_text(load_style("ocean", {"emphasis": ["WOW"]}).to_toml())
    again = load_style(str(f))
    assert again.highlight == (51, 169, 244) and again.emphasis == ["WOW"]
