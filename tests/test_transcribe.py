import os
import shutil
from pathlib import Path

import pytest

from wordcaps.transcribe import merge_tokens


def test_merge_tokens_joins_subwords_and_drops_tags():
    toks = [(0.0, 0.2, " Ciao"), (0.2, 0.5, " fighi"), (0.5, 0.8, "ssima"),
            (0.8, 0.9, "!"), (0.9, 1.0, " [BLANK_AUDIO]"), (1.0, 1.2, " ok")]
    words = merge_tokens(toks)
    assert [(w.text, w.start, w.end) for w in words] == [
        ("Ciao", 0.0, 0.2), ("fighissima!", 0.2, 0.9), ("ok", 1.0, 1.2)]


def test_faster_whisper_load_failure_is_actionable(monkeypatch):
    import sys
    import types

    from wordcaps.models import WordcapsError
    from wordcaps.transcribe import FasterWhisper

    def fail(*args, **kwargs):
        raise OSError("403 Forbidden")

    monkeypatch.setitem(sys.modules, "faster_whisper", types.SimpleNamespace(WhisperModel=fail))
    with pytest.raises(WordcapsError, match="could not load model 'base'"):
        FasterWhisper("base")


def test_faster_whisper_joins_hyphenated_pieces(monkeypatch):
    import sys
    import types

    from wordcaps.transcribe import FasterWhisper

    W = types.SimpleNamespace
    pieces = [(" how", 0.0, 0.2), (" word", 0.2, 0.4), ("-by", 0.4, 0.6),
              ("-word", 0.6, 0.8), (" captions", 0.8, 1.2)]

    class Model:
        def __init__(self, *args, **kwargs):
            pass

        def transcribe(self, *args, **kwargs):
            seg = W(words=[W(word=t, start=s, end=e) for t, s, e in pieces])
            return [seg], None

    monkeypatch.setitem(sys.modules, "faster_whisper", W(WhisperModel=Model))
    words = FasterWhisper("base").transcribe(Path("x.wav"), "en")
    assert [(w.text, w.start, w.end) for w in words] == [
        ("how", 0.0, 0.2), ("word-by-word", 0.2, 0.8), ("captions", 0.8, 1.2)]


@pytest.mark.whisper
@pytest.mark.skipif(not os.environ.get("WORDCAPS_TEST_MODEL") or not shutil.which("say"),
                    reason="set WORDCAPS_TEST_MODEL to a ggml model (macOS only: uses `say`)")
def test_real_transcription(tmp_path):
    import subprocess

    from wordcaps.align import refine_words
    from wordcaps.transcribe import WhisperCpp, transcribe_media

    wav = tmp_path / "v.aiff"
    subprocess.run(["say", "-o", str(wav), "[[slnc 1500]] The quick brown fox."], check=True)
    backend = WhisperCpp(os.environ["WORDCAPS_TEST_MODEL"])
    words, analysis = transcribe_media(Path(wav), backend, language="en")
    words, _ = refine_words(words, analysis.blocks)
    assert "fox" in " ".join(w.text.lower() for w in words)
    # leading silence must not drag the first word early
    assert words[0].start >= analysis.blocks[0][0] - 0.1
