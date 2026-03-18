"""Dashboard view — grid of server cards with live status, filters, and grid size control."""

import customtkinter as ctk
from typing import Dict, List, Tuple
from collections import Counter

from app.models import ServerStatus
from app.ui.styles import COLORS, FONTS


class DashboardView(ctk.CTkFrame):
    """Main dashboard showing all servers as status cards with filtering."""

    GRID_OPTIONS = {"Pequeño (5)": 5, "Normal (4)": 4, "Grande (3)": 3, "XL (2)": 2}

    def __init__(self, parent, on_server_click, on_add_server, on_edit_server, on_delete_server):
        super().__init__(parent, fg_color=COLORS["bg_dark"])
        self.on_server_click = on_server_click
        self.on_add_server = on_add_server
        self.on_edit_server = on_edit_server
        self.on_delete_server = on_delete_server
        self.cards: Dict[str, ctk.CTkFrame] = {}
        self._all_statuses: Dict[str, ServerStatus] = {}
        self._cols = 3
        self._active_filters: Dict[str, str] = {}  # filter_type -> value
        self._build_ui()

    def _build_ui(self):
        # ─── Header ───
        header = ctk.CTkFrame(self, fg_color="transparent", height=60)
        header.pack(fill="x", padx=20, pady=(15, 5))
        header.pack_propagate(False)

        ctk.CTkLabel(header, text="🖥  ServerC Monitor HUV", font=FONTS["title"],
                      text_color=COLORS["text_primary"]).pack(side="left")

        self.add_btn = ctk.CTkButton(
            header, text="＋ Agregar Servidor", font=FONTS["body_bold"],
            fg_color=COLORS["accent"], hover_color=COLORS["accent_hover"],
            height=38, width=180, command=self.on_add_server,
        )
        self.add_btn.pack(side="right")

        # ─── Search + Grid Size row ───
        search_row = ctk.CTkFrame(self, fg_color="transparent")
        search_row.pack(fill="x", padx=20, pady=(5, 3))

        # Search entry
        self.search_var = ctk.StringVar()
        self.search_var.trace_add("write", lambda *_: self._apply_filters())
        self.search_entry = ctk.CTkEntry(
            search_row, textvariable=self.search_var,
            placeholder_text="🔍  Buscar por nombre, IP, usuario...",
            height=38, font=FONTS["body"], width=400,
            corner_radius=10,
        )
        self.search_entry.pack(side="left", fill="x", expand=True, padx=(0, 10))

        # Grid size selector
        grid_frame = ctk.CTkFrame(search_row, fg_color="transparent")
        grid_frame.pack(side="right")
        ctk.CTkLabel(grid_frame, text="Grid:", font=FONTS["small_bold"],
                      text_color=COLORS["text_muted"]).pack(side="left", padx=(0, 5))
        self.grid_selector = ctk.CTkSegmentedButton(
            grid_frame, values=["5", "4", "3", "2"],
            command=self._on_grid_change, font=FONTS["small_bold"],
            height=32,
        )
        self.grid_selector.set("3")
        self.grid_selector.pack(side="left")

        # ─── Filter chips row (scrollable) ───
        self._filter_outer = ctk.CTkFrame(self, fg_color="transparent", height=38)
        self._filter_outer.pack(fill="x", padx=20, pady=(3, 3))
        self._filter_outer.pack_propagate(False)

        self._filter_canvas = ctk.CTkCanvas(
            self._filter_outer, highlightthickness=0,
            bg=self._apply_appearance_mode(COLORS["bg_dark"]),
            height=36,
        )
        self._filter_canvas.pack(side="left", fill="both", expand=True)

        self.filter_row = ctk.CTkFrame(self._filter_canvas, fg_color="transparent")
        self._filter_window = self._filter_canvas.create_window((0, 0), window=self.filter_row, anchor="nw")

        self.filter_row.bind("<Configure>", lambda e: self._filter_canvas.configure(
            scrollregion=self._filter_canvas.bbox("all")))

        # Mouse wheel horizontal scroll on filter area
        def _on_filter_scroll(event):
            self._filter_canvas.xview_scroll(int(-1 * (event.delta / 120)), "units")
        self._filter_canvas.bind("<MouseWheel>", _on_filter_scroll)
        self.filter_row.bind("<MouseWheel>", _on_filter_scroll)

        # Scroll arrows
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

        # ─── Summary bar ───
        self.summary_frame = ctk.CTkFrame(self, fg_color=COLORS["bg_medium"], corner_radius=10, height=40)
        self.summary_frame.pack(fill="x", padx=20, pady=(3, 8))
        self.summary_frame.pack_propagate(False)

        self.summary_label = ctk.CTkLabel(
            self.summary_frame, text="Cargando servidores...",
            font=FONTS["body"], text_color=COLORS["text_secondary"],
        )
        self.summary_label.pack(side="left", padx=15)

        self.filter_info_label = ctk.CTkLabel(
            self.summary_frame, text="",
            font=FONTS["small"], text_color=COLORS["accent"],
        )
        self.filter_info_label.pack(side="left", padx=5)

        self.last_update_label = ctk.CTkLabel(
            self.summary_frame, text="",
            font=FONTS["small"], text_color=COLORS["text_muted"],
        )
        self.last_update_label.pack(side="right", padx=15)

        # ─── Scrollable grid area ───
        self.grid_scroll = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self.grid_scroll.pack(fill="both", expand=True, padx=15, pady=(0, 15))

    # ─── Grid size ───

    def _on_grid_change(self, value: str):
        self._cols = int(value)
        self._apply_filters()

    # ─── Filter logic ───

    def _get_unique_names(self) -> List[str]:
        """Get server names that appear more than once (groups)."""
        names = [s.server.name for s in self._all_statuses.values() if s.server.name]
        counts = Counter(names)
        return sorted([n for n, c in counts.items() if c > 1])

    def _build_filter_chips(self):
        """Build dynamic filter chip buttons."""
        for w in self.filter_row.winfo_children():
            w.destroy()

        statuses = self._all_statuses

        if not statuses:
            self._scroll_left_btn.pack_forget()
            self._scroll_right_btn.pack_forget()
            return

        # "Todos" chip (clear filters)
        self._add_chip("Todos", "all", "all", is_clear=True)

        # Status filters
        online_count = sum(1 for s in statuses.values() if s.is_online)
        offline_count = len(statuses) - online_count
        self._add_chip(f"✅ En línea ({online_count})", "status", "online")
        self._add_chip(f"❌ Sin conexión ({offline_count})", "status", "offline")

        # Load filters
        warning_count = sum(1 for s in statuses.values() if s.is_online and s.load_level == "warning")
        critical_count = sum(1 for s in statuses.values() if s.is_online and s.load_level == "critical")
        if warning_count:
            self._add_chip(f"⚠ Precaución ({warning_count})", "load", "warning")
        if critical_count:
            self._add_chip(f"🔴 Sobrecarga ({critical_count})", "load", "critical")

        # Separator
        sep = ctk.CTkLabel(self.filter_row, text="│", font=FONTS["body"],
                            text_color=COLORS["text_muted"])
        sep.pack(side="left", padx=6)

        # Name group filters — ALL groups, no limit
        groups = self._get_unique_names()
        for name in groups:
            count = sum(1 for s in statuses.values() if s.server.name == name)
            self._add_chip(f"{name} ({count})", "group", name)

        # Show/hide scroll arrows based on content overflow
        self.filter_row.update_idletasks()
        content_width = self.filter_row.winfo_reqwidth()
        canvas_width = self._filter_canvas.winfo_width()
        if content_width > canvas_width and canvas_width > 1:
            self._scroll_left_btn.pack(side="left", padx=(4, 0))
            self._scroll_right_btn.pack(side="right", padx=(0, 0))
        else:
            self._scroll_left_btn.pack_forget()
            self._scroll_right_btn.pack_forget()

    def _add_chip(self, text: str, filter_type: str, value: str, is_clear: bool = False):
        is_active = (not self._active_filters and is_clear) or \
                    self._active_filters.get(filter_type) == value

        fg = COLORS["accent"] if is_active else COLORS["bg_card"]
        hover = COLORS["accent_hover"] if is_active else COLORS["bg_card_hover"]
        text_color = COLORS["bg_dark"] if is_active else COLORS["text_secondary"]

        btn = ctk.CTkButton(
            self.filter_row, text=text, font=FONTS["small_bold"],
            fg_color=fg, hover_color=hover, text_color=text_color,
            height=28, corner_radius=14,
            command=lambda: self._toggle_filter(filter_type, value, is_clear),
        )
        btn.pack(side="left", padx=2)
        # Propagate mouse wheel to canvas for scrolling
        btn.bind("<MouseWheel>", lambda e: self._filter_canvas.xview_scroll(
            int(-1 * (e.delta / 120)), "units"))

    def _toggle_filter(self, filter_type: str, value: str, is_clear: bool):
        if is_clear:
            self._active_filters.clear()
        elif self._active_filters.get(filter_type) == value:
            del self._active_filters[filter_type]
        else:
            self._active_filters[filter_type] = value
        self._apply_filters()

    def _filter_statuses(self) -> Dict[str, ServerStatus]:
        """Apply all active filters and search query to statuses."""
        result = dict(self._all_statuses)
        search = self.search_var.get().strip().lower()

        # Text search
        if search:
            result = {
                host: s for host, s in result.items()
                if search in s.server.name.lower()
                or search in s.server.host.lower()
                or search in s.server.username.lower()
                or search in host.lower()
                or any(search in sess.username.lower() for sess in s.sessions)
            }

        # Status filter
        status_filter = self._active_filters.get("status")
        if status_filter == "online":
            result = {h: s for h, s in result.items() if s.is_online}
        elif status_filter == "offline":
            result = {h: s for h, s in result.items() if not s.is_online}

        # Load filter
        load_filter = self._active_filters.get("load")
        if load_filter:
            result = {h: s for h, s in result.items() if s.is_online and s.load_level == load_filter}

        # Group (name) filter
        group_filter = self._active_filters.get("group")
        if group_filter:
            result = {h: s for h, s in result.items() if s.server.name == group_filter}

        return result

    def _apply_filters(self):
        """Re-render cards with current filters."""
        filtered = self._filter_statuses()
        self._render_cards(filtered)
        self._build_filter_chips()

        total = len(self._all_statuses)
        shown = len(filtered)
        if shown < total:
            self.filter_info_label.configure(text=f"Mostrando {shown} de {total}")
        else:
            self.filter_info_label.configure(text="")

    # ─── Rendering ───

    def _render_cards(self, statuses: Dict[str, ServerStatus]):
        """Render the card grid."""
        for widget in self.grid_scroll.winfo_children():
            widget.destroy()
        self.cards.clear()

        if not statuses:
            if self._all_statuses:
                msg = "No hay servidores que coincidan con los filtros."
            else:
                msg = "No hay servidores configurados.\nHaz clic en '＋ Agregar Servidor' para comenzar."
            ctk.CTkLabel(self.grid_scroll, text=msg,
                          font=FONTS["body"], text_color=COLORS["text_muted"],
                          justify="center").pack(pady=60)
            return

        row_frame = None
        for i, (host, status) in enumerate(statuses.items()):
            if i % self._cols == 0:
                row_frame = ctk.CTkFrame(self.grid_scroll, fg_color="transparent")
                row_frame.pack(fill="x", pady=4)

            card = self._create_server_card(row_frame, status)
            card.pack(side="left", fill="both", expand=True, padx=4, pady=4)
            self.cards[host] = card

    def update_all(self, statuses: Dict[str, ServerStatus]):
        """Refresh all server cards with new statuses (called from main window)."""
        self._all_statuses = statuses

        # Summary (always shows totals, unfiltered)
        if statuses:
            online_count = sum(1 for s in statuses.values() if s.is_online)
            total_users = sum(s.total_sessions for s in statuses.values() if s.is_online)
            total = len(statuses)
            self.summary_label.configure(
                text=f"📊 {total} servidores  |  ✅ {online_count} en línea  |  "
                     f"❌ {total - online_count} sin conexión  |  👥 {total_users} usuarios"
            )
        else:
            self.summary_label.configure(text="Sin servidores configurados")

        from datetime import datetime
        self.last_update_label.configure(
            text=f"Última actualización: {datetime.now().strftime('%H:%M:%S')}"
        )

        self._apply_filters()

    def update_single(self, host: str, status: ServerStatus):
        """Update a single server status incrementally (called as results arrive)."""
        self._all_statuses[host] = status
        # Refresh summary counts
        statuses = self._all_statuses
        online_count = sum(1 for s in statuses.values() if s.is_online)
        total_users = sum(s.total_sessions for s in statuses.values() if s.is_online)
        total = len(statuses)
        self.summary_label.configure(
            text=f"📊 {total} servidores  |  ✅ {online_count} en línea  |  "
                 f"❌ {total - online_count} sin conexión  |  👥 {total_users} usuarios"
        )
        from datetime import datetime
        self.last_update_label.configure(
            text=f"Última actualización: {datetime.now().strftime('%H:%M:%S')}"
        )
        # Re-render with filters
        self._apply_filters()

    def _create_server_card(self, parent, status: ServerStatus) -> ctk.CTkFrame:
        """Create a single server status card."""
        load = status.load_level
        if not status.is_online:
            card_bg = COLORS["bg_card"]
        elif load == "critical":
            card_bg = "#3d1520"
        elif load == "warning":
            card_bg = "#3d2e15"
        else:
            card_bg = COLORS["bg_card"]

        card = ctk.CTkFrame(parent, fg_color=card_bg, corner_radius=14, height=200)
        card.pack_propagate(False)

        def on_click(e, h=status.server.host):
            self.on_server_click(h)

        card.bind("<Button-1>", on_click)

        inner = ctk.CTkFrame(card, fg_color="transparent")
        inner.pack(fill="both", expand=True, padx=15, pady=12)
        inner.bind("<Button-1>", on_click)

        # Top row: name + status dot
        top_row = ctk.CTkFrame(inner, fg_color="transparent")
        top_row.pack(fill="x")
        top_row.bind("<Button-1>", on_click)

        color = COLORS["online"] if status.is_online else COLORS["offline"]
        dot = ctk.CTkLabel(top_row, text="●", font=("Segoe UI", 14), text_color=color)
        dot.pack(side="left")
        dot.bind("<Button-1>", on_click)

        name_lbl = ctk.CTkLabel(top_row, text=status.server.display_name,
                                 font=FONTS["heading"], text_color=COLORS["text_primary"])
        name_lbl.pack(side="left", padx=(6, 0))
        name_lbl.bind("<Button-1>", on_click)

        # Edit/delete buttons
        btn_frame = ctk.CTkFrame(top_row, fg_color="transparent")
        btn_frame.pack(side="right")

        ctk.CTkButton(
            btn_frame, text="✏", width=28, height=28, font=("Segoe UI", 12),
            fg_color="transparent", hover_color=COLORS["bg_card_hover"],
            command=lambda h=status.server.host: self.on_edit_server(h),
        ).pack(side="left", padx=2)

        ctk.CTkButton(
            btn_frame, text="🗑", width=28, height=28, font=("Segoe UI", 12),
            fg_color="transparent", hover_color=COLORS["critical"],
            command=lambda h=status.server.host: self.on_delete_server(h),
        ).pack(side="left")

        # Host IP
        ip_lbl = ctk.CTkLabel(inner, text=status.server.host, font=FONTS["mono"],
                                text_color=COLORS["text_muted"])
        ip_lbl.pack(anchor="w", pady=(2, 8))
        ip_lbl.bind("<Button-1>", on_click)

        if status.is_online:
            user_row = ctk.CTkFrame(inner, fg_color="transparent")
            user_row.pack(fill="x")
            user_row.bind("<Button-1>", on_click)

            user_color = COLORS["text_primary"]
            if load == "critical":
                user_color = COLORS["critical"]
            elif load == "warning":
                user_color = COLORS["warning"]

            ctk.CTkLabel(user_row, text=str(status.total_sessions),
                          font=FONTS["mono_large"], text_color=user_color).pack(side="left")
            lbl = ctk.CTkLabel(user_row, text=f" sesiones ({status.active_users} activas)",
                          font=FONTS["small"], text_color=COLORS["text_secondary"])
            lbl.pack(side="left", pady=(5, 0))
            lbl.bind("<Button-1>", on_click)

            if status.metrics:
                m = status.metrics
                metrics_row = ctk.CTkFrame(inner, fg_color="transparent")
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

                    ctk.CTkLabel(item, text=f"{label}: {val:.0f}%", font=FONTS["small_bold"],
                                  text_color=mc).pack()

            if load != "normal":
                load_text = "⚠ SOBRECARGADO" if load == "critical" else "⚠ PRECAUCIÓN"
                load_color = COLORS["critical"] if load == "critical" else COLORS["warning"]
                load_lbl = ctk.CTkLabel(inner, text=load_text, font=FONTS["small_bold"],
                                         text_color=load_color)
                load_lbl.pack(anchor="w", pady=(5, 0))
                load_lbl.bind("<Button-1>", on_click)
        else:
            err = status.error_message[:80] if status.error_message else "No se pudo conectar"
            err_lbl = ctk.CTkLabel(inner, text=f"❌ {err}", font=FONTS["small"],
                                    text_color=COLORS["critical"], wraplength=250)
            err_lbl.pack(anchor="w", pady=(5, 0))
            err_lbl.bind("<Button-1>", on_click)

        return card
