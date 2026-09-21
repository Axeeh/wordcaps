# wordcaps

Open source CLI and Python package: word-by-word karaoke captions for any video,
transcribed locally with Whisper and burned in with ffmpeg. Public repository,
so everything here (code, comments, docs, commit messages) is in **English**.

Read `README.md` for the user view and `docs/how-it-works.md` for the pipeline.

## Layout

- `src/wordcaps/`: `audio.py` (ffmpeg decode, RMS envelope, speech blocks),
  `transcribe.py` (whisper.cpp and faster-whisper backends), `align.py`
  (segment planning, word edge snapping), `cues.py` (grouping), `style.py` +
  `presets/*.toml`, `render.py` (Pillow frames, cached by state), `video.py`
  (probe, burn, alpha overlay, preview, contact sheet), `export.py`
  (SRT/VTT/ASS), `verify.py` (speech coverage), `cli.py`.
- `tests/`: pytest. Clips are generated with ffmpeg in `conftest.py`, no media
  is committed. The real-Whisper test only runs with `WORDCAPS_TEST_MODEL`.
- `docs/demo.gif`, `docs/emphasis.png`: README assets, made from synthetic
  voices (macOS `say`) over a gradient. Never use client footage or voices.

## Commands

```bash
uv venv .venv.nosync -p 3.12 && ln -sfn .venv.nosync .venv   # venv kept out of iCloud
uv pip install -p .venv.nosync -e ".[dev]"
.venv/bin/ruff check src tests
.venv/bin/python -m pytest -q
.venv/bin/wordcaps doctor
```

Set `UV_CACHE_DIR` and `WORDCAPS_MODELS` to paths under `$TMPDIR` when the
sandbox blocks `~/.cache`. In a sandbox whisper.cpp cannot reach the GPU: the
backend retries on CPU by itself, that is expected.

## Rules

- Pipeline steps stay pure functions over `Word`/`Cue`; ffmpeg and file I/O
  only in `audio.py`, `video.py`, `models.py`, `whisper_models.py`.
- Style values are relative to the frame (fractions of width/height, multiples
  of the font size). A new option needs a default that leaves existing output
  unchanged.
- User-facing failures raise `WordcapsError` with an actionable message.
- Run ruff and the full test suite before every commit; add a test with every fix.
- No em dashes in docs or copy.
- This folder is its **own git repository** (ignored by the workspace repo).
  The GitHub remote is `github.com/Axeeh/wordcaps`: create it, push, tag or
  publish to PyPI only when the maintainer asks.
