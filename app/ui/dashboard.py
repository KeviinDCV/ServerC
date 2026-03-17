"""Dashboard view — grid of server cards with live status."""

import customtkinter as ctk
from typing import Dict

from app.models import ServerStatus
from app.ui.styles import COLORS, FONTS


class DashboardView(ctk.CTkFrame):
    """Main dashboard showing all servers as status cards."""

    def __init__(self, parent, on_server_click, on_add_server, on_edit_server, on_delete_server):
        super().__init__(parent, fg_color=COLORS["bg_dark"])
        self.on_server_click = on_server_click
        self.on_add_server = on_add_server
        self.on_edit_server = on_edit_server
        self.on_delete_server = on_delete_server
        self.cards: Dict[str, ctk.CTkFrame] = {}
        self._build_ui()

    def _build_ui(self):
        # Header
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

        # Summary bar
        self.summary_frame = ctk.CTkFrame(self, fg_color=COLORS["bg_medium"], corner_radius=10, height=45)
        self.summary_frame.pack(fill="x", padx=20, pady=(5, 10))
        self.summary_frame.pack_propagate(False)

        self.summary_label = ctk.CTkLabel(
            self.summary_frame, text="Cargando servidores...",
            font=FONTS["body"], text_color=COLORS["text_secondary"],
        )
        self.summary_label.pack(side="left", padx=15)

        self.last_update_label = ctk.CTkLabel(
            self.summary_frame, text="",
            font=FONTS["small"], text_color=COLORS["text_muted"],
        )
        self.last_update_label.pack(side="right", padx=15)

        # Scrollable grid area
        self.grid_scroll = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self.grid_scroll.pack(fill="both", expand=True, padx=15, pady=(0, 15))

        # Empty state
        self.empty_label = ctk.CTkLabel(
            self.grid_scroll,
            text="No hay servidores configurados.\nHaz clic en '＋ Agregar Servidor' para comenzar.",
            font=FONTS["body"], text_color=COLORS["text_muted"], justify="center",
        )

    def update_all(self, statuses: Dict[str, ServerStatus]):
        """Refresh all server cards with new statuses."""
        # Clear existing cards
        for widget in self.grid_scroll.winfo_children():
            widget.destroy()
        self.cards.clear()

        if not statuses:
            self.empty_label = ctk.CTkLabel(
                self.grid_scroll,
                text="No hay servidores configurados.\nHaz clic en '＋ Agregar Servidor' para comenzar.",
                font=FONTS["body"], text_color=COLORS["text_muted"], justify="center",
            )
            self.empty_label.pack(pady=60)
            self.summary_label.configure(text="Sin servidores configurados")
            return

        # Create grid of cards (3 per row)
        row_frame = None
        online_count = 0
        total_users = 0

        for i, (host, status) in enumerate(statuses.items()):
            if i % 3 == 0:
                row_frame = ctk.CTkFrame(self.grid_scroll, fg_color="transparent")
                row_frame.pack(fill="x", pady=5)

            card = self._create_server_card(row_frame, status)
            card.pack(side="left", fill="both", expand=True, padx=5, pady=5)
            self.cards[host] = card

            if status.is_online:
                online_count += 1
                total_users += status.total_sessions

        total = len(statuses)
        self.summary_label.configure(
            text=f"📊 {total} servidores  |  ✅ {online_count} en línea  |  "
                 f"❌ {total - online_count} sin conexión  |  👥 {total_users} usuarios conectados"
        )

        # Update timestamp
        from datetime import datetime
        self.last_update_label.configure(
            text=f"Última actualización: {datetime.now().strftime('%H:%M:%S')}"
        )

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

        # Make entire card clickable
        def on_click(e, h=status.server.host):
            self.on_server_click(h)

        card.bind("<Button-1>", on_click)

        # Card content
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

        # Buttons (edit/delete) at top-right
        btn_frame = ctk.CTkFrame(top_row, fg_color="transparent")
        btn_frame.pack(side="right")

        edit_btn = ctk.CTkButton(
            btn_frame, text="✏", width=28, height=28, font=("Segoe UI", 12),
            fg_color="transparent", hover_color=COLORS["bg_card_hover"],
            command=lambda h=status.server.host: self.on_edit_server(h),
        )
        edit_btn.pack(side="left", padx=2)

        del_btn = ctk.CTkButton(
            btn_frame, text="🗑", width=28, height=28, font=("Segoe UI", 12),
            fg_color="transparent", hover_color=COLORS["critical"],
            command=lambda h=status.server.host: self.on_delete_server(h),
        )
        del_btn.pack(side="left")

        # Host IP
        ip_lbl = ctk.CTkLabel(inner, text=status.server.host, font=FONTS["mono"],
                                text_color=COLORS["text_muted"])
        ip_lbl.pack(anchor="w", pady=(2, 8))
        ip_lbl.bind("<Button-1>", on_click)

        if status.is_online:
            # Users section
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

            # Metrics bar
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

            # Load indicator
            if load != "normal":
                load_text = "⚠ SOBRECARGADO" if load == "critical" else "⚠ PRECAUCIÓN"
                load_color = COLORS["critical"] if load == "critical" else COLORS["warning"]
                load_lbl = ctk.CTkLabel(inner, text=load_text, font=FONTS["small_bold"],
                                         text_color=load_color)
                load_lbl.pack(anchor="w", pady=(5, 0))
                load_lbl.bind("<Button-1>", on_click)
        else:
            # Offline message
            err = status.error_message[:80] if status.error_message else "No se pudo conectar"
            err_lbl = ctk.CTkLabel(inner, text=f"❌ {err}", font=FONTS["small"],
                                    text_color=COLORS["critical"], wraplength=250)
            err_lbl.pack(anchor="w", pady=(5, 0))
            err_lbl.bind("<Button-1>", on_click)

        return card
