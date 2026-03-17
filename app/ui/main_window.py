"""Main application window — orchestrates dashboard, detail view, and background polling."""

import customtkinter as ctk
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, Optional
from collections import OrderedDict

from app.models import ServerConfig, ServerStatus
from app.config import load_servers, save_servers, add_server, remove_server, update_server
from app.server_manager import query_server
from app.ui.styles import COLORS
from app.ui.dashboard import DashboardView
from app.ui.server_detail import ServerDetailView
from app.ui.add_server import AddServerDialog


class MainWindow(ctk.CTk):
    """Main application window."""

    POLL_INTERVAL_MS = 30_000  # 30 seconds
    MAX_WORKERS = 15  # parallel WinRM queries

    def __init__(self):
        super().__init__()

        # Window configuration
        self.title("ServerC Monitor HUV")
        self.geometry("1200x750")
        self.minsize(900, 600)
        self.configure(fg_color=COLORS["bg_dark"])

        # Try to set icon
        try:
            import os, sys
            from PIL import Image, ImageTk

            # When compiled: _MEIPASS/assets/  When running from source: project/assets/
            if getattr(sys, '_MEIPASS', None):
                assets_dir = os.path.join(sys._MEIPASS, "assets")
            else:
                assets_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "assets")

            icon_png = os.path.join(assets_dir, "favicon.png")
            icon_ico = os.path.join(assets_dir, "icon.ico")

            if os.path.exists(icon_png):
                img = Image.open(icon_png)
                self._icon_img = ImageTk.PhotoImage(img)
                self.wm_iconphoto(True, self._icon_img)
            elif os.path.exists(icon_ico):
                self.iconbitmap(icon_ico)
        except Exception as e:
            print("Icon load error:", e)

        # State
        self.servers: list = load_servers()
        self.statuses: Dict[str, ServerStatus] = OrderedDict()
        self.selected_host: Optional[str] = None
        self._polling = True
        self._poll_job = None

        # Build views
        self.dashboard = DashboardView(
            self,
            on_server_click=self._on_server_click,
            on_add_server=self._on_add_server,
            on_edit_server=self._on_edit_server,
            on_delete_server=self._on_delete_server,
        )
        self.detail_view = ServerDetailView(self, on_back=self._show_dashboard)

        # Show servers immediately (before polling) as "Loading" cards
        self._init_statuses()

        self._show_dashboard()
        self._start_polling()

        # Graceful shutdown
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _init_statuses(self):
        """Create placeholder statuses so dashboard shows all servers immediately."""
        for server in self.servers:
            self.statuses[server.host] = ServerStatus(
                server=server,
                is_online=False,
                error_message="Consultando servidor...",
            )

    # --- Navigation ---

    def _show_dashboard(self):
        """Switch to dashboard view."""
        self.selected_host = None
        self.detail_view.pack_forget()
        self.dashboard.pack(fill="both", expand=True)
        self.dashboard.update_all(self.statuses)

    def _show_detail(self, host: str):
        """Switch to server detail view."""
        self.selected_host = host
        self.dashboard.pack_forget()
        self.detail_view.pack(fill="both", expand=True)
        status = self.statuses.get(host)
        if status:
            self.detail_view.update_status(status)

    def _on_server_click(self, host: str):
        self._show_detail(host)

    # --- Server CRUD ---

    def _on_add_server(self):
        AddServerDialog(self, on_save=self._save_new_server)

    def _save_new_server(self, config: ServerConfig, editing: Optional[ServerConfig]):
        if editing:
            self.servers = update_server(editing.host, config)
        else:
            self.servers = add_server(config)
        self._refresh_now()

    def _on_edit_server(self, host: str):
        server = next((s for s in self.servers if s.host == host), None)
        if server:
            AddServerDialog(self, on_save=self._save_new_server, server=server)

    def _on_delete_server(self, host: str):
        server = next((s for s in self.servers if s.host == host), None)
        if not server:
            return
        dialog = ctk.CTkInputDialog(
            text=f"Escribe 'ELIMINAR' para confirmar la eliminación de\n{server.display_name} ({host})",
            title="Confirmar Eliminación",
        )
        result = dialog.get_input()
        if result and result.strip().upper() == "ELIMINAR":
            self.servers = remove_server(host)
            self.statuses.pop(host, None)
            self._show_dashboard()

    # --- Polling ---

    def _start_polling(self):
        """Start background polling of all servers."""
        self._poll_once()

    def _poll_once(self):
        """Query all servers in parallel using a thread pool, then schedule next poll."""
        if not self._polling:
            return

        servers_snapshot = list(self.servers)

        def _work():
            new_statuses = OrderedDict()
            # Pre-fill in order so dict keeps server list order
            for server in servers_snapshot:
                new_statuses[server.host] = None

            def _query_one(server):
                try:
                    return server.host, query_server(server)
                except Exception as e:
                    return server.host, ServerStatus(
                        server=server, is_online=False,
                        error_message=str(e),
                    )

            with ThreadPoolExecutor(max_workers=self.MAX_WORKERS) as pool:
                futures = {pool.submit(_query_one, s): s for s in servers_snapshot}
                for future in as_completed(futures):
                    if not self._polling:
                        return
                    host, status = future.result()
                    new_statuses[host] = status
                    # Push incremental update to UI
                    if self._polling:
                        self.after(0, lambda h=host, st=status: self._on_single_update(h, st))

            if self._polling:
                self.after(0, lambda: self._on_poll_complete(new_statuses))

        threading.Thread(target=_work, daemon=True).start()

    def _on_single_update(self, host: str, status: ServerStatus):
        """Update a single server's status in real time as results arrive."""
        self.statuses[host] = status
        if self.selected_host == host:
            self.detail_view.update_status(status)
        elif not self.selected_host:
            self.dashboard.update_single(host, status)

    def _on_poll_complete(self, new_statuses: Dict[str, ServerStatus]):
        """Called on main thread when polling completes."""
        self.statuses = new_statuses

        if self.selected_host:
            # Update detail view
            status = self.statuses.get(self.selected_host)
            if status:
                self.detail_view.update_status(status)
        else:
            # Update dashboard
            self.dashboard.update_all(self.statuses)

        # Schedule next poll
        if self._polling:
            self._poll_job = self.after(self.POLL_INTERVAL_MS, self._poll_once)

    def _refresh_now(self):
        """Cancel pending poll and refresh immediately."""
        if self._poll_job:
            self.after_cancel(self._poll_job)
            self._poll_job = None
        self._poll_once()

    # --- Cleanup ---

    def _on_close(self):
        self._polling = False
        if self._poll_job:
            self.after_cancel(self._poll_job)
        self.destroy()
