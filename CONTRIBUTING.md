# Contributing

Thanks for helping. Bug reports with a short clip that reproduces the problem
are the most useful contribution of all.

## Set up

```bash
git clone https://github.com/Axeeh/wordcaps
cd wordcaps
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
```

You also need `ffmpeg` on your PATH.

## Run the checks

```bash
ruff check src tests
pytest
```

The test suite builds its own tiny clips with ffmpeg (color bars plus tone
bursts standing in for speech), so it needs no model and runs in a couple of
seconds. The one test that runs real Whisper is skipped unless you point it at
a model (macOS only, it uses `say` to make the audio):

```bash
wordcaps models download base
WORDCAPS_TEST_MODEL=~/.cache/wordcaps/models/ggml-base.bin pytest -m whisper
```

## Guidelines

- Keep the pipeline steps as plain functions over `Word` and `Cue`, with no
  I/O, so they stay easy to test. ffmpeg calls belong in `audio.py` and
  `video.py`.
- New style options go in the `Style` dataclass with a default that keeps
  existing output unchanged, and should be relative to the frame size.
- Add a test for every bug fix.
- User-facing errors raise `WordcapsError` with a message that says what to do.

## Releasing (maintainers)

1. Bump `version` in `pyproject.toml` and `src/wordcaps/__init__.py`, and
   update `CHANGELOG.md`.
2. Tag and push: `git tag v0.2.0 && git push --tags`.
3. The `release` workflow builds the package and publishes it to PyPI through
   trusted publishing (configure the `wordcaps` project on PyPI once, with this
   repository and the `release.yml` workflow as trusted publisher).
