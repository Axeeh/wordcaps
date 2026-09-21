import json

import pytest

from wordcaps.models import Cue, Word, WordcapsError, load_captions, save_captions


def test_roundtrip(tmp_path):
    cues = [Cue([Word("CIAO", 0.2, 0.55), Word("RAGAZZI", 0.55, 0.99)]),
            Cue([Word("NUOTO", 3.36, 3.76), Word("CONTROCORRENTE", 3.76, 4.5)], lines=[0, 1])]
    path = tmp_path / "c.json"
    save_captions(path, cues, "it")
    loaded, loose, lang = load_captions(path)
    assert lang == "it" and loose == []
    assert [c.text for c in loaded] == ["CIAO RAGAZZI", "NUOTO CONTROCORRENTE"]
    assert loaded[1].lines == [0, 1]
    # one cue per line keeps diffs and hand edits readable
    assert len(path.read_text().splitlines()) == 8


def test_accepts_word_objects_and_loose_words(tmp_path):
    path = tmp_path / "c.json"
    path.write_text(json.dumps({"words": [{"text": "hi", "start": 0, "end": 0.3}]}))
    cues, loose, _ = load_captions(path)
    assert cues == [] and loose[0].text == "hi"


@pytest.mark.parametrize("payload, message", [
    ({"cues": [{"words": [["a", 1, 0.5]]}]}, "ends before"),
    ({"cues": [{"words": [["a", 0, 1]], "lines": [1]}]}, "invalid lines"),
    ({"cues": [{"words": [["a", 0]]}]}, "must be"),
    ({}, "no cues"),
])
def test_rejects_bad_files(tmp_path, payload, message):
    path = tmp_path / "c.json"
    path.write_text(json.dumps(payload))
    with pytest.raises(WordcapsError, match=message):
        load_captions(path)


def test_missing_file():
    with pytest.raises(WordcapsError, match="not found"):
        load_captions("/nope/c.json")
