"""Command line interface."""

from __future__ import annotations

import argparse
import importlib.util
import shutil
import subprocess
import sys
import tempfile
import tomllib
from pathlib import Path

from . import __version__, whisper_models
from .align import refine_words
from .audio import analyze, extract_wav
from .cues import group_words
from .export import to_ass, to_srt, to_vtt
from .fonts import BUNDLED, font_file
from .models import Cue, Word, WordcapsError, load_captions, save_captions
from .render import OverlayRenderer
from .style import Style, load_style, preset_names
from .verify import check_coverage


def log(msg: str) -> None:
    print(msg, file=sys.stderr)


# ---------------------------------------------------------------- helpers


def _parse_set(items: list[str] | None) -> dict:
    out = {}
    for item in items or []:
        if "=" not in item:
            raise WordcapsError(f"--set expects key=value, got {item!r}")
        k, v = item.split("=", 1)
        try:
            out[k.strip()] = tomllib.loads(f"v = {v}")["v"]
        except tomllib.TOMLDecodeError:
            out[k.strip()] = v
    return out


def _style(args) -> Style:
    return load_style(args.style, _parse_set(getattr(args, "set", None)))


def _threshold(value: str) -> float | None:
    if value == "auto":
        return None
    try:
        return float(value)
    except ValueError as e:
        raise argparse.ArgumentTypeError("threshold is a dBFS number or 'auto'") from e


def _group(words: list[Word], style: Style) -> list[Cue]:
    return group_words(
        words,
        max_words=style.max_words,
        max_chars=style.max_chars,
        max_pause=style.max_pause,
        uppercase=style.uppercase,
        strip_punctuation=style.strip_punctuation,
    )


def _cues_from_file(path: str, style: Style) -> tuple[list[Cue], str | None]:
    cues, loose, lang = load_captions(path)
    return (cues or _group(loose, style)), lang


def _transcribe(args, style: Style) -> tuple[list[Cue], str | None]:
    from .transcribe import get_backend, transcribe_media

    backend = get_backend(args.backend, args.model)
    log(f"speech-to-text: {backend.name}, model {args.model}")
    lang = None if args.lang == "auto" else args.lang
    words, analysis = transcribe_media(args.input, backend, language=lang,
                                       threshold=args.threshold, progress=log)
    if not words:
        raise WordcapsError("no speech found. Try --threshold auto or a lower value like -40.")
    words, adjustments = refine_words(words, analysis.blocks)
    for a in adjustments:
        if "check" in a.note or args.verbose:
            log(f"  {a.word!r}: {a.before[0]:.2f}-{a.before[1]:.2f} -> "
                f"{a.after[0]:.2f}-{a.after[1]:.2f} ({a.note})")
    cues = _group(words, style)
    log(f"{len(words)} words in {len(cues)} captions")
    return cues, lang


def _coverage(video: str, cues: list[Cue], threshold: float | None) -> bool:
    with tempfile.TemporaryDirectory() as tmp:
        wav = extract_wav(video, Path(tmp) / "a.wav")
        analysis = analyze(wav, threshold=threshold)
    rep = check_coverage(analysis.blocks, cues)
    if rep.ok:
        log(f"verify: ok, all {len(rep.blocks)} speech blocks have captions")
    else:
        log(f"verify: {rep.uncovered_seconds:.2f}s of speech without captions:")
        for s, e in rep.uncovered:
            log(f"  {s:7.2f}s - {e:7.2f}s")
    for c in rep.silent_cues:
        log(f"  note: caption over silence at {c.start:.2f}s: {c.text!r}")
    return rep.ok


# ---------------------------------------------------------------- commands


def cmd_burn(args) -> int:
    from .video import burn, export_overlay, probe

    style = _style(args)
    info = probe(args.input)
    src = Path(args.input)
    if args.overlay_only:
        out = Path(args.output or src.with_name(f"{src.stem}.captions.mov"))
    else:
        out = Path(args.output or src.with_name(f"{src.stem}.captioned.mp4"))
    if out.resolve() == src.resolve():
        raise WordcapsError("output would overwrite the input")

    if args.captions:
        cues, lang = _cues_from_file(args.captions, style)
    else:
        cues, lang = _transcribe(args, style)
        cap = out.with_name(f"{out.stem}.json")
        save_captions(cap, cues, lang)
        log(f"captions saved to {cap} (edit it and pass --captions to re-render)")

    log(f"{info.width}x{info.height} @ {float(info.fps):.3f} fps, {info.duration:.1f}s, "
        f"style {style.name}")
    renderer = OverlayRenderer(cues, style, info.width, info.height, float(info.fps))
    if args.overlay_only:
        export_overlay(out, renderer, info)
    else:
        burn(src, out, renderer, info, crf=args.crf, preset=args.preset)
    log(f"wrote {out}")
    if args.verify and info.has_audio and not args.overlay_only:
        return 0 if _coverage(str(out), cues, args.threshold) else 1
    return 0


