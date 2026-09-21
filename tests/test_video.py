"""End-to-end tests through ffmpeg, with a hand-written captions file."""

import json

import numpy as np
import pytest
from PIL import Image

from wordcaps.cli import main
from wordcaps.video import probe

CAPTIONS = {"cues": [
    {"words": [["HELLO", 0.5, 0.9], ["THERE", 0.9, 1.2]]},
    {"words": [["TESTING", 1.8, 2.6]]},
]}


@pytest.fixture
def captions(tmp_path):
    p = tmp_path / "c.json"
    p.write_text(json.dumps(CAPTIONS))
    return p


def test_probe(make_video):
    info = probe(make_video(width=180, height=320, duration=2.0, fps=25))
    assert (info.width, info.height, float(info.fps)) == (180, 320, 25.0)
    assert info.duration == pytest.approx(2.0, abs=0.1) and info.has_audio
    assert info.frame_count in (50, 51)


def test_burn_and_verify(make_video, captions, tmp_path):
    src = make_video()
    out = tmp_path / "out.mp4"
    assert main(["burn", str(src), "-o", str(out), "--captions", str(captions)]) == 0
    info = probe(out)
    assert (info.width, info.height) == (180, 320) and info.has_audio

    # captions changed the pixels around the baseline, not elsewhere
    from wordcaps.video import grab_frame
    before, after = (np.asarray(grab_frame(p, 0.7).convert("L"), dtype=int) for p in (src, out))
    diff = np.abs(before - after)
    band = int(0.70 * 320)
    assert diff[band - 25:band + 5].mean() > 3 * diff[:100].mean() + 1


def test_verify_fails_when_speech_is_uncaptioned(make_video, tmp_path):
    src = make_video(bursts=((0.5, 1.2), (1.8, 2.6)))
    half = tmp_path / "half.json"
    half.write_text(json.dumps({"cues": [CAPTIONS["cues"][0]]}))
    assert main(["verify", str(src), str(half)]) == 1


def test_overlay_only_has_alpha(make_video, captions, tmp_path):
    out = tmp_path / "ov.mov"
    assert main(["burn", str(make_video()), "-o", str(out), "--captions", str(captions),
                 "--overlay-only"]) == 0
    import subprocess
    fmt = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                          "stream=pix_fmt,codec_name", "-of", "csv=p=0", str(out)],
                         capture_output=True, text=True).stdout
    assert "prores" in fmt and "yuva" in fmt


def test_preview_and_sheet(make_video, captions, tmp_path):
    src = make_video()
    png = tmp_path / "p.png"
    assert main(["preview", str(src), str(captions), "--at", "0.7", "-o", str(png)]) == 0
    assert Image.open(png).size == (180, 320)
    sheet = tmp_path / "s.jpg"
    assert main(["sheet", str(src), "-o", str(sheet), "--count", "4", "--cols", "2"]) == 0
    assert Image.open(sheet).size == (400, 712)
