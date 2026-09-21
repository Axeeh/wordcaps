"""Render the caption layer as transparent RGBA frames with Pillow.

The captions are drawn here instead of with ffmpeg's ``drawtext`` or
``subtitles`` filters on purpose: many ffmpeg builds (Homebrew's included)
ship without them, and per-word karaoke animation is awkward to express in
ASS anyway. Frames only change when the visible state changes, so rendered
frames are cached and reused.
"""

from __future__ import annotations

from bisect import bisect_right
from collections import OrderedDict
from collections.abc import Iterator
from dataclasses import dataclass

from PIL import Image, ImageDraw, ImageFilter

from .fonts import load_font
from .models import Cue
from .style import Style

POP_TIME = 0.10        # seconds for the spoken word to grow in "pop"/"box" modes
EMPHASIS_TIME = 0.32   # seconds for an emphasis word to pop in
BOX_PAD_X, BOX_PAD_Y = 0.30, 0.22  # box padding around the outlined word, in font sizes


def ease_out(p: float, power: float = 3) -> float:
    return 1 - (1 - p) ** power


def ease_out_back(p: float, s: float = 2.4) -> float:
    p -= 1.0
    return 1 + (s + 1) * p**3 + s * p**2


def break_lines(
    widths: list[float], space: float, max_width: float, forced: list[int] | None = None
) -> list[list[int]]:
    """Split word indexes into lines.

    One line if it fits; otherwise the most balanced two-line split that fits
    (ties go to the shorter top line); otherwise greedy filling. ``forced``
    gives the first word of each line.
    """
    n = len(widths)
    if forced:
        bounds = [*forced, n]
        return [list(range(a, b)) for a, b in zip(bounds, bounds[1:], strict=False)]

    def span(a: int, b: int) -> float:
        return sum(widths[a:b]) + space * (b - a - 1)

    if n <= 1 or span(0, n) <= max_width:
        return [list(range(n))]
    best, cost = None, None
    for k in range(1, n):
        w1, w2 = span(0, k), span(k, n)
        if max(w1, w2) <= max_width and (cost is None or abs(w1 - w2) < cost):
            best, cost = k, abs(w1 - w2)
    if best is not None:
        return [list(range(best)), list(range(best, n))]
    lines, cur = [], [0]
    for i in range(1, n):
        if span(cur[0], i + 1) > max_width:
            lines.append(cur)
            cur = [i]
        else:
            cur.append(i)
    lines.append(cur)
    return lines


@dataclass(frozen=True)
class _WordState:
    active: bool
    boxed: bool
    scale: int  # percent


