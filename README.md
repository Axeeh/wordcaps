# wordcaps

**Word-by-word karaoke captions for any video, made on your machine.**

wordcaps transcribes a video with Whisper, lines every word up with the actual
voice, and burns animated captions into the video: the word being spoken lights
up as it is said. It works offline, costs nothing per minute, and gives you an
editable file in between, so you can fix a typo and re-render in seconds.

![Three caption styles on the same clip: reel, box and pop](docs/demo.gif)

It was built for vertical Reels, Shorts and TikToks, and works on any video:
landscape interviews, courses, square posts.

[![CI](https://github.com/Axeeh/wordcaps/actions/workflows/ci.yml/badge.svg)](https://github.com/Axeeh/wordcaps/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/wordcaps)](https://pypi.org/project/wordcaps/)
[![Python](https://img.shields.io/pypi/pyversions/wordcaps)](https://pypi.org/project/wordcaps/)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue)](LICENSE)

## Why another captioning tool

Most auto-captioning is either a paid cloud service or a script that trusts
Whisper's timestamps. Those timestamps are good at *which* words were said and
noticeably worse at *when*: on a clip that opens with a second of silence, the
first words routinely show up early. On a fast-cut vertical video that is the
difference between captions that feel glued to the voice and captions that
feel off.

wordcaps treats timing as the core problem:

- **Silence-aware transcription.** It finds speech in the loudness envelope
  first and hands Whisper only the stretches with voice, each starting 0.15 s
  before the first sound, so leading silence can't drag the words early.
- **Envelope snapping.** Word edges that fall in silence are moved onto the
  real speech onset or offset.
- **A coverage check on the output.** After rendering, wordcaps re-reads the
  audio of the finished file and tells you if any moment of speech has no
  caption on screen. It exits non-zero, so it also works in scripts.

How it works in detail: [docs/how-it-works.md](docs/how-it-works.md).

## Install

You need Python 3.11+ and [ffmpeg](https://ffmpeg.org). For speech-to-text,
pick one backend:

```bash
# macOS: whisper.cpp is fast on Apple Silicon
brew install ffmpeg whisper-cpp
pipx install wordcaps
wordcaps models download base
```

```bash
# Linux / Windows: faster-whisper, a pure pip install
pipx install "wordcaps[faster-whisper]"
```

Then check that everything is in place:

```bash
wordcaps doctor
```

## Quick start

```bash
wordcaps burn talk.mp4 --lang en
```

This writes `talk.captioned.mp4`, plus `talk.captioned.json` with every word
and its timing. Whisper will get a few words wrong: open the JSON, fix them,
and render again without transcribing:

```bash
wordcaps burn talk.mp4 --captions talk.captioned.json
```

The captions file keeps one caption per line, so it stays easy to edit:

```json
{
  "wordcaps": 1,
  "language": "en",
  "cues": [
    {"words": [["HI", 1.15, 1.23], ["EVERYONE", 1.23, 2.25]]},
    {"words": [["TODAY", 2.25, 2.43], ["I", 2.43, 2.51], ["WANT", 2.51, 2.74]]}
  ]
}
```

Each word is `[text, start, end]` in seconds. Add `"lines": [0, 2]` to a cue to
force a line break before its third word.

## Styles

```bash
wordcaps styles
```

| Style | For | Look |
|---|---|---|
| `reel` (default) | Reels, Shorts, TikTok | Bold caps, the spoken word turns yellow |
| `box` | Vertical | The spoken word sits on a colored box, with a small pop |
| `pop` | Vertical | Two words at a time, the spoken word grows and turns green |
| `ocean` | Vertical | Compact two-line captions with a blue highlight |
| `landscape` | 16:9 video | Sentence case, lower third, longer lines, punctuation kept |
| `minimal` | Anything | No outline, soft shadow, subtle highlight |

Sizes and positions are fractions of the frame, so every style works at any
resolution. Tweak any option from the command line:

```bash
wordcaps burn talk.mp4 --style box --set highlight=#FF4D8D --set max_words=2
```

Or keep your brand in a TOML file that starts from a preset
([example](examples/brand.toml)):

```toml
extends = "reel"
highlight = "#FF4D8D"
highlight_mode = "box"
emphasis = ["FREE", "TODAY"]   # these words get a box and a bouncy pop
```

```bash
wordcaps burn talk.mp4 --style brand.toml
wordcaps styles --show reel    # every option, with its current value
```

![An emphasis word popping in a colored box](docs/emphasis.png)

Iterate on a style without rendering the whole video:

```bash
wordcaps preview talk.mp4 talk.captioned.json --at 3.2 -o frame.png
```

## Using it with a video editor

Keep editing in Premiere, Final Cut, DaVinci or CapCut and let wordcaps do only
the captions:

```bash
# captions only, transparent background, ProRes 4444
wordcaps burn talk.mp4 --overlay-only -o captions.mov

# or standard subtitle files
wordcaps export talk.captioned.json -o talk.srt
wordcaps export talk.captioned.json -o talk.ass --size 1080x1920
```

The `.ass` export reproduces the word-by-word highlight (one event per word);
the box and pop animations exist only in burned-in video.

## All commands

| Command | What it does |
|---|---|
| `wordcaps burn VIDEO` | Transcribe (or read `--captions`) and burn captions in |
| `wordcaps transcribe VIDEO` | Only write the editable captions file |
| `wordcaps preview VIDEO CAPTIONS --at T` | Render one frame, to check a style |
| `wordcaps export CAPTIONS -o file.srt` | Convert to SRT, VTT or ASS |
| `wordcaps verify VIDEO CAPTIONS` | Report speech with no caption on screen |
| `wordcaps sheet VIDEO` | Contact sheet of evenly spaced frames |
| `wordcaps styles` | List presets, `--show NAME` for all options |
| `wordcaps models list / download NAME` | Manage whisper.cpp models |
| `wordcaps doctor` | Check ffmpeg, backends, models and fonts |

Useful flags: `--lang` (default auto-detect), `--model` (`base`, `small`,
`large-v3-turbo`, or a path to a `.bin`), `--backend`, `--threshold` (speech
level in dBFS, or `auto` for noisy recordings), `--crf` for output quality.

## Choosing a model

| Model | Download | Notes |
|---|---|---|
| `base` | 142 MB | Fast, fine for clear English |
| `small` | 466 MB | Good default for other languages |
| `large-v3-turbo` | 1.6 GB | Best accuracy, still quick on Apple Silicon |

Models are stored in `~/.cache/wordcaps/models` (override with
`WORDCAPS_MODELS`). Downloads resume if the connection drops.

## Limitations

- HDR sources are captioned but not tone mapped: export SDR first if colors
  look washed out.
- One speaker style per video: there is no per-speaker color yet.
- The loudness-based checks assume speech is louder than the background. With
  loud music under the voice, try `--threshold auto` or a higher value.

## Roadmap

- Per-speaker colors (diarization)
- Automatic emphasis on keywords
- Emoji and title overlays
- A Python API reference

Ideas and pull requests are welcome, see [CONTRIBUTING.md](CONTRIBUTING.md).

## Credits

- Speech recognition: [whisper.cpp](https://github.com/ggml-org/whisper.cpp)
  and [faster-whisper](https://github.com/SYSTRAN/faster-whisper), on OpenAI's Whisper models
- Bundled font: [Montserrat](https://github.com/JulietaUla/Montserrat), SIL Open Font License 1.1
- Video I/O: [ffmpeg](https://ffmpeg.org)

## License

MIT, see [LICENSE](LICENSE). The bundled Montserrat fonts are under the
[SIL Open Font License](src/wordcaps/fonts/OFL.txt).
