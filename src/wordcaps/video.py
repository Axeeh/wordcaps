"""ffmpeg plumbing: probing, burning captions in, alpha overlays, previews."""

from __future__ import annotations

import json
import math
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path

from PIL import Image, ImageDraw

from .audio import require_tool
from .models import WordcapsError
from .render import OverlayRenderer


@dataclass
class VideoInfo:
    width: int
    height: int
    fps: Fraction
    duration: float
    has_audio: bool

    @property
    def frame_count(self) -> int:
        return max(1, math.ceil(self.duration * self.fps - 1e-6))


def _rotation(stream: dict) -> int:
    for sd in stream.get("side_data_list", []) or []:
        if "rotation" in sd:
            return int(float(sd["rotation"]))
    return int(float((stream.get("tags") or {}).get("rotate", 0)))


def probe(path: str | Path) -> VideoInfo:
    """Display size (after rotation metadata), frame rate and duration."""
    cmd = [require_tool("ffprobe"), "-v", "error", "-show_streams", "-show_format",
           "-of", "json", str(path)]
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        raise WordcapsError(f"cannot read {path}:\n{res.stderr.strip()}")
    data = json.loads(res.stdout)
    streams = data.get("streams", [])
    video = next((s for s in streams if s.get("codec_type") == "video"), None)
    if video is None:
        raise WordcapsError(f"{path} has no video stream")
    w, h = int(video["width"]), int(video["height"])
    if abs(_rotation(video)) % 180 == 90:
        w, h = h, w
    fps = Fraction(video.get("avg_frame_rate") or "0/1")
    if fps <= 0:
        fps = Fraction(video.get("r_frame_rate") or "30/1")
    fps = fps.limit_denominator(1001)
    duration = float(video.get("duration") or data.get("format", {}).get("duration") or 0)
    if duration <= 0:
        raise WordcapsError(f"cannot tell the duration of {path}")
    has_audio = any(s.get("codec_type") == "audio" for s in streams)
    return VideoInfo(w, h, fps, duration, has_audio)


def _pipe_frames(cmd: list[str], renderer: OverlayRenderer, count: int, label: str) -> None:
    with tempfile.TemporaryFile() as err:
        proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=err)
        assert proc.stdin is not None
        last = 0.0
        try:
            for n, frame in enumerate(renderer.frames(count)):
                proc.stdin.write(frame)
                now = time.monotonic()
                if now - last > 0.5 or n == count - 1:
                    last = now
                    print(f"\r{label} {(n + 1) * 100 // count:3d}%", end="", file=sys.stderr,
                          flush=True)
            proc.stdin.close()
        except BrokenPipeError:
            pass
        code = proc.wait()
        print(file=sys.stderr)
        if code != 0:
            err.seek(0)
            raise WordcapsError(f"ffmpeg failed:\n{err.read().decode(errors='replace')[-3000:]}")


def _raw_input(info: VideoInfo) -> list[str]:
    return ["-f", "rawvideo", "-pix_fmt", "rgba", "-s", f"{info.width}x{info.height}",
            "-framerate", f"{info.fps.numerator}/{info.fps.denominator}", "-i", "pipe:0"]


def burn(src: str | Path, dst: str | Path, renderer: OverlayRenderer, info: VideoInfo,
         *, crf: int = 18, preset: str = "medium") -> None:
    """Composite the captions over ``src`` and encode H.264 + AAC."""
    cmd = [require_tool("ffmpeg"), "-v", "error", "-y", "-i", str(src), *_raw_input(info),
           "-filter_complex", "[0:v][1:v]overlay=0:0:eof_action=pass:format=auto[v]",
           "-map", "[v]", "-map", "0:a?",
           "-c:v", "libx264", "-preset", preset, "-crf", str(crf), "-pix_fmt", "yuv420p",
           "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(dst)]
    _pipe_frames(cmd, renderer, info.frame_count, "burning")


def export_overlay(dst: str | Path, renderer: OverlayRenderer, info: VideoInfo) -> None:
    """Write only the captions, with alpha, as ProRes 4444 for video editors."""
    cmd = [require_tool("ffmpeg"), "-v", "error", "-y", *_raw_input(info),
           "-c:v", "prores_ks", "-profile:v", "4444", "-pix_fmt", "yuva444p10le",
           "-vendor", "apl0", str(dst)]
    _pipe_frames(cmd, renderer, info.frame_count, "overlay")


def grab_frame(src: str | Path, t: float) -> Image.Image:
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "f.png"
        cmd = [require_tool("ffmpeg"), "-v", "error", "-ss", f"{t:.3f}", "-i", str(src),
               "-frames:v", "1", "-y", str(out)]
        res = subprocess.run(cmd, capture_output=True, text=True)
        if res.returncode != 0 or not out.is_file():
            raise WordcapsError(f"cannot read a frame at {t:.2f}s from {src}")
        return Image.open(out).convert("RGBA")


def preview(src: str | Path, renderer: OverlayRenderer, t: float) -> Image.Image:
    """One frame of ``src`` with the captions drawn on top."""
    frame = grab_frame(src, t)
    if frame.size != (renderer.W, renderer.H):
        frame = frame.resize((renderer.W, renderer.H))
    frame.alpha_composite(renderer.frame_image(t))
    return frame.convert("RGB")


def contact_sheet(src: str | Path, count: int = 24, cols: int = 6,
                  thumb_width: int = 200) -> Image.Image:
    """Evenly spaced thumbnails with timestamps, to eyeball a finished video."""
    info = probe(src)
    th = round(thumb_width * info.height / info.width)
    rows = math.ceil(count / cols)
    sheet = Image.new("RGB", (thumb_width * cols, th * rows), (18, 18, 18))
    draw = ImageDraw.Draw(sheet)
    for i in range(count):
        t = info.duration * (i + 0.5) / count
        im = grab_frame(src, t).convert("RGB").resize((thumb_width, th), Image.LANCZOS)
        x, y = thumb_width * (i % cols), th * (i // cols)
        sheet.paste(im, (x, y))
        draw.rectangle([x, y, x + 52, y + 16], fill=(0, 0, 0))
        draw.text((x + 4, y + 3), f"{t:.1f}s", fill=(255, 235, 0))
    return sheet
