"""Dashboard view — grid of server cards with live status, filters, and grid size control.

Performance design:
- Cards are created once per server and *updated in-place* (never destroyed/recreated).
- Layout (grid arrangement) only changes when the visible host set or column count changes.
- Filter chips are rebuilt only on explicit update_all(), not on every data refresh.
- Summary bar is a simple .configure() call — no widget churn.
"""

import logging
import customtkinter as ctk
from typing import Dict, List, Optional, Set, Callable
from collections import Counter
from dataclasses import dataclass, field

from app.models import ServerStatus
from app.ui.styles import COLORS, FONTS
from app.ui.summary_panel import SummaryPanel
from app.ui.table_view import TableView
from app.ui.sparkline import Sparkline

log = logging.getLogger(__name__)


# ── Per-card widget references for in-place updates ──────────────────────────

@dataclass
class _CardWidgets:
    """Stores references to all mutable labels inside a card so we can
    update them with .configure() instead of destroying/recreating."""
    frame: ctk.CTkFrame
    dot: ctk.CTkLabel
    name_lbl: ctk.CTkLabel
    ip_lbl: ctk.CTkLabel
    # Dynamic area — a frame whose children change
    body: ctk.CTkFrame
    # Sparklines for metric history
    spark_cpu: Optional[Sparkline] = None
    spark_ram: Optional[Sparkline] = None
    spark_frame: Optional[ctk.CTkFrame] = None
    # Cached last-rendered signature so we can skip no-op redraws
    _sig: str = ""


