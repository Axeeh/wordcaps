# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[semantic versioning](https://semver.org/).

## [Unreleased]

### Fixed

- faster-whisper backend: hyphenated words ("word-by-word") are joined into one
  word instead of being split into pieces across captions.
- faster-whisper backend: a model that cannot be downloaded or loaded now gives
  a short, actionable error instead of a Python traceback.

## [0.1.0] - 2026-09-21

### Added

- `wordcaps burn`: transcribe a video and burn in word-by-word karaoke captions
  in a single ffmpeg pass, with an editable JSON captions file.
- Silence-aware transcription: speech is detected from the loudness envelope
  and transcribed segment by segment, so leading silence cannot shift words.
- Word edges snapped onto speech onsets and offsets, with a log of every change
  and a warning for words far from any speech.
- Speech coverage check on the finished video (`wordcaps verify`, run
  automatically after `burn`).
- Backends: whisper.cpp (with automatic CPU fallback) and faster-whisper.
- Six style presets (`reel`, `box`, `pop`, `ocean`, `landscape`, `minimal`),
  TOML styles with `extends`, `--set` overrides and emphasis words.
- `--overlay-only` export as ProRes 4444 with alpha for video editors.
- SRT, WebVTT and ASS export; the ASS keeps the per-word highlight.
- `preview`, `sheet`, `styles`, `models` and `doctor` commands.
- Resumable model downloads.
