"""Sparkline mini-charts drawn on a Tk Canvas.

Used inside server cards to show metric evolution over time (CPU, RAM, etc.).
Pure Tk canvas — no external charting library needed.
"""

import customtkinter as ctk
from typing import List, Optional, Tuple
from app.ui.styles import COLORS


class Sparkline(ctk.CTkCanvas):
    """Tiny line chart that fits inside a server card (e.g. 120×32 px).

    Parameters
    ----------
    parent : widget
    width, height : int
    line_color : str  — hex color for the line
    fill_color : str  — hex color for the area under the line (with alpha via stipple)
    """

    def __init__(self, parent, width: int = 120, height: int = 32,
                 line_color: str = COLORS["accent"],
                 fill_color: Optional[str] = None, **kw):
        bg = parent.cget("fg_color") if hasattr(parent, "cget") else COLORS["bg_card"]
        if isinstance(bg, (list, tuple)):
            bg = bg[-1]  # dark-mode value
        super().__init__(parent, width=width, height=height,
                         bg=bg, highlightthickness=0, **kw)
        self._w = width
        self._h = height
        self._line_color = line_color
        self._fill_color = fill_color or line_color
        self._data: List[float] = []

    def set_data(self, values: List[float], y_min: float = 0, y_max: float = 100):
        """Redraw the sparkline with new data points."""
        self._data = values
        self.delete("all")

        if len(values) < 2:
            # Not enough data — show placeholder text
            self.create_text(
                self._w // 2, self._h // 2,
                text="sin datos" if not values else "...",
                fill=COLORS["text_muted"], font=("Segoe UI", 8),
            )
            return

        pad_x, pad_y = 2, 3
        w = self._w - 2 * pad_x
        h = self._h - 2 * pad_y

        span = max(y_max - y_min, 1)

        def _xy(i: int, v: float) -> Tuple[float, float]:
            x = pad_x + (i / (len(values) - 1)) * w
            y = pad_y + h - ((v - y_min) / span) * h
            return x, y

        # Build polygon for filled area
        points = [_xy(i, v) for i, v in enumerate(values)]
        # Bottom-right and bottom-left to close the polygon
        polygon = []
        for p in points:
            polygon.extend(p)
        polygon.extend([pad_x + w, pad_y + h, pad_x, pad_y + h])

        self.create_polygon(
            polygon, fill=self._fill_color, outline="",
            stipple="gray25",  # cheap transparency
        )

        # Draw line on top
        line_coords = []
        for p in points:
            line_coords.extend(p)
        self.create_line(line_coords, fill=self._line_color, width=1.5, smooth=True)

        # Current value dot
        lx, ly = points[-1]
        self.create_oval(lx - 2, ly - 2, lx + 2, ly + 2,
                         fill=self._line_color, outline="")
