"""Table view — sortable list of all servers as compact rows.

Provides a dense, scannable alternative to the card grid.
"""

import customtkinter as ctk
from typing import Dict, List, Optional, Callable, Tuple
from app.models import ServerStatus
from app.ui.styles import COLORS, FONTS


_COLUMNS: List[Tuple[str, str, int, str]] = [
    # (key, header, width, align)
    ("name",     "Servidor",   180, "w"),
    ("host",     "IP / Host",  140, "w"),
    ("status",   "Estado",      80, "center"),
    ("cpu",      "CPU %",       70, "center"),
    ("ram",      "RAM %",       70, "center"),
    ("disk",     "Disco %",     70, "center"),
    ("sessions", "Sesiones",    80, "center"),
    ("active",   "Activas",     70, "center"),
    ("uptime",   "Uptime",      90, "center"),
]


class TableView(ctk.CTkFrame):
    """Sortable server table — alternative to card grid."""

    def __init__(self, parent, on_server_click: Callable[[str], None]):
        super().__init__(parent, fg_color="transparent")
        self._on_click = on_server_click
        self._sort_col = "name"
        self._sort_asc = True
        self._statuses: Dict[str, ServerStatus] = {}
        self._row_frames: List[ctk.CTkFrame] = []

        self._build_ui()

    def _build_ui(self):
        # Header row
        self._header = ctk.CTkFrame(self, fg_color=COLORS["bg_medium"],
                                     corner_radius=8, height=36)
        self._header.pack(fill="x", padx=4, pady=(0, 2))
        self._header.pack_propagate(False)

        self._header_btns: Dict[str, ctk.CTkButton] = {}
        for key, title, w, _ in _COLUMNS:
            btn = ctk.CTkButton(
                self._header, text=title, width=w, height=30,
                font=FONTS["small_bold"], fg_color="transparent",
                hover_color=COLORS["bg_card"], text_color=COLORS["text_secondary"],
                anchor="center",
                command=lambda k=key: self._on_sort(k),
            )
            btn.pack(side="left", padx=1)
            self._header_btns[key] = btn

        # Scrollable body
        self._body = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self._body.pack(fill="both", expand=True, padx=4, pady=2)

    def _on_sort(self, col: str):
        if self._sort_col == col:
            self._sort_asc = not self._sort_asc
        else:
            self._sort_col = col
            self._sort_asc = True
        # Update header indicators
        for k, btn in self._header_btns.items():
            arrow = ""
            if k == col:
                arrow = " ▲" if self._sort_asc else " ▼"
            original = [t for kk, t, _, _ in _COLUMNS if kk == k][0]
            btn.configure(text=original + arrow)
        self._render()

    def _sort_key(self, st: ServerStatus):
        m = st.metrics
        col = self._sort_col
        if col == "name":
            return st.server.display_name.lower()
        if col == "host":
            return st.server.host
        if col == "status":
            return 0 if st.is_online else 1
        if col == "cpu":
            return m.cpu_percent if m else -1
        if col == "ram":
            return m.memory_percent if m else -1
        if col == "disk":
            return m.disk_percent if m else -1
        if col == "sessions":
            return st.total_sessions
        if col == "active":
            return st.active_users
        if col == "uptime":
            return m.uptime_hours if m else -1
        return 0

    def update_all(self, statuses: Dict[str, ServerStatus],
                   visible_hosts: Optional[List[str]] = None):
        self._statuses = statuses
        self._visible = visible_hosts
        self._render()

    def _render(self):
        # Destroy old rows
        for f in self._row_frames:
            f.destroy()
        self._row_frames.clear()

        hosts = self._visible if self._visible else list(self._statuses.keys())
        items = [self._statuses[h] for h in hosts if h in self._statuses]
        items.sort(key=self._sort_key, reverse=not self._sort_asc)

        for i, st in enumerate(items):
            bg = COLORS["bg_card"] if i % 2 == 0 else COLORS["bg_medium"]
            row = ctk.CTkFrame(self._body, fg_color=bg, corner_radius=6,
                               height=34)
            row.pack(fill="x", pady=1)
            row.pack_propagate(False)

            host = st.server.host
            m = st.metrics

            vals = {
                "name": st.server.display_name,
                "host": host,
                "status": "🟢 Online" if st.is_online else "🔴 Offline",
                "cpu": f"{m.cpu_percent:.0f}%" if m else "—",
                "ram": f"{m.memory_percent:.0f}%" if m else "—",
                "disk": f"{m.disk_percent:.0f}%" if m else "—",
                "sessions": str(st.total_sessions) if st.is_online else "—",
                "active": str(st.active_users) if st.is_online else "—",
                "uptime": self._fmt_uptime(m.uptime_hours) if m else "—",
            }

            for key, _, w, anchor in _COLUMNS:
                txt = vals.get(key, "")
                tc = COLORS["text_primary"]
                if key in ("cpu", "ram", "disk") and m and st.is_online:
                    v = getattr(m, {"cpu": "cpu_percent", "ram": "memory_percent",
                                    "disk": "disk_percent"}[key])
                    if v >= 90:
                        tc = COLORS["critical"]
                    elif v >= 75:
                        tc = COLORS["warning"]
                if key == "status":
                    tc = COLORS["success"] if st.is_online else COLORS["critical"]

                lbl = ctk.CTkLabel(row, text=txt, width=w, font=FONTS["small"],
                                    text_color=tc, anchor=anchor)
                lbl.pack(side="left", padx=1)
                lbl.bind("<Button-1>", lambda e, h=host: self._on_click(h))

            row.bind("<Button-1>", lambda e, h=host: self._on_click(h))
            self._row_frames.append(row)

    @staticmethod
    def _fmt_uptime(hours: float) -> str:
        if hours < 1:
            return f"{hours * 60:.0f}m"
        if hours < 24:
            return f"{hours:.1f}h"
        days = int(hours // 24)
        h = hours % 24
        return f"{days}d {h:.0f}h"
