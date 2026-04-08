"""Server detail view — shows sessions and metrics for a single server."""

import re
import threading
import customtkinter as ctk
from typing import Optional

from app.models import ServerStatus, UserSession
from app.ui.styles import COLORS, FONTS


def _format_idle_time(raw: str) -> str:
    """Convert quser idle time to human-readable Spanish format.
    
    Formats: '.' -> Activo, '10' -> 10 min, '1:07' -> 1h 07m,
             '3+18:09' -> 3d 18h 09m, 'none' -> Activo
    """
    if not raw or raw in (".", "none", "Ninguno"):
        return "Activo"

    # Days + hours:minutes  e.g. "3+18:09"
    m = re.match(r"^(\d+)\+(\d+):(\d+)$", raw)
    if m:
        d, h, mi = m.groups()
        return f"{d}d {h}h {mi}m"

    # Hours:minutes  e.g. "1:07"
    m = re.match(r"^(\d+):(\d+)$", raw)
    if m:
        h, mi = m.groups()
        return f"{h}h {mi}m"

    # Just minutes  e.g. "10"
    if raw.isdigit():
        mins = int(raw)
        if mins >= 60:
            return f"{mins // 60}h {mins % 60:02d}m"
        return f"{mins} min"

    return raw


class ServerDetailView(ctk.CTkFrame):
    """Panel showing full details of a selected server."""

    def __init__(self, parent, on_back: callable):
        super().__init__(parent, fg_color=COLORS["bg_dark"])
        self.on_back = on_back
        self._build_ui()

    def _build_ui(self):
        # Top bar
        top = ctk.CTkFrame(self, fg_color="transparent", height=50)
        top.pack(fill="x", padx=20, pady=(15, 5))
        top.pack_propagate(False)

        self.back_btn = ctk.CTkButton(
            top, text="← Volver", font=FONTS["body_bold"], width=100, height=35,
            fg_color=COLORS["bg_card"], hover_color=COLORS["bg_card_hover"],
            command=self.on_back,
        )
        self.back_btn.pack(side="left")

        self.server_title = ctk.CTkLabel(top, text="", font=FONTS["subtitle"],
                                          text_color=COLORS["text_primary"])
        self.server_title.pack(side="left", padx=15)

        self.status_badge = ctk.CTkLabel(top, text="", font=FONTS["small_bold"],
                                          corner_radius=8, width=80, height=26)
        self.status_badge.pack(side="left")

        # Send message button (right side of top bar)
        self.msg_btn = ctk.CTkButton(
            top, text="💬 Enviar Mensaje", font=FONTS["small_bold"],
            fg_color=COLORS["accent"], hover_color=COLORS["accent_hover"],
            height=35, width=160, command=self._on_send_message,
        )
        self.msg_btn.pack(side="right")

        # Metrics cards row
        self.metrics_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.metrics_frame.pack(fill="x", padx=20, pady=10)

        self.metric_cards = {}
        metrics_config = [
            ("cpu", "CPU", "%"),
            ("ram", "RAM", "%"),
            ("disk", "Disco C:", "%"),
            ("users", "Sesiones", ""),
            ("processes", "Procesos", ""),
            ("uptime", "Uptime", "h"),
        ]
        for key, label, unit in metrics_config:
            card = self._create_metric_card(self.metrics_frame, label, "—", unit)
            card.pack(side="left", fill="both", expand=True, padx=5)
            self.metric_cards[key] = card

        # Sessions table
        table_header = ctk.CTkFrame(self, fg_color="transparent")
        table_header.pack(fill="x", padx=20, pady=(15, 5))
        ctk.CTkLabel(table_header, text="Sesiones de Usuario", font=FONTS["heading"],
                      text_color=COLORS["text_primary"]).pack(side="left")
        self.session_count_label = ctk.CTkLabel(table_header, text="", font=FONTS["small"],
                                                  text_color=COLORS["text_secondary"])
        self.session_count_label.pack(side="left", padx=10)

        # Table header row
        header_row = ctk.CTkFrame(self, fg_color=COLORS["bg_card"], corner_radius=8, height=36)
        header_row.pack(fill="x", padx=20, pady=(0, 2))
        header_row.pack_propagate(False)
        cols = ["Usuario", "Sesión", "Estado", "Inactivo", "Equipo Cliente", "Inicio Sesión", "Acciones"]
        for text in cols:
            lbl = ctk.CTkLabel(header_row, text=text, font=FONTS["small_bold"],
                                text_color=COLORS["text_secondary"])
            lbl.pack(side="left", fill="both", expand=True)

        # Scrollable sessions list
        self.sessions_scroll = ctk.CTkScrollableFrame(
            self, fg_color="transparent", corner_radius=0,
        )
        self.sessions_scroll.pack(fill="both", expand=True, padx=20, pady=(0, 15))

        # Error label
        self.error_label = ctk.CTkLabel(self, text="", font=FONTS["body"],
                                         text_color=COLORS["critical"])

    def _create_metric_card(self, parent, label: str, value: str, unit: str) -> ctk.CTkFrame:
        card = ctk.CTkFrame(parent, fg_color=COLORS["bg_card"], corner_radius=12, height=100)
        card.pack_propagate(False)

        ctk.CTkLabel(card, text=label, font=FONTS["metric_label"],
                      text_color=COLORS["text_secondary"]).pack(pady=(12, 0))

        val_frame = ctk.CTkFrame(card, fg_color="transparent")
        val_frame.pack()

        value_lbl = ctk.CTkLabel(val_frame, text=value, font=FONTS["metric_value"],
                                  text_color=COLORS["text_primary"])
        value_lbl.pack(side="left")
        card._value_label = value_lbl

        if unit:
            unit_lbl = ctk.CTkLabel(val_frame, text=unit, font=FONTS["small"],
                                     text_color=COLORS["text_muted"])
            unit_lbl.pack(side="left", padx=(2, 0), pady=(8, 0))

        return card

    def update_status(self, status: ServerStatus):
        """Update the view with new server status data."""
        self.current_status = status
        self.server_title.configure(text=status.server.display_name)

        if status.is_online:
            self.status_badge.configure(text="EN LÍNEA", fg_color=COLORS["online"],
                                         text_color=COLORS["bg_dark"])
            self.error_label.pack_forget()
        else:
            self.status_badge.configure(text="SIN CONEXIÓN", fg_color=COLORS["offline"],
                                         text_color=COLORS["text_primary"])
            if status.error_message:
                self.error_label.configure(text=f"Error: {status.error_message}")
                self.error_label.pack(fill="x", padx=20, pady=5)

        # Update metrics
        m = status.metrics
        if m:
            self._update_metric("cpu", f"{m.cpu_percent:.0f}", m.cpu_percent)
            self._update_metric("ram", f"{m.memory_percent:.0f}", m.memory_percent)
            self._update_metric("disk", f"{m.disk_percent:.0f}", m.disk_percent)
            self._update_metric("processes", f"{m.total_processes}", 0)
            self._update_metric("uptime", f"{m.uptime_hours:.0f}", 0)

        user_count = status.total_sessions
        self._update_metric("users", str(user_count), 0)

        load = status.load_level
        user_card = self.metric_cards["users"]
        if load == "critical":
            user_card.configure(fg_color=COLORS["critical_bg"])
        elif load == "warning":
            user_card.configure(fg_color=COLORS["warning_bg"])
        else:
            user_card.configure(fg_color=COLORS["bg_card"])

        # Update sessions
        self.session_count_label.configure(
            text=f"{status.active_users} activas / {status.total_sessions} total"
        )
        self._populate_sessions(status.sessions)

    def _update_metric(self, key: str, text: str, percent: float):
        card = self.metric_cards.get(key)
        if card:
            color = COLORS["text_primary"]
            if percent >= 90:
                color = COLORS["critical"]
            elif percent >= 70:
                color = COLORS["warning"]
            card._value_label.configure(text=text, text_color=color)

    def _populate_sessions(self, sessions: list):
        """Clear and repopulate session rows."""
        import threading
        from app.server_manager import logoff_user
        
        for widget in self.sessions_scroll.winfo_children():
            widget.destroy()

        if not sessions:
            ctk.CTkLabel(self.sessions_scroll, text="No hay sesiones activas",
                          font=FONTS["body"], text_color=COLORS["text_muted"]).pack(pady=30)
            return

        def _do_logoff(session_id, username):
            # Prompt for confirmation
            dialog = ctk.CTkInputDialog(
                text=f"Escribe 'CERRAR' para desconectar al usuario {username} (Sesión: {session_id})",
                title="Confirmar Cierre de Sesión"
            )
            result = dialog.get_input()
            if result and result.strip().upper() == "CERRAR":
                self.error_label.configure(text=f"Cerrando sesión de {username}...", text_color=COLORS["text_secondary"])
                self.error_label.pack(fill="x", padx=20, pady=5)
                
                def _bg_task():
                    success, msg = logoff_user(self.current_status.server, session_id)
                    self.after(0, lambda: self._on_logoff_result(success, msg))
                threading.Thread(target=_bg_task, daemon=True).start()

        for i, s in enumerate(sessions):
            row_color = COLORS["bg_medium"] if i % 2 == 0 else COLORS["bg_dark"]
            row = ctk.CTkFrame(self.sessions_scroll, fg_color=row_color, corner_radius=6, height=34)
            row.pack(fill="x", pady=1)
            row.pack_propagate(False)

            state_color = COLORS["success"] if s.state.lower() in ("active", "activo") else COLORS["text_muted"]

            values = [
                (s.username, COLORS["text_primary"], FONTS["body_bold"]),
                (s.session_id, COLORS["text_secondary"], FONTS["mono"]),
                (s.state, state_color, FONTS["small_bold"]),
                (_format_idle_time(s.idle_time), COLORS["text_secondary"], FONTS["mono"]),
                (s.client_name or "—", COLORS["text_secondary"], FONTS["body"]),
                (s.logon_time, COLORS["text_secondary"], FONTS["small"]),
            ]
            
            # Pack all text labels
            for text, color, font in values:
                lbl_container = ctk.CTkFrame(row, fg_color="transparent")
                lbl_container.pack(side="left", fill="both", expand=True)
                ctk.CTkLabel(lbl_container, text=text, font=font, text_color=color).pack(expand=True)
            
            # Action button container
            action_container = ctk.CTkFrame(row, fg_color="transparent")
            action_container.pack(side="left", fill="both", expand=True)
            
            # Ensure "Services" / "Console" session isn't easily killed by mistake, though the prompt stops them
            if str(s.session_id) != "0":
                btn = ctk.CTkButton(
                    action_container, text="Cerrar", width=60, height=24,
                    font=FONTS["small_bold"], fg_color=COLORS["critical"],
                    hover_color="#c0392b",
                    command=lambda sid=s.session_id, u=s.username: _do_logoff(sid, u)
                )
                btn.pack(expand=True, pady=4)

    def _on_logoff_result(self, success: bool, msg: str):
        color = COLORS["success"] if success else COLORS["critical"]
        self.error_label.configure(text=msg, text_color=color)
        self.error_label.pack(fill="x", padx=20, pady=5)

    def _on_send_message(self):
        """Prompt for a message and send it to all sessions on this server."""
        from app.server_manager import send_message

        dialog = ctk.CTkInputDialog(
            text=f"Escribe el mensaje para los usuarios de\n{self.current_status.server.display_name}:",
            title="Enviar Mensaje a Usuarios",
        )
        msg_text = dialog.get_input()
        if not msg_text or not msg_text.strip():
            return

        msg_text = msg_text.strip()
        self.error_label.configure(
            text=f"Enviando mensaje a usuarios de {self.current_status.server.display_name}...",
            text_color=COLORS["text_secondary"],
        )
        self.error_label.pack(fill="x", padx=20, pady=5)

        def _bg():
            success, result = send_message(self.current_status.server, msg_text)
            self.after(0, lambda: self._on_message_result(success, result))

        threading.Thread(target=_bg, daemon=True).start()

    def _on_message_result(self, success: bool, msg: str):
        color = COLORS["success"] if success else COLORS["critical"]
        self.error_label.configure(text=msg, text_color=color)
        self.error_label.pack(fill="x", padx=20, pady=5)