class OverlayRenderer:
    def __init__(self, cues: list[Cue], style: Style, width: int, height: int, fps: float):
        self.cues = sorted(cues, key=lambda c: c.start)
        self.style, self.W, self.H, self.fps = style, width, height, fps
        self.size = max(8, round(style.size * width))
        self.font = load_font(style.font, self.size, style.font_index)
        self.space = self.font.getlength(" ")
        self.pitch = style.line_spacing * self.size
        self.starts = [c.start for c in self.cues]
        self.emphasis = {e.casefold() for e in style.emphasis}
        self.layouts = [self._layout(c) for c in self.cues]
        self._cache: OrderedDict[tuple, bytes] = OrderedDict()
        self._empty = bytes(width * height * 4)

    # ---------------------------------------------------------------- layout

    def _is_emphasis(self, text: str) -> bool:
        return text.casefold() in self.emphasis

    def _slot(self, text: str) -> float:
        """Horizontal room a word needs at its largest, so nothing jumps."""
        st = self.style
        w = self.font.getlength(text)
        grow = 1.0
        if st.highlight_mode != "color":
            grow = max(grow, st.pop_scale)
        if self._is_emphasis(text):
            grow = max(grow, st.emphasis_scale)
        boxed = st.highlight_mode == "box" or self._is_emphasis(text)
        # the box may spill into the word gap, so reserve only half of its padding
        pad = (BOX_PAD_X + st.stroke) * self.size * grow if boxed else 0
        return w * grow + pad

    def _layout(self, cue: Cue) -> list[list[tuple[int, float]]]:
        """Lines of (word index, center x)."""
        slots = [self._slot(w.text) for w in cue.words]
        lines = break_lines(slots, self.space, self.style.max_width * self.W, cue.lines)
        out = []
        for idxs in lines:
            total = sum(slots[i] for i in idxs) + self.space * (len(idxs) - 1)
            x = (self.W - total) / 2
            row = []
            for i in idxs:
                row.append((i, x + slots[i] / 2))
                x += slots[i] + self.space
            out.append(row)
        return out

    # ---------------------------------------------------------------- state

    def cue_index(self, t: float) -> int | None:
        i = bisect_right(self.starts, t) - 1
        if i >= 0 and t < self.cues[i].end:
            return i
        return None

    def _state(self, t: float) -> tuple | None:
        i = self.cue_index(t)
        if i is None:
            return None
        st, cue = self.style, self.cues[i]
        alpha = 255
        if st.fade_in > 0 and t < cue.start + st.fade_in:
            alpha = max(0, min(255, round(255 * (t - cue.start) / st.fade_in)))
        words = []
        for w in cue.words:
            active = w.start <= t < w.end
            boxed = active and st.highlight_mode == "box"
            scale = 1.0
            if active and st.highlight_mode != "color":
                scale = 1 + (st.pop_scale - 1) * ease_out(min(1.0, (t - w.start) / POP_TIME))
            if self._is_emphasis(w.text) and t >= w.start:
                boxed = True
                p = min(1.0, (t - w.start) / EMPHASIS_TIME)
                scale = max(scale, 1 + (st.emphasis_scale - 1) * ease_out_back(p))
            words.append(_WordState(active, boxed, round(scale * 100)))
        return (i, alpha, tuple(words))

    # ---------------------------------------------------------------- drawing

    def _draw_cue(self, key: tuple) -> Image.Image:
        i, alpha, states = key
        st, cue = self.style, self.cues[i]
        n = len(self.layouts[i])
        base_y = st.baseline * self.H
        top = int(base_y - (n - 1) * self.pitch - self.size * 2.2)
        bottom = int(base_y + self.size * 1.2)
        top, bottom = max(0, top), min(self.H, bottom)
        region = (self.W, max(1, bottom - top))
        text = Image.new("RGBA", region, (0, 0, 0, 0))
        shadow = Image.new("RGBA", region, (0, 0, 0, 0))
        dt, ds = ImageDraw.Draw(text), ImageDraw.Draw(shadow)
        sh_alpha = round(255 * st.shadow_opacity)
        sh_fill = (0, 0, 0, sh_alpha)
        stroke_fill = (*st.stroke_color, 255)

        for row_n, row in enumerate(self.layouts[i]):
            y = base_y - (n - 1 - row_n) * self.pitch - top
            for wi, cx in row:
                ws = states[wi]
                size = round(self.size * ws.scale / 100)
                font = load_font(st.font, size, st.font_index)
                stroke = round(st.stroke * size)
                word = cue.words[wi].text
                if ws.boxed:
                    fill = (*st.box_text_color, 255)
                elif ws.active:
                    fill = (*st.highlight, 255)
                else:
                    fill = (*st.color, 255)
                off = st.shadow_offset * size
                if ws.boxed:
                    x0, y0, x1, y1 = font.getbbox(word, anchor="ms", stroke_width=stroke)
                    pad_x, pad_y = BOX_PAD_X * size, BOX_PAD_Y * size
                    box = [cx + x0 - pad_x, y + y0 - pad_y, cx + x1 + pad_x, y + y1 + pad_y]
                    radius = round(0.22 * size)
                    if st.shadow:
                        ds.rounded_rectangle([box[0], box[1] + off, box[2], box[3] + off],
                                             radius=radius, fill=sh_fill)
                    dt.rounded_rectangle(box, radius=radius, fill=(*st.highlight, 255),
                                         outline=stroke_fill if stroke else None,
                                         width=max(2, stroke // 2))
                if st.shadow:
                    ds.text((cx, y + off), word, font=font, anchor="ms", fill=sh_fill,
                            stroke_width=stroke, stroke_fill=sh_fill)
                dt.text((cx, y), word, font=font, anchor="ms", fill=fill,
                        stroke_width=stroke, stroke_fill=stroke_fill)

        if st.shadow and st.shadow_blur > 0:
            shadow = shadow.filter(ImageFilter.GaussianBlur(st.shadow_blur * self.size))
        layer = shadow if st.shadow else Image.new("RGBA", region, (0, 0, 0, 0))
        layer.alpha_composite(text)
        if alpha < 255:
            a = layer.getchannel("A").point(lambda v: v * alpha // 255)
            layer.putalpha(a)
        frame = Image.new("RGBA", (self.W, self.H), (0, 0, 0, 0))
        frame.paste(layer, (0, top))
        return frame

    def frame_image(self, t: float) -> Image.Image:
        key = self._state(t)
        if key is None:
            return Image.new("RGBA", (self.W, self.H), (0, 0, 0, 0))
        return self._draw_cue(key)

    def frame_bytes(self, t: float) -> bytes:
        key = self._state(t)
        if key is None:
            return self._empty
        cached = self._cache.get(key)
        if cached is not None:
            self._cache.move_to_end(key)
            return cached
        data = self._draw_cue(key).tobytes()
        self._cache[key] = data
        if len(self._cache) > 24:
            self._cache.popitem(last=False)
        return data

    def frames(self, count: int) -> Iterator[bytes]:
        for n in range(count):
            yield self.frame_bytes(n / self.fps)
