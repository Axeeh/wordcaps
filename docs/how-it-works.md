# How wordcaps works

The pipeline has five steps. Each one lives in its own module and is a plain
function over plain data, so it can be tested and reused on its own.

```
video ─► audio.py ─► transcribe.py ─► align.py ─► cues.py ─► render.py + video.py ─► verify.py
         envelope    Whisper per      snap word   group into  draw frames, pipe      re-check the
         + speech    speech segment   edges onto  captions    them into ffmpeg       finished file
         blocks                       speech
```

## 1. Find the speech (`audio.py`)

The audio is decoded to 16 kHz mono and cut into 50 ms windows. For each
window wordcaps computes the RMS loudness in dBFS. Windows above the threshold
(-32 dBFS by default, or estimated from the noise floor with `--threshold auto`)
are speech.

Two clean-ups turn that into usable **speech blocks**:

- gaps up to 0.2 s are bridged, because the dip inside a double consonant or
  between two quick words is not a real pause;
- blocks shorter than 0.1 s are dropped (clicks, breaths).

## 2. Transcribe only where there is voice (`transcribe.py`, `align.plan_segments`)

Whisper decodes 30-second windows and has no notion of "nothing is being said
yet". Give it a clip that starts with a second of silence and it tends to
stretch the first words across that silence: they end up on screen early.

So wordcaps groups the speech blocks into **segments** (a pause longer than
1.5 s starts a new one) and transcribes each segment separately, starting
0.15 s before its first sound. The word times are then shifted back onto the
timeline of the original video.

With whisper.cpp, wordcaps asks for one token per segment (`-ml 1`) and joins
sub-word tokens back into words: a token that does not start with a space
continues the previous word. Bracketed tags such as `[BLANK_AUDIO]` are
dropped.

## 3. Snap word edges to the voice (`align.refine_words`)

For every word:

- if it **starts in silence** and speech begins before the word ends, the
  start moves to that speech onset;
- if it **ends in silence** and speech ended after the word started, the end
  moves back to that speech offset;
- overlaps with the previous word are removed and every word lasts at least
  80 ms;
- a word more than 0.3 s away from any speech is kept but reported: that is
  the typical shape of a Whisper hallucination ("Thanks for watching!" over
  silence).

Every change is logged (`-v` prints them all).

## 4. Group words into captions (`cues.py`)

A caption (cue) ends when adding the next word would exceed `max_words` or
`max_chars`, after a pause longer than `max_pause`, after the end of a
sentence, or after a comma once the cue has at least two words.

Then two timing rules make the karaoke feel continuous:

- inside a caption each word is stretched to the start of the next, so the
  highlight never blinks off between words;
- gaps between captions shorter than 0.3 s are closed, so captions do not
  flicker during a quick breath.

## 5. Render and encode (`render.py`, `video.py`)

Captions are drawn with Pillow, not with ffmpeg's `drawtext` or `subtitles`
filters. Many ffmpeg builds, Homebrew's included, ship without them, and a
per-word animation is simpler to express as code than as ASS tags.

For each frame the renderer computes a small **state**: which caption is
visible, its fade-in alpha, and for every word whether it is active, boxed and
how much it is scaled. Frames with the same state are identical, so rendered
frames are cached: a 60-second video usually needs a few hundred distinct
frames, not 3,600.

Line breaking reserves room for each word at its largest size (pop, emphasis,
box), so the layout never shifts while the highlight moves. When a caption
does not fit on one line, the most balanced two-line split wins, and ties go
to the shorter top line.

Frames are streamed as raw RGBA into ffmpeg's stdin and composited with the
`overlay` filter in a single pass. Nothing is written to disk in between.
`--overlay-only` sends the same frames to a ProRes 4444 encoder instead, which
keeps the alpha channel for video editors.

## 6. Verify the result (`verify.py`)

The finished file goes back through step 1. wordcaps samples every speech
block every 50 ms and checks that some caption is on screen at that moment
(with 0.1 s of tolerance at the edges). Any uncovered stretch is printed and
the command exits with status 1. Captions that sit entirely over silence are
reported as notes.

This check is independent of Whisper on purpose: it catches phrases that got
dropped during transcription, captions deleted by mistake while editing the
JSON, and timings typed wrong by hand.
