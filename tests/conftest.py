import shutil
import subprocess

import pytest

HAS_FFMPEG = bool(shutil.which("ffmpeg") and shutil.which("ffprobe"))


@pytest.fixture
def make_video(tmp_path):
    """Build a small test clip: moving color bars plus tone bursts as 'speech'."""
    if not HAS_FFMPEG:
        pytest.skip("ffmpeg not installed")

    def _make(width=180, height=320, duration=3.0, fps=30, bursts=((0.5, 1.2), (1.8, 2.6))):
        # a 440 Hz tone gated on inside the bursts, silence elsewhere
        gate = "+".join(f"between(t,{a},{b})" for a, b in bursts) or "0"
        out = tmp_path / f"clip_{width}x{height}.mp4"
        subprocess.run(
            ["ffmpeg", "-v", "error", "-y",
             "-f", "lavfi", "-i", f"testsrc2=s={width}x{height}:r={fps}:d={duration}",
             "-f", "lavfi", "-i", f"aevalsrc='0.5*sin(2*PI*440*t)*({gate})':s=16000:d={duration}",
             "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
             "-c:a", "aac", "-shortest", str(out)],
            check=True,
        )
        return out

    return _make