def cmd_transcribe(args) -> int:
    style = _style(args)
    cues, lang = _transcribe(args, style)
    src = Path(args.input)
    out = Path(args.output or src.with_name(f"{src.stem}.json"))
    save_captions(out, cues, lang)
    log(f"wrote {out}")
    return 0


def cmd_preview(args) -> int:
    from .video import preview, probe

    style = _style(args)
    info = probe(args.input)
    cues, _ = _cues_from_file(args.captions, style)
    t = args.at
    if t is None:
        c = cues[0]
        t = c.words[min(1, len(c.words) - 1)].start + 0.2
    renderer = OverlayRenderer(cues, style, info.width, info.height, float(info.fps))
    out = args.output or "preview.png"
    preview(args.input, renderer, t).save(out)
    log(f"wrote {out} (t = {t:.2f}s)")
    return 0


def cmd_export(args) -> int:
    style = _style(args)
    cues, _ = _cues_from_file(args.captions, style)
    fmt = args.format or (Path(args.output).suffix.lstrip(".") if args.output else "srt")
    if fmt == "srt":
        text = to_srt(cues)
    elif fmt == "vtt":
        text = to_vtt(cues)
    elif fmt == "ass":
        w, h = (int(x) for x in args.size.lower().split("x"))
        text = to_ass(cues, style, w, h)
    else:
        raise WordcapsError(f"unknown format {fmt!r} (srt, vtt, ass)")
    if args.output:
        Path(args.output).write_text(text, encoding="utf-8")
        log(f"wrote {args.output}")
    else:
        sys.stdout.write(text)
    return 0


def cmd_verify(args) -> int:
    cues, _ = _cues_from_file(args.captions, load_style("reel"))
    return 0 if _coverage(args.video, cues, args.threshold) else 1


def cmd_sheet(args) -> int:
    from .video import contact_sheet

    out = args.output or f"{Path(args.video).stem}.sheet.jpg"
    contact_sheet(args.video, args.count, args.cols).save(out, quality=90)
    log(f"wrote {out}")
    return 0


def cmd_styles(args) -> int:
    if args.show:
        sys.stdout.write(load_style(args.show).to_toml())
        return 0
    for name in preset_names():
        print(f"  {name:<10} {load_style(name).description}")
    print("\nShow all options of one: wordcaps styles --show reel")
    return 0


def cmd_models(args) -> int:
    if args.action == "download":
        path = whisper_models.download(args.name, force=args.force)
        log(f"ready: {path}")
        return 0
    have = {p.name for p in whisper_models.installed()}
    print(f"models folder: {whisper_models.models_dir()}")
    for name, size in whisper_models.KNOWN.items():
        mark = "installed" if f"ggml-{name}.bin" in have else ""
        print(f"  {name:<16} {size:>7}  {mark}")
    return 0


def cmd_doctor(args) -> int:
    ok = True

    def row(label: str, good: bool, detail: str) -> None:
        nonlocal ok
        print(f"  [{'ok' if good else '--'}] {label:<16} {detail}")

    for tool in ("ffmpeg", "ffprobe"):
        path = shutil.which(tool)
        ok &= bool(path)
        row(tool, bool(path), path or "missing (required)")
    if shutil.which("ffmpeg"):
        enc = subprocess.run(["ffmpeg", "-hide_banner", "-encoders"],
                             capture_output=True, text=True).stdout
        for codec, use in (("libx264", "burn"), ("prores_ks", "--overlay-only")):
            row(codec, codec in enc, f"needed for {use}")
    cpp = shutil.which("whisper-cli") or shutil.which("whisper-cpp")
    row("whisper.cpp", bool(cpp), cpp or "not installed (brew install whisper-cpp)")
    models = whisper_models.installed()
    row("ggml models", bool(models),
        ", ".join(p.stem[5:] for p in models) or "none (wordcaps models download base)")
    fw = importlib.util.find_spec("faster_whisper") is not None
    row("faster-whisper", fw,
        "installed" if fw else "optional: pip install 'wordcaps[faster-whisper]'")
    for name in BUNDLED:
        row("font", bool(font_file(name)), name)
    if not (cpp and models) and not fw:
        print("\nNo speech-to-text backend ready: you can still burn an existing captions file.")
    return 0 if ok else 1


