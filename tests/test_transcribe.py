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