class DashboardView(ctk.CTkFrame):
    """Main dashboard showing all servers as status cards with filtering."""

    def __init__(self, parent, on_server_click, on_add_server, on_edit_server,
                 on_delete_server, on_export=None):
        super().__init__(parent, fg_color=COLORS["bg_dark"])
        self.on_server_click = on_server_click
        self.on_add_server = on_add_server
        self.on_edit_server = on_edit_server
        self.on_delete_server = on_delete_server
        self.on_export = on_export

        # Card pool — keyed by host, created once, never destroyed
        self._card_pool: Dict[str, _CardWidgets] = {}
        self._all_statuses: Dict[str, ServerStatus] = {}
        self._visible_hosts: List[str] = []   # ordered list of hosts currently shown
        self._cols = 3
        self._active_filters: Dict[str, str] = {}
        self._empty_label: Optional[ctk.CTkLabel] = None
        self._prev_layout_key: str = ""  # tracks when grid needs rebuild
        self._view_mode = "cards"  # "cards" or "table"
        self._spark_data: Dict[str, Dict[str, List[float]]] = {}  # host -> {cpu: [...], ram: [...]}
        self._alerts: List[Dict] = []

        self._build_ui()

    # ──────────────────────────────────────────────────────────────────────────
    # UI skeleton (built once)
    # ──────────────────────────────────────────────────────────────────────────

    def _build_ui(self):
        # ─── Header ───
        header = ctk.CTkFrame(self, fg_color="transparent", height=60)
        header.pack(fill="x", padx=20, pady=(15, 5))
        header.pack_propagate(False)

        ctk.CTkLabel(header, text="🖥  ServerC Monitor HUV", font=FONTS["title"],
                      text_color=COLORS["text_primary"]).pack(side="left")

        # Right side buttons
        btn_row = ctk.CTkFrame(header, fg_color="transparent")
        btn_row.pack(side="right")

        ctk.CTkButton(
            btn_row, text="📥 Exportar", font=FONTS["small_bold"],
            fg_color=COLORS["bg_card"], hover_color=COLORS["bg_card_hover"],
            height=34, width=100, command=self._do_export,
        ).pack(side="left", padx=(0, 8))

        ctk.CTkButton(
            btn_row, text="＋ Agregar Servidor", font=FONTS["body_bold"],
            fg_color=COLORS["accent"], hover_color=COLORS["accent_hover"],
            height=38, width=180, command=self.on_add_server,
        ).pack(side="left")

        # ─── Executive Summary Panel ───
        self.summary_panel = SummaryPanel(self)
        self.summary_panel.pack(fill="x", padx=20, pady=(5, 5))

        # ─── Search + View toggle + Grid Size row ───
        search_row = ctk.CTkFrame(self, fg_color="transparent")
        search_row.pack(fill="x", padx=20, pady=(5, 3))

        self.search_var = ctk.StringVar()
        self.search_var.trace_add("write", lambda *_: self._on_filter_changed())
        ctk.CTkEntry(
            search_row, textvariable=self.search_var,
            placeholder_text="🔍  Buscar por nombre, IP, usuario...",
            height=38, font=FONTS["body"], width=400, corner_radius=10,
        ).pack(side="left", fill="x", expand=True, padx=(0, 10))

        right_controls = ctk.CTkFrame(search_row, fg_color="transparent")
        right_controls.pack(side="right")

        # View toggle: Cards / Table
        ctk.CTkLabel(right_controls, text="Vista:", font=FONTS["small_bold"],
                      text_color=COLORS["text_muted"]).pack(side="left", padx=(0, 5))
        self._view_toggle = ctk.CTkSegmentedButton(
            right_controls, values=["🃏 Cards", "📋 Tabla"],
            command=self._on_view_toggle, font=FONTS["small_bold"], height=32,
        )
        self._view_toggle.set("🃏 Cards")
        self._view_toggle.pack(side="left", padx=(0, 10))

        ctk.CTkLabel(right_controls, text="Grid:", font=FONTS["small_bold"],
                      text_color=COLORS["text_muted"]).pack(side="left", padx=(0, 5))
        self.grid_selector = ctk.CTkSegmentedButton(
            right_controls, values=["5", "4", "3", "2"],
            command=self._on_grid_change, font=FONTS["small_bold"], height=32,
        )
        self.grid_selector.set("3")
        self.grid_selector.pack(side="left")

        # ─── Filter chips (scrollable) ───
        self._filter_outer = ctk.CTkFrame(self, fg_color="transparent", height=38)
        self._filter_outer.pack(fill="x", padx=20, pady=(3, 3))
        self._filter_outer.pack_propagate(False)

        self._filter_canvas = ctk.CTkCanvas(
            self._filter_outer, highlightthickness=0,
            bg=self._apply_appearance_mode(COLORS["bg_dark"]), height=36,
        )
        self._filter_canvas.pack(side="left", fill="both", expand=True)

        self.filter_row = ctk.CTkFrame(self._filter_canvas, fg_color="transparent")
        self._filter_canvas.create_window((0, 0), window=self.filter_row, anchor="nw")
        self.filter_row.bind("<Configure>", lambda e: self._filter_canvas.configure(
            scrollregion=self._filter_canvas.bbox("all")))

        def _wheel(event):
            self._filter_canvas.xview_scroll(int(-1 * (event.delta / 120)), "units")
        self._filter_canvas.bind("<MouseWheel>", _wheel)
        self.filter_row.bind("<MouseWheel>", _wheel)

        self._scroll_left_btn = ctk.CTkButton(
            self._filter_outer, text="◀", width=24, height=28,
            font=("Segoe UI", 11), corner_radius=6,
            fg_color=COLORS["bg_card"], hover_color=COLORS["bg_card_hover"],
            text_color=COLORS["text_muted"],
            command=lambda: self._filter_canvas.xview_scroll(-3, "units"),
        )
        self._scroll_right_btn = ctk.CTkButton(
            self._filter_outer, text="▶", width=24, height=28,
            font=("Segoe UI", 11), corner_radius=6,
            fg_color=COLORS["bg_card"], hover_color=COLORS["bg_card_hover"],
            text_color=COLORS["text_muted"],
            command=lambda: self._filter_canvas.xview_scroll(3, "units"),
        )

        # ─── Status bar (compact, below filters) ───
        self.summary_frame = ctk.CTkFrame(self, fg_color=COLORS["bg_medium"], corner_radius=10, height=36)
        self.summary_frame.pack(fill="x", padx=20, pady=(3, 4))
        self.summary_frame.pack_propagate(False)

        self.filter_info_label = ctk.CTkLabel(
            self.summary_frame, text="",
            font=FONTS["small"], text_color=COLORS["accent"],
        )
        self.filter_info_label.pack(side="left", padx=15)

        self.last_update_label = ctk.CTkLabel(
            self.summary_frame, text="Cargando servidores...",
            font=FONTS["small"], text_color=COLORS["text_muted"],
        )
        self.last_update_label.pack(side="right", padx=15)

        # ─── Content area: cards grid + table (only one visible at a time) ───
        self._content_frame = ctk.CTkFrame(self, fg_color="transparent")
        self._content_frame.pack(fill="both", expand=True, padx=0, pady=0)

        self.grid_scroll = ctk.CTkScrollableFrame(self._content_frame, fg_color="transparent")
        self.grid_scroll.pack(fill="both", expand=True, padx=15, pady=(0, 15))

        self._table_view = TableView(self._content_frame, on_server_click=self.on_server_click)
        # table is hidden initially

    # ──────────────────────────────────────────────────────────────────────────
    # View toggle + Grid size
    # ──────────────────────────────────────────────────────────────────────────

    def _on_view_toggle(self, value: str):
        if "Tabla" in value:
            self._view_mode = "table"
            self.grid_scroll.pack_forget()
            self._table_view.pack(fill="both", expand=True, padx=15, pady=(0, 15))
            self._table_view.update_all(self._all_statuses, self._visible_hosts)
        else:
            self._view_mode = "cards"
            self._table_view.pack_forget()
            self.grid_scroll.pack(fill="both", expand=True, padx=15, pady=(0, 15))
            self._relayout()

    def _on_grid_change(self, value: str):
        self._cols = int(value)
        self._relayout()

    def _do_export(self):
        if self.on_export:
            self.on_export()

    # ──────────────────────────────────────────────────────────────────────────
    # Filter logic
    # ──────────────────────────────────────────────────────────────────────────

    def _get_unique_names(self) -> List[str]:
        names = [s.server.name for s in self._all_statuses.values() if s.server.name]
        counts = Counter(names)
        return sorted([n for n, c in counts.items() if c > 1])

    def _build_filter_chips(self):
        for w in self.filter_row.winfo_children():
            w.destroy()

        statuses = self._all_statuses
        if not statuses:
            self._scroll_left_btn.pack_forget()
            self._scroll_right_btn.pack_forget()
            return

        self._add_chip("Todos", "all", "all", is_clear=True)

        online_count = sum(1 for s in statuses.values() if s.is_online)
        offline_count = len(statuses) - online_count
        self._add_chip(f"✅ En línea ({online_count})", "status", "online")
        self._add_chip(f"❌ Sin conexión ({offline_count})", "status", "offline")

        warning_count = sum(1 for s in statuses.values() if s.is_online and s.load_level == "warning")
        critical_count = sum(1 for s in statuses.values() if s.is_online and s.load_level == "critical")
        if warning_count:
            self._add_chip(f"⚠ Precaución ({warning_count})", "load", "warning")
        if critical_count:
            self._add_chip(f"🔴 Sobrecarga ({critical_count})", "load", "critical")

        sep = ctk.CTkLabel(self.filter_row, text="│", font=FONTS["body"],
                            text_color=COLORS["text_muted"])
        sep.pack(side="left", padx=6)

        for name in self._get_unique_names():
            count = sum(1 for s in statuses.values() if s.server.name == name)
            self._add_chip(f"{name} ({count})", "group", name)

        self.filter_row.update_idletasks()
        cw = self._filter_canvas.winfo_width()
        if self.filter_row.winfo_reqwidth() > cw > 1:
            self._scroll_left_btn.pack(side="left", padx=(4, 0))
            self._scroll_right_btn.pack(side="right")
        else:
            self._scroll_left_btn.pack_forget()
            self._scroll_right_btn.pack_forget()

    def _add_chip(self, text: str, ft: str, val: str, is_clear: bool = False):
        active = (not self._active_filters and is_clear) or \
                 self._active_filters.get(ft) == val
        fg = COLORS["accent"] if active else COLORS["bg_card"]
        hov = COLORS["accent_hover"] if active else COLORS["bg_card_hover"]
        tc = COLORS["bg_dark"] if active else COLORS["text_secondary"]

        btn = ctk.CTkButton(
            self.filter_row, text=text, font=FONTS["small_bold"],
            fg_color=fg, hover_color=hov, text_color=tc,
            height=28, corner_radius=14,
            command=lambda: self._toggle_filter(ft, val, is_clear),
        )
        btn.pack(side="left", padx=2)
        btn.bind("<MouseWheel>", lambda e: self._filter_canvas.xview_scroll(
            int(-1 * (e.delta / 120)), "units"))

    def _toggle_filter(self, ft: str, val: str, is_clear: bool):
        if is_clear:
            self._active_filters.clear()
        elif self._active_filters.get(ft) == val:
            del self._active_filters[ft]
        else:
            self._active_filters[ft] = val
        self._build_filter_chips()
        self._on_filter_changed()

    def _compute_visible(self) -> List[str]:
        """Return ordered list of hosts that pass current filters."""
        search = self.search_var.get().strip().lower()
        status_f = self._active_filters.get("status")
        load_f = self._active_filters.get("load")
        group_f = self._active_filters.get("group")

        result = []
        for host, s in self._all_statuses.items():
            if search:
                if not (search in s.server.name.lower()
                        or search in s.server.host.lower()
                        or search in s.server.username.lower()
                        or search in host.lower()
                        or any(search in sess.username.lower() for sess in s.sessions)):
                    continue
            if status_f == "online" and not s.is_online:
                continue
            if status_f == "offline" and s.is_online:
                continue
            if load_f and (not s.is_online or s.load_level != load_f):
                continue
            if group_f and s.server.name != group_f:
                continue
            result.append(host)
        return result

    def _on_filter_changed(self):
        """Called when search text or filter chip changes."""
        visible = self._compute_visible()
        self._visible_hosts = visible
        self._relayout()
        # Update info label
        total = len(self._all_statuses)
        shown = len(visible)
        self.filter_info_label.configure(
            text=f"Mostrando {shown} de {total}" if shown < total else "")

    # ──────────────────────────────────────────────────────────────────────────
    # Card pool — create once, update in-place
    # ──────────────────────────────────────────────────────────────────────────

    def _ensure_card(self, host: str) -> _CardWidgets:
        """Get or create a card for 'host'. Cards are created once and reused."""
        if host in self._card_pool:
            return self._card_pool[host]

        status = self._all_statuses.get(host)
        if not status:
            return None  # shouldn't happen

        card = ctk.CTkFrame(self.grid_scroll, fg_color=COLORS["bg_card"],
                            corner_radius=14, height=240)
        card.pack_propagate(False)

        def on_click(e, h=host):
            self.on_server_click(h)
        card.bind("<Button-1>", on_click)

        inner = ctk.CTkFrame(card, fg_color="transparent")
        inner.pack(fill="both", expand=True, padx=15, pady=12)
        inner.bind("<Button-1>", on_click)

        # Top row
        top_row = ctk.CTkFrame(inner, fg_color="transparent")
        top_row.pack(fill="x")
        top_row.bind("<Button-1>", on_click)

        dot = ctk.CTkLabel(top_row, text="●", font=("Segoe UI", 14),
                           text_color=COLORS["offline"])
        dot.pack(side="left")
        dot.bind("<Button-1>", on_click)

        name_lbl = ctk.CTkLabel(top_row, text=status.server.display_name,
                                 font=FONTS["heading"], text_color=COLORS["text_primary"])
        name_lbl.pack(side="left", padx=(6, 0))
        name_lbl.bind("<Button-1>", on_click)

        btn_frame = ctk.CTkFrame(top_row, fg_color="transparent")
        btn_frame.pack(side="right")
        ctk.CTkButton(
            btn_frame, text="✏", width=28, height=28, font=("Segoe UI", 12),
            fg_color="transparent", hover_color=COLORS["bg_card_hover"],
            command=lambda h=host: self.on_edit_server(h),
        ).pack(side="left", padx=2)
        ctk.CTkButton(
            btn_frame, text="🗑", width=28, height=28, font=("Segoe UI", 12),
            fg_color="transparent", hover_color=COLORS["critical"],
            command=lambda h=host: self.on_delete_server(h),
        ).pack(side="left")

        ip_lbl = ctk.CTkLabel(inner, text=host, font=FONTS["mono"],
                               text_color=COLORS["text_muted"])
        ip_lbl.pack(anchor="w", pady=(2, 8))
        ip_lbl.bind("<Button-1>", on_click)

        # Body area — content changes when status updates
        body = ctk.CTkFrame(inner, fg_color="transparent")
        body.pack(fill="both", expand=True)
        body.bind("<Button-1>", on_click)

        # Sparkline area for metric history
        spark_frame = ctk.CTkFrame(inner, fg_color=COLORS["bg_card"], height=36,
                                    corner_radius=6)
        spark_frame.pack(fill="x", pady=(4, 0))
        spark_frame.pack_propagate(False)
        spark_frame.bind("<Button-1>", on_click)

        spark_cpu = Sparkline(spark_frame, width=80, height=30,
                              line_color=COLORS["accent"])
        spark_cpu.pack(side="left", padx=(4, 0))
        ctk.CTkLabel(spark_frame, text="CPU", font=("Segoe UI", 8),
                      text_color=COLORS["text_muted"]).pack(side="left", padx=(2, 8))

        spark_ram = Sparkline(spark_frame, width=80, height=30,
                              line_color=COLORS["warning"])
        spark_ram.pack(side="left")
        ctk.CTkLabel(spark_frame, text="RAM", font=("Segoe UI", 8),
                      text_color=COLORS["text_muted"]).pack(side="left", padx=(2, 0))

        cw = _CardWidgets(frame=card, dot=dot, name_lbl=name_lbl,
                          ip_lbl=ip_lbl, body=body,
                          spark_cpu=spark_cpu, spark_ram=spark_ram,
                          spark_frame=spark_frame)
        self._card_pool[host] = cw

        # Initial content
        self._update_card_body(host, cw)
        return cw

    def _card_signature(self, status: ServerStatus) -> str:
        """A cheap string that changes only when visible card content changes."""
        if not status.is_online:
            return f"off|{(status.error_message or '')[:40]}"
        m = status.metrics
        cpu = int(m.cpu_percent) if m else 0
        ram = int(m.memory_percent) if m else 0
        dsk = int(m.disk_percent) if m else 0
        return f"on|{status.total_sessions}|{status.active_users}|{status.load_level}|{cpu}|{ram}|{dsk}"

    def _update_card_body(self, host: str, cw: _CardWidgets):
        """Update the mutable parts of a card. Only touches widgets that changed."""
        status = self._all_statuses.get(host)
        if not status:
            return

        sig = self._card_signature(status)
        if sig == cw._sig:
            return  # nothing changed — skip entirely
        cw._sig = sig

        # Dot color
        cw.dot.configure(text_color=COLORS["online"] if status.is_online else COLORS["offline"])

        # Card background
        load = status.load_level
        if not status.is_online:
            bg = COLORS["bg_card"]
        elif load == "critical":
            bg = "#3d1520"
        elif load == "warning":
            bg = "#3d2e15"
        else:
            bg = COLORS["bg_card"]
        cw.frame.configure(fg_color=bg)

        # Rebuild body content (this is the only destroy/recreate, and only when data changes)
        for w in cw.body.winfo_children():
            w.destroy()

        on_click = lambda e, h=host: self.on_server_click(h)

        if status.is_online:
            user_color = COLORS["text_primary"]
            if load == "critical":
                user_color = COLORS["critical"]
            elif load == "warning":
                user_color = COLORS["warning"]

            user_row = ctk.CTkFrame(cw.body, fg_color="transparent")
            user_row.pack(fill="x")
            user_row.bind("<Button-1>", on_click)

            ctk.CTkLabel(user_row, text=str(status.total_sessions),
                          font=FONTS["mono_large"], text_color=user_color).pack(side="left")
            lbl = ctk.CTkLabel(user_row, text=f" sesiones ({status.active_users} activas)",
                          font=FONTS["small"], text_color=COLORS["text_secondary"])
            lbl.pack(side="left", pady=(5, 0))
            lbl.bind("<Button-1>", on_click)

            if status.metrics:
                m = status.metrics
                metrics_row = ctk.CTkFrame(cw.body, fg_color="transparent")
                metrics_row.pack(fill="x", pady=(8, 0))
                metrics_row.bind("<Button-1>", on_click)
                for label, val, thresh in [
                    ("CPU", m.cpu_percent, 80),
                    ("RAM", m.memory_percent, 80),
                    ("Disco", m.disk_percent, 90),
                ]:
                    mc = COLORS["text_secondary"]
                    if val >= thresh:
                        mc = COLORS["critical"]
                    elif val >= thresh * 0.8:
                        mc = COLORS["warning"]
                    item = ctk.CTkFrame(metrics_row, fg_color="transparent")
                    item.pack(side="left", fill="x", expand=True)
                    item.bind("<Button-1>", on_click)
                    ctk.CTkLabel(item, text=f"{label}: {val:.0f}%",
                                  font=FONTS["small_bold"], text_color=mc).pack()

            if load != "normal":
                txt = "⚠ SOBRECARGADO" if load == "critical" else "⚠ PRECAUCIÓN"
                col = COLORS["critical"] if load == "critical" else COLORS["warning"]
                l = ctk.CTkLabel(cw.body, text=txt, font=FONTS["small_bold"], text_color=col)
                l.pack(anchor="w", pady=(5, 0))
                l.bind("<Button-1>", on_click)
        else:
            err = status.error_message[:80] if status.error_message else "No se pudo conectar"
            l = ctk.CTkLabel(cw.body, text=f"❌ {err}", font=FONTS["small"],
                              text_color=COLORS["critical"], wraplength=250)
            l.pack(anchor="w", pady=(5, 0))
            l.bind("<Button-1>", on_click)

    # ──────────────────────────────────────────────────────────────────────────
    # Layout — only runs when the visible set or column count changes
    # ──────────────────────────────────────────────────────────────────────────

    def _relayout(self):
        """Arrange visible cards into the grid using grid manager.
        Cards are children of grid_scroll — we just grid/grid_forget them."""
        # Hide empty label
        if self._empty_label:
            self._empty_label.grid_forget()
            self._empty_label = None

        # Hide ALL cards (grid_forget keeps the widget alive)
        for cw in self._card_pool.values():
            cw.frame.grid_forget()

        hosts = self._visible_hosts

        if not hosts:
            if self._all_statuses:
                msg = "No hay servidores que coincidan con los filtros."
            else:
                msg = "No hay servidores configurados.\nHaz clic en '＋ Agregar Servidor' para comenzar."
            self._empty_label = ctk.CTkLabel(
                self.grid_scroll, text=msg, font=FONTS["body"],
                text_color=COLORS["text_muted"], justify="center")
            self._empty_label.grid(row=0, column=0, columnspan=self._cols, pady=60)
            return

        # Configure column weights so cards stretch equally
        for c in range(self._cols):
            self.grid_scroll.columnconfigure(c, weight=1, uniform="card")
        # Clean up extra columns from previous layout
        for c in range(self._cols, 10):
            self.grid_scroll.columnconfigure(c, weight=0, uniform="")

        for i, host in enumerate(hosts):
            cw = self._ensure_card(host)
            row = i // self._cols
            col = i % self._cols
            cw.frame.grid(row=row, column=col, padx=4, pady=4, sticky="nsew")

        # Cache layout key
        self._prev_layout_key = f"{','.join(hosts)}|{self._cols}"

    # ──────────────────────────────────────────────────────────────────────────
    # Public API called by MainWindow
    # ──────────────────────────────────────────────────────────────────────────

    def update_all(self, statuses: Dict[str, ServerStatus]):
        """Full refresh: update data, chips, summary, cards, layout."""
        log.debug("update_all called with %d statuses", len(statuses))
        self._all_statuses = statuses

        try:
            self._update_summary()
        except Exception:
            log.exception("Error in _update_summary")

        try:
            self._build_filter_chips()
        except Exception:
            log.exception("Error in _build_filter_chips")

        # Remove cards for deleted servers
        stale = set(self._card_pool) - set(statuses)
        for h in stale:
            cw = self._card_pool.pop(h)
            cw.frame.destroy()

        # Compute visible set
        visible = self._compute_visible()
        layout_key = f"{','.join(visible)}|{self._cols}"
        need_relayout = (layout_key != self._prev_layout_key)
        self._visible_hosts = visible

        # Update card data in-place (cheap .configure() per card)
        for host in visible:
            try:
                cw = self._ensure_card(host)
                self._update_card_body(host, cw)
                # Feed sparklines if data available
                sdata = self._spark_data.get(host)
                if sdata and cw.spark_cpu and cw.spark_ram:
                    cw.spark_cpu.set_data(sdata.get("cpu", []))
                    cw.spark_ram.set_data(sdata.get("ram", []))
            except Exception:
                log.exception("Error updating card for %s", host)

        if need_relayout:
            self._relayout()

        # Also update table view if active
        try:
            if self._view_mode == "table":
                self._table_view.update_all(statuses, visible)
        except Exception:
            log.exception("Error updating table view")

        total = len(statuses)
        shown = len(visible)
        self.filter_info_label.configure(
            text=f"Mostrando {shown} de {total}" if shown < total else "")

    def update_progress(self, done: int, total: int):
        """Cheap progress indicator — no re-render."""
        self.last_update_label.configure(text=f"Consultando {done}/{total}...")

    def _update_summary(self):
        """Update the executive summary panel and the compact status bar."""
        statuses = self._all_statuses
        self.summary_panel.update(statuses, self._alerts)
        from datetime import datetime
        self.last_update_label.configure(
            text=f"Última actualización: {datetime.now().strftime('%H:%M:%S')}"
        )

    def set_spark_data(self, data: Dict[str, Dict[str, List[float]]]):
        """Provide sparkline history data. Called by MainWindow.

        data = {host: {"cpu": [v1, v2, ...], "ram": [v1, v2, ...]}}.
        """
        self._spark_data = data

    def set_alerts(self, alerts: List[Dict]):
        """Provide recent alerts for the summary panel ticker."""
        self._alerts = alerts
