"""Dialog for adding or editing a server configuration."""

import customtkinter as ctk
from typing import Optional, Callable
import threading

from app.models import ServerConfig
from app.utils.crypto import encrypt_password, decrypt_password
from app.ui.styles import COLORS, FONTS


class AddServerDialog(ctk.CTkToplevel):
    """Modal dialog for adding/editing server configuration."""

    def __init__(self, parent, on_save: Callable, server: Optional[ServerConfig] = None):
        super().__init__(parent)
        self.on_save = on_save
        self.editing = server
        self.result = None

        # Window setup
        self.title("Editar Servidor" if server else "Agregar Servidor")
        self.geometry("500x620")
        self.resizable(False, False)
        self.configure(fg_color=COLORS["bg_dark"])
        self.transient(parent)
        self.grab_set()

        # Center on parent
        self.update_idletasks()
        x = parent.winfo_x() + (parent.winfo_width() // 2) - 250
        y = parent.winfo_y() + (parent.winfo_height() // 2) - 310
        self.geometry(f"+{x}+{y}")

        self._build_ui(server)

    def _build_ui(self, server: Optional[ServerConfig]):
        container = ctk.CTkFrame(self, fg_color="transparent")
        container.pack(fill="both", expand=True, padx=30, pady=20)

        # Title
        ctk.CTkLabel(
            container,
            text="Editar Servidor" if server else "Nuevo Servidor",
            font=FONTS["subtitle"],
            text_color=COLORS["text_primary"],
        ).pack(pady=(0, 20))

        # Name
        ctk.CTkLabel(container, text="Nombre (alias)", font=FONTS["small_bold"],
                      text_color=COLORS["text_secondary"]).pack(anchor="w")
        self.name_entry = ctk.CTkEntry(container, placeholder_text="Ej: Servidor Historia Clínica 1",
                                        height=38, font=FONTS["body"])
        self.name_entry.pack(fill="x", pady=(2, 10))

        # Host / IP
        ctk.CTkLabel(container, text="Dirección IP o Hostname *", font=FONTS["small_bold"],
                      text_color=COLORS["text_secondary"]).pack(anchor="w")
        self.host_entry = ctk.CTkEntry(container, placeholder_text="Ej: 192.168.14.65",
                                        height=38, font=FONTS["mono"])
        self.host_entry.pack(fill="x", pady=(2, 10))

        # Username
        ctk.CTkLabel(container, text="Usuario (dominio\\usuario o usuario) *", font=FONTS["small_bold"],
                      text_color=COLORS["text_secondary"]).pack(anchor="w")
        self.user_entry = ctk.CTkEntry(container, placeholder_text="Ej: DOMINIO\\Administrador",
                                        height=38, font=FONTS["body"])
        self.user_entry.pack(fill="x", pady=(2, 10))

        # Password
        ctk.CTkLabel(container, text="Contraseña *", font=FONTS["small_bold"],
                      text_color=COLORS["text_secondary"]).pack(anchor="w")
        self.pass_entry = ctk.CTkEntry(container, placeholder_text="••••••••", show="•",
                                        height=38, font=FONTS["body"])
        self.pass_entry.pack(fill="x", pady=(2, 10))

        # Port and SSL row
        row = ctk.CTkFrame(container, fg_color="transparent")
        row.pack(fill="x", pady=(0, 10))

        port_frame = ctk.CTkFrame(row, fg_color="transparent")
        port_frame.pack(side="left", fill="x", expand=True, padx=(0, 10))
        ctk.CTkLabel(port_frame, text="Puerto WinRM", font=FONTS["small_bold"],
                      text_color=COLORS["text_secondary"]).pack(anchor="w")
        self.port_entry = ctk.CTkEntry(port_frame, placeholder_text="5985", height=38, font=FONTS["mono"])
        self.port_entry.pack(fill="x", pady=(2, 0))

        ssl_frame = ctk.CTkFrame(row, fg_color="transparent")
        ssl_frame.pack(side="left")
        ctk.CTkLabel(ssl_frame, text="Usar SSL", font=FONTS["small_bold"],
                      text_color=COLORS["text_secondary"]).pack(anchor="w")
        self.ssl_var = ctk.BooleanVar(value=False)
        ctk.CTkSwitch(ssl_frame, text="HTTPS", variable=self.ssl_var,
                       onvalue=True, offvalue=False).pack(pady=(6, 0))

        # Thresholds row
        thresh_row = ctk.CTkFrame(container, fg_color="transparent")
        thresh_row.pack(fill="x", pady=(0, 15))

        warn_frame = ctk.CTkFrame(thresh_row, fg_color="transparent")
        warn_frame.pack(side="left", fill="x", expand=True, padx=(0, 10))
        ctk.CTkLabel(warn_frame, text="Alerta (usuarios)", font=FONTS["small_bold"],
                      text_color=COLORS["warning"]).pack(anchor="w")
        self.warn_entry = ctk.CTkEntry(warn_frame, placeholder_text="10", height=38, font=FONTS["mono"])
        self.warn_entry.pack(fill="x", pady=(2, 0))

        crit_frame = ctk.CTkFrame(thresh_row, fg_color="transparent")
        crit_frame.pack(side="left", fill="x", expand=True)
        ctk.CTkLabel(crit_frame, text="Crítico (usuarios)", font=FONTS["small_bold"],
                      text_color=COLORS["critical"]).pack(anchor="w")
        self.crit_entry = ctk.CTkEntry(crit_frame, placeholder_text="15", height=38, font=FONTS["mono"])
        self.crit_entry.pack(fill="x", pady=(2, 0))

        # Status label
        self.status_label = ctk.CTkLabel(container, text="", font=FONTS["small"],
                                          text_color=COLORS["text_muted"])
        self.status_label.pack(pady=(0, 5))

        # Buttons
        btn_row = ctk.CTkFrame(container, fg_color="transparent")
        btn_row.pack(fill="x")

        ctk.CTkButton(
            btn_row, text="Probar Conexión", font=FONTS["body_bold"],
            fg_color=COLORS["bg_card"], hover_color=COLORS["bg_card_hover"],
            height=40, command=self._test_connection,
        ).pack(side="left", padx=(0, 10))

        ctk.CTkButton(
            btn_row, text="Guardar", font=FONTS["body_bold"],
            fg_color=COLORS["accent"], hover_color=COLORS["accent_hover"],
            height=40, command=self._save,
        ).pack(side="right")

        ctk.CTkButton(
            btn_row, text="Cancelar", font=FONTS["body_bold"],
            fg_color=COLORS["border"], hover_color=COLORS["text_muted"],
            height=40, command=self.destroy,
        ).pack(side="right", padx=(0, 10))

        # Pre-fill if editing
        if server:
            self.name_entry.insert(0, server.name)
            self.host_entry.insert(0, server.host)
            self.user_entry.insert(0, server.username)
            try:
                self.pass_entry.insert(0, decrypt_password(server.encrypted_password))
            except Exception:
                pass
            self.port_entry.insert(0, str(server.port))
            self.ssl_var.set(server.use_ssl)
            self.warn_entry.insert(0, str(server.max_users_warning))
            self.crit_entry.insert(0, str(server.max_users_critical))

    def _build_server_config(self) -> Optional[ServerConfig]:
        """Validate and build ServerConfig from form fields."""
        host = self.host_entry.get().strip()
        username = self.user_entry.get().strip()
        password = self.pass_entry.get().strip()

        if not host or not username:
            self.status_label.configure(text="⚠ IP/Host y Usuario son obligatorios",
                                         text_color=COLORS["warning"])
            return None

        # Only require password for new servers or if changed
        if not password and not self.editing:
            self.status_label.configure(text="⚠ La contraseña es obligatoria",
                                         text_color=COLORS["warning"])
            return None

        port_str = self.port_entry.get().strip()
        port = int(port_str) if port_str.isdigit() else (5986 if self.ssl_var.get() else 5985)

        warn_str = self.warn_entry.get().strip()
        crit_str = self.crit_entry.get().strip()

        enc_pass = encrypt_password(password) if password else self.editing.encrypted_password

        return ServerConfig(
            name=self.name_entry.get().strip(),
            host=host,
            username=username,
            encrypted_password=enc_pass,
            port=port,
            use_ssl=self.ssl_var.get(),
            max_users_warning=int(warn_str) if warn_str.isdigit() else 10,
            max_users_critical=int(crit_str) if crit_str.isdigit() else 15,
        )

    def _test_connection(self):
        """Test connection in background thread."""
        config = self._build_server_config()
        if not config:
            return
        self.status_label.configure(text="🔄 Probando conexión...", text_color=COLORS["text_secondary"])

        def _test():
            from app.server_manager import test_connection
            success, msg = test_connection(config)
            self.after(0, lambda: self.status_label.configure(
                text=f"{'✅' if success else '❌'} {msg}",
                text_color=COLORS["success"] if success else COLORS["critical"],
            ))

        threading.Thread(target=_test, daemon=True).start()

    def _save(self):
        config = self._build_server_config()
        if config:
            self.on_save(config, self.editing)
            self.destroy()