# ---------------------------------------------------------------- parser


def _add_style_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--style", default="reel",
                   help="preset name or .toml file (default: reel). See: wordcaps styles")
    p.add_argument("--set", action="append", metavar="KEY=VALUE",
                   help="override one style option, e.g. --set highlight=#00E5FF (repeatable)")


def _add_stt_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--lang", default="auto",
                   help="spoken language code, e.g. en, it (default: auto)")
    p.add_argument("--backend", default="auto", help="whisper.cpp, faster-whisper or auto")
    p.add_argument("--model", default="base", help="model name or .bin path (default: base)")
    p.add_argument("-v", "--verbose", action="store_true", help="log every timing correction")


def _add_threshold(p: argparse.ArgumentParser) -> None:
    p.add_argument("--threshold", type=_threshold, default=-32.0,
                   help="speech level in dBFS, or 'auto' (default: -32)")


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="wordcaps",
        description="Word-by-word karaoke captions for any video, made locally with Whisper.",
    )
    ap.add_argument("--version", action="version", version=f"wordcaps {__version__}")
    sub = ap.add_subparsers(dest="command", required=True, metavar="command")

    p = sub.add_parser("burn", help="transcribe and burn captions into a video")
    p.add_argument("input")
    p.add_argument("-o", "--output")
    p.add_argument("--captions", help="use this captions file instead of transcribing")
    p.add_argument("--overlay-only", action="store_true",
                   help="write only the captions with alpha (ProRes 4444 .mov) for editors")
    p.add_argument("--crf", type=int, default=18, help="x264 quality, lower is better (18)")
    p.add_argument("--preset", default="medium", help="x264 speed preset (medium)")
    p.add_argument("--no-verify", dest="verify", action="store_false",
                   help="skip the speech coverage check")
    _add_style_args(p)
    _add_stt_args(p)
    _add_threshold(p)
    p.set_defaults(func=cmd_burn)

    p = sub.add_parser("transcribe", help="write an editable captions file")
    p.add_argument("input")
    p.add_argument("-o", "--output")
    _add_style_args(p)
    _add_stt_args(p)
    _add_threshold(p)
    p.set_defaults(func=cmd_transcribe)

    p = sub.add_parser("preview", help="render one frame to check a style")
    p.add_argument("input")
    p.add_argument("captions")
    p.add_argument("--at", type=float, help="time in seconds (default: during the first caption)")
    p.add_argument("-o", "--output")
    _add_style_args(p)
    p.set_defaults(func=cmd_preview)

    p = sub.add_parser("export", help="convert captions to SRT, VTT or ASS")
    p.add_argument("captions")
    p.add_argument("-o", "--output")
    p.add_argument("-f", "--format", choices=("srt", "vtt", "ass"))
    p.add_argument("--size", default="1080x1920", help="video size for ASS (1080x1920)")
    _add_style_args(p)
    p.set_defaults(func=cmd_export)

    p = sub.add_parser("verify", help="check that all speech in a video has captions")
    p.add_argument("video")
    p.add_argument("captions")
    _add_threshold(p)
    p.set_defaults(func=cmd_verify)

    p = sub.add_parser("sheet", help="contact sheet of a video, to review it at a glance")
    p.add_argument("video")
    p.add_argument("-o", "--output")
    p.add_argument("--count", type=int, default=24)
    p.add_argument("--cols", type=int, default=6)
    p.set_defaults(func=cmd_sheet)

    p = sub.add_parser("styles", help="list the built-in styles")
    p.add_argument("--show", metavar="NAME", help="print every option of a style as TOML")
    p.set_defaults(func=cmd_styles)

    p = sub.add_parser("models", help="list or download whisper.cpp models")
    p.add_argument("action", choices=("list", "download"), nargs="?", default="list")
    p.add_argument("name", nargs="?", default="base")
    p.add_argument("--force", action="store_true")
    p.set_defaults(func=cmd_models)

    p = sub.add_parser("doctor", help="check that ffmpeg, whisper and fonts are ready")
    p.set_defaults(func=cmd_doctor)
    return ap


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except WordcapsError as e:
        log(f"wordcaps: {e}")
        return 2
    except KeyboardInterrupt:
        log("interrupted")
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
