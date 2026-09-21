"""Audio extraction and speech detection from the RMS loudness envelope.

Whisper is good at telling *which* words were said and noticeably worse at
telling exactly *when*. The loudness envelope is the opposite: it knows
nothing about words but it marks where sound starts and stops to within one
analysis hop. wordcaps uses both.
"""

from __future__ import annotations

import shutil
import subprocess
import wave
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from .models import WordcapsError

SAMPLE_RATE = 16000


def require_tool(name: str) -> str:
    path = shutil.which(name)
    if not path:
        raise WordcapsError(
            f"{name} not found on PATH. Install ffmpeg "
            "(macOS: brew install ffmpeg, Debian/Ubuntu: apt install ffmpeg)."
        )
    return path


def extract_wav(
    src: str | Path,
    dest: str | Path,
    *,
    start: float | None = None,
    duration: float | None = None,
    sample_rate: int = SAMPLE_RATE,
) -> Path:
    """Decode the audio of ``src`` into a mono 16-bit WAV."""
    cmd = [require_tool("ffmpeg"), "-v", "error", "-nostdin"]
    if start:
        cmd += ["-ss", f"{start:.3f}"]
    cmd += ["-i", str(src)]
    if duration:
        cmd += ["-t", f"{duration:.3f}"]
    cmd += ["-vn", "-ac", "1", "-ar", str(sample_rate), "-c:a", "pcm_s16le", "-y", str(dest)]
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        raise WordcapsError(f"ffmpeg could not read the audio of {src}:\n{res.stderr.strip()}")
    return Path(dest)


def read_wav(path: str | Path) -> tuple[np.ndarray, int]:
    """Return mono float samples in [-1, 1] and the sample rate."""
    with wave.open(str(path)) as w:
        sr, n, ch = w.getframerate(), w.getnframes(), w.getnchannels()
        if w.getsampwidth() != 2:
            raise WordcapsError(f"{path}: expected 16-bit PCM")
        data = np.frombuffer(w.readframes(n), dtype=np.int16).astype(np.float64) / 32768.0
    if ch > 1:
        data = data.reshape(-1, ch).mean(axis=1)
    return data, sr


def rms_db(samples: np.ndarray, sample_rate: int, hop: float = 0.05) -> np.ndarray:
    """Loudness in dBFS, one value per ``hop`` seconds (the tail is dropped)."""
    n = max(1, int(sample_rate * hop))
    frames = len(samples) // n
    if frames == 0:
        return np.empty(0)
    x = samples[: frames * n].reshape(frames, n)
    rms = np.sqrt((x**2).mean(axis=1) + 1e-12)
    return 20 * np.log10(rms + 1e-9)


def auto_threshold(db: np.ndarray) -> float:
    """Pick a speech threshold between the noise floor and the speech level."""
    if len(db) == 0:
        return -32.0
    floor, peak = np.percentile(db, 10), np.percentile(db, 95)
    if peak - floor < 12:  # almost no dynamic range: someone talking non-stop
        return float(peak - 12)
    return float(floor + 0.45 * (peak - floor))


def speech_blocks(
    db: np.ndarray,
    hop: float,
    threshold: float | None = -32.0,
    max_gap: float = 0.2,
    min_length: float = 0.10,
) -> list[tuple[float, float]]:
    """Stretches of sound above ``threshold``, in seconds.

    Gaps up to ``max_gap`` are bridged (the dip inside a double consonant
    must not split a word) and blocks shorter than ``min_length`` dropped.
    ``threshold=None`` estimates it from the envelope.
    """
    if len(db) == 0:
        return []
    if threshold is None:
        threshold = auto_threshold(db)
    on = (db > threshold).astype(np.int8)
    edges = np.flatnonzero(np.diff(np.concatenate(([0], on, [0]))))
    starts, ends = edges[0::2], edges[1::2]
    gap_frames = max(1, round(max_gap / hop))
    merged: list[list[int]] = []
    for s, e in zip(starts, ends, strict=True):
        if merged and s - merged[-1][1] <= gap_frames:
            merged[-1][1] = e
        else:
            merged.append([int(s), int(e)])
    return [
        (round(s * hop, 3), round(e * hop, 3)) for s, e in merged if (e - s) * hop > min_length
    ]


@dataclass
class Analysis:
    db: np.ndarray
    hop: float
    threshold: float
    blocks: list[tuple[float, float]]
    duration: float


def analyze(
    wav: str | Path, hop: float = 0.05, threshold: float | None = -32.0
) -> Analysis:
    samples, sr = read_wav(wav)
    db = rms_db(samples, sr, hop)
    thr = auto_threshold(db) if threshold is None else threshold
    return Analysis(db, hop, thr, speech_blocks(db, hop, thr), len(samples) / sr)
