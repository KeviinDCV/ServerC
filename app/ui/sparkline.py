"""Sparkline mini-charts rendered as PIL images inside CTkLabels.

Used inside server cards to show metric evolution over time (CPU, RAM, etc.).
Pure PIL rendering — no raw Tk Canvas, no widget mixing issues.
"""

import customtkinter as ctk
from typing import List, Optional
from PIL import Image, ImageDraw
from app.ui.styles import COLORS


def _hex_to_rgb(h: str):
    h = h.lstrip("#")
    return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))


class Sparkline(ctk.CTkLabel):
    """Tiny line chart rendered as an image inside a CTkLabel."""

    def __init__(self, parent, width: int = 80, height: int = 30,
                 line_color: str = COLORS["accent"],
                 fill_color: Optional[str] = None, **kw):
        self._sw = int(width)
        self._sh = int(height)
        self._line_color = line_color
        self._fill_color = fill_color or line_color
        self._bg_color = COLORS["bg_card"]

        # Create a blank placeholder image
        self._img = self._render([])
        self._ctk_img = ctk.CTkImage(light_image=self._img,
                                      dark_image=self._img,
                                      size=(self._sw, self._sh))
        super().__init__(parent, image=self._ctk_img, text="",
                         fg_color="transparent", **kw)

    def set_data(self, values: List[float], y_min: float = 0, y_max: float = 100):
        """Redraw the sparkline with new data points."""
        self._img = self._render(values, y_min, y_max)
        self._ctk_img.configure(light_image=self._img, dark_image=self._img)

    def _render(self, values: List[float],
                y_min: float = 0, y_max: float = 100) -> Image.Image:
        w, h = self._sw, self._sh
        bg = _hex_to_rgb(self._bg_color)
        img = Image.new("RGBA", (w, h), (*bg, 255))
        draw = ImageDraw.Draw(img)

        if len(values) < 2:
            # Placeholder — draw small centered text
            tc = _hex_to_rgb(COLORS["text_muted"])
            draw.text((4, h // 2 - 4), "···",
                      fill=(*tc, 140))
            return img

        line_rgb = _hex_to_rgb(self._line_color)
        fill_rgb = _hex_to_rgb(self._fill_color)

        pad_x, pad_y = 2, 3
        cw = w - 2 * pad_x
        ch = h - 2 * pad_y
        span = max(y_max - y_min, 1)

        def _xy(i: int, v: float):
            x = pad_x + (i / (len(values) - 1)) * cw
            y = pad_y + ch - ((v - y_min) / span) * ch
            return x, y

        points = [_xy(i, v) for i, v in enumerate(values)]

        # Filled area (semi-transparent)
        polygon = list(points) + [(pad_x + cw, pad_y + ch), (pad_x, pad_y + ch)]
        draw.polygon(polygon, fill=(*fill_rgb, 40))

        # Line
        if len(points) >= 2:
            draw.line(points, fill=(*line_rgb, 220), width=2)

        # Current value dot
        lx, ly = points[-1]
        draw.ellipse([lx - 2, ly - 2, lx + 2, ly + 2],
                     fill=(*line_rgb, 255))

        return img
