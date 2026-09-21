"""Speech-to-text backends that return word-level timestamps.

* ``whisper.cpp`` (default): runs the ``whisper-cli`` binary, fast on Apple
  Silicon, no Python ML stack needed.
* ``faster-whisper``: pure pip install (``pip install wordcaps[faster-whisper]``),
  handy on Linux and Windows.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Protocol

from . import whisper_models
from .align import plan_segments
from .audio import Analysis, analyze, extract_wav
from .models import Word, WordcapsError

WHISPER_CPP_BINARIES = ("whisper-cli", "whisper-cpp")


class Backend(Protocol):
    name: str

    def transcribe(self, wav: Path, language: str | None) -> list[Word]: ...


def merge_tokens(tokens: list[tuple[float, float, str]]) -> list[Word]:
    """Join sub-word tokens into words.

    whisper.cpp emits one token per segment with ``-ml 1``; a token that does
    not start with a space continues the previous word ("fighi" + "ssima").
    Bracketed non-speech tags such as ``[BLANK_AUDIO]`` are dropped.
    """
    out: list[Word] = []
    for start, end, text in tokens:
        bare = text.strip()
        if not bare or (bare.startswith("[") and bare.endswith("]")):
            continue
        if text.startswith(" ") or not out:
            out.append(Word(bare, start, end))
        else:
            out[-1].end = end
            out[-1].text += bare
    return out


class WhisperCpp:
    name = "whisper.cpp"

    def __init__(self, model: str = "base", *, binary: str | None = None,
                 gpu: bool = True, threads: int | None = None):
        self.model = whisper_models.resolve(model)
        self.binary = binary or next(
            (b for b in map(shutil.which, WHISPER_CPP_BINARIES) if b), None
        )
        if not self.binary:
            raise WordcapsError(
                "whisper.cpp not found (whisper-cli). Install it "
                "(macOS: brew install whisper-cpp) or use --backend faster-whisper."
            )
        self.gpu, self.threads = gpu, threads

    def _run(self, wav: Path, language: str | None, base: Path) -> subprocess.CompletedProcess:
        cmd = [self.binary, "-m", str(self.model), "-f", str(wav),
               "-l", language or "auto", "-ml", "1", "-oj", "-of", str(base)]
        if not self.gpu:
            cmd.append("-ng")
        if self.threads:
            cmd += ["-t", str(self.threads)]
        return subprocess.run(cmd, capture_output=True, text=True)

    def transcribe(self, wav: Path, language: str | None) -> list[Word]:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp) / "out"
            res = self._run(wav, language, base)
            if res.returncode != 0 and self.gpu:
                # no usable GPU (VMs, sandboxes, old drivers): stay on the CPU from now on
                self.gpu = False
                res = self._run(wav, language, base)
            if res.returncode != 0:
                raise WordcapsError(f"whisper.cpp failed:\n{res.stderr.strip()[-2000:]}")
            data = json.loads(base.with_suffix(".json").read_text(encoding="utf-8"))
        tokens = [
            (s["offsets"]["from"] / 1000.0, s["offsets"]["to"] / 1000.0, s["text"])
            for s in data.get("transcription", [])
        ]
        return merge_tokens(tokens)


class FasterWhisper:
    name = "faster-whisper"

    def __init__(self, model: str = "base", *, device: str = "auto", compute_type: str = "int8"):
        try:
            from faster_whisper import WhisperModel
        except ImportError as e:
            raise WordcapsError(
                "faster-whisper is not installed: pip install 'wordcaps[faster-whisper]'"
            ) from e
        self._model = WhisperModel(model, device=device, compute_type=compute_type)

    def transcribe(self, wav: Path, language: str | None) -> list[Word]:
        segments, _ = self._model.transcribe(str(wav), language=language, word_timestamps=True)
        return [
            Word(w.word.strip(), float(w.start), float(w.end))
            for seg in segments for w in (seg.words or []) if w.word.strip()
        ]


def get_backend(name: str = "auto", model: str = "base") -> Backend:
    if name in ("whisper.cpp", "whispercpp", "cpp"):
        return WhisperCpp(model)
    if name in ("faster-whisper", "faster"):
        return FasterWhisper(model)
    if name != "auto":
        raise WordcapsError(f"unknown backend '{name}' (use whisper.cpp or faster-whisper)")
    errors = []
    for cls in (WhisperCpp, FasterWhisper):
        try:
            return cls(model)
        except WordcapsError as e:
            errors.append(f"  {cls.name}: {e}")
    raise WordcapsError("no speech-to-text backend available:\n" + "\n".join(errors))


def transcribe_media(
    src: str | Path,
    backend: Backend,
    *,
    language: str | None = None,
    threshold: float | None = -32.0,
    progress: Callable[[str], None] | None = None,
) -> tuple[list[Word], Analysis]:
    """Transcribe a media file segment by segment, cutting away dead air.

    Returns words on the timeline of ``src`` plus the loudness analysis, which
    the caller needs for :func:`wordcaps.align.refine_words`.
    """
    with tempfile.TemporaryDirectory() as tmp:
        full = extract_wav(src, Path(tmp) / "full.wav")
        analysis = analyze(full, threshold=threshold)
        segments = plan_segments(analysis.blocks)
        words: list[Word] = []
        for i, (s, e) in enumerate(segments, 1):
            if progress:
                progress(f"transcribing segment {i}/{len(segments)} ({s:.1f}s-{e:.1f}s)")
            seg = extract_wav(full, Path(tmp) / f"seg{i}.wav", start=s, duration=e - s)
            for w in backend.transcribe(seg, language):
                words.append(Word(w.text, round(w.start + s, 4), round(w.end + s, 4)))
    return words, analysis
