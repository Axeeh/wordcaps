import json

from wordcaps.cli import build_parser, main


def test_export_srt_to_stdout(tmp_path, capsys):
    p = tmp_path / "c.json"
    p.write_text(json.dumps({"words": [["Hello,", 0, 0.4], ["world.", 0.4, 0.9]]}))
    assert main(["export", str(p)]) == 0
    assert "HELLO WORLD" in capsys.readouterr().out


def test_export_infers_format_from_extension(tmp_path):
    p = tmp_path / "c.json"
    p.write_text(json.dumps({"cues": [{"words": [["hi", 0, 1]]}]}))
    out = tmp_path / "c.vtt"
    assert main(["export", str(p), "-o", str(out)]) == 0
    assert out.read_text().startswith("WEBVTT")


def test_set_parses_toml_values():
    from wordcaps.cli import _parse_set
    assert _parse_set(["max_words=5", "uppercase=false", "highlight=#FF0000",
                       'emphasis=["WOW"]']) == {
        "max_words": 5, "uppercase": False, "highlight": "#FF0000", "emphasis": ["WOW"]}


def test_errors_are_reported_without_traceback(capsys):
    assert main(["export", "/nope.json"]) == 2
    assert "not found" in capsys.readouterr().err


def test_styles_listing(capsys):
    assert main(["styles"]) == 0
    assert "reel" in capsys.readouterr().out
    assert main(["styles", "--show", "box"]) == 0
    assert 'highlight_mode = "box"' in capsys.readouterr().out


def test_every_command_has_help():
    parser = build_parser()
    sub = next(a for a in parser._actions if a.dest == "command")
    assert set(sub.choices) == {"burn", "transcribe", "preview", "export", "verify",
                                "sheet", "styles", "models", "doctor"}
