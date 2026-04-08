"""Main application window — orchestrates dashboard, detail view, and background polling."""

import customtkinter as ctk
import threading
import logging
import queue
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
from app.history import record_statuses, get_series, purge_old, close as close_history
from app.alerts import AlertManager
from app.export import export_csv

log = logging.getLogger(__name__)


class MainWindow(ctk.CTk):
    """Main application window."""

    POLL_INTERVAL_MS = 30_000  # 30 seconds
    MAX_WORKERS = 15  # parallel WinRM queries
    _DEBOUNCE_MS = 1000  # batch UI updates to at most once per second

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
        self._debounce_job = None
        self._pending_count = 0
        self._total_servers = len(self.servers)
        self._alert_mgr = AlertManager()
        self._purge_counter = 0  # purge old history every N polls
        self._ui_queue: queue.Queue = queue.Queue()  # thread-safe queue for bg→main thread

        # Build views
        self.dashboard = DashboardView(
            self,
            on_server_click=self._on_server_click,
            on_add_server=self._on_add_server,
            on_edit_server=self._on_edit_server,
            on_delete_server=self._on_delete_server,
            on_export=self._on_export,
            on_send_message=self._on_send_message_bulk,
        )
        self.detail_view = ServerDetailView(self, on_back=self._show_dashboard)

        # Show servers immediately (before polling) as "Loading" cards
        self._init_statuses()

        self._show_dashboard()
        self._start_polling()
        self._drain_ui_queue()  # start draining the thread-safe queue

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

    def _drain_ui_queue(self):
        """Process all pending callbacks from background threads (runs on main thread)."""
        try:
            while True:
                fn = self._ui_queue.get_nowait()
                try:
                    fn()
                except Exception:
                    log.exception("Error executing queued UI callback")
        except queue.Empty:
            pass
        # Re-schedule self every 100ms
        if self._polling:
            self.after(100, self._drain_ui_queue)

    def _start_polling(self):
        """Start background polling of all servers."""
        self._poll_once()

    def _poll_once(self):
        """Query all servers in parallel using a thread pool, then schedule next poll."""
        if not self._polling:
            return

        log.info("Starting poll cycle for %d servers", len(self.servers))
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
                    # Queue UI update on the main thread via the thread-safe queue
                    if self._polling:
                        self._ui_queue.put(lambda h=host, st=status: self._on_result_arrived(h, st))

            if self._polling:
                self._ui_queue.put(lambda: self._on_poll_complete(new_statuses))

        threading.Thread(target=_work, daemon=True).start()

    def _on_result_arrived(self, host: str, status: ServerStatus):
        """Store one result and schedule a debounced UI refresh."""
        try:
            self.statuses[host] = status
            self._pending_count += 1
            log.debug("Result: %s online=%s", host, status.is_online)

            # If detail view is open for this specific server, update immediately (cheap)
            if self.selected_host == host:
                self.detail_view.update_status(status)
                return

            # Update progress text cheaply (no re-render)
            if not self.selected_host:
                self.dashboard.update_progress(self._pending_count, self._total_servers)

            # Schedule a batched dashboard refresh (debounced)
            if self._debounce_job is None:
                self._debounce_job = self.after(self._DEBOUNCE_MS, self._flush_dashboard)
        except Exception:
            log.exception("Error in _on_result_arrived for %s", host)

    def _flush_dashboard(self):
        """Actually push accumulated status changes to the dashboard."""
        self._debounce_job = None
        try:
            if not self.selected_host:
                log.debug("Flushing dashboard with %d statuses", len(self.statuses))
                self.dashboard.update_all(self.statuses)
        except Exception:
            log.exception("Error in _flush_dashboard")

    def _on_poll_complete(self, new_statuses: Dict[str, ServerStatus]):
        """Called on main thread when polling completes."""
        self.statuses = new_statuses
        self._pending_count = 0
        log.info("Poll complete: %d servers, %d online",
                 len(new_statuses),
                 sum(1 for s in new_statuses.values() if s.is_online))

        # Cancel any pending debounce — we'll do the final render now
        if self._debounce_job is not None:
            self.after_cancel(self._debounce_job)
            self._debounce_job = None

        # Record history, check alerts, and build sparkline data in background
        threading.Thread(target=self._post_poll_work, args=(dict(new_statuses),),
                         daemon=True).start()

        try:
            if self.selected_host:
                status = self.statuses.get(self.selected_host)
                if status:
                    self.detail_view.update_status(status)
            else:
                self.dashboard.update_all(self.statuses)
        except Exception:
            log.exception("Error in _on_poll_complete UI update")

        # Schedule next poll
        if self._polling:
            self._poll_job = self.after(self.POLL_INTERVAL_MS, self._poll_once)

    def _post_poll_work(self, statuses: Dict[str, ServerStatus]):
        """Background: record history, evaluate alerts, build sparklines."""
        log.debug("_post_poll_work starting with %d statuses", len(statuses))
        try:
            record_statuses(statuses)
        except Exception:
            log.exception("Error in record_statuses")
        try:
            alerts = self._alert_mgr.check(statuses)
            if alerts or self._alert_mgr.alerts_log:
                recent = self._alert_mgr.get_recent(50)
                self._ui_queue.put(lambda: self.dashboard.set_alerts(recent))
        except Exception:
            log.exception("Error in alert check")
        try:
            spark = {}
            for host in statuses:
                cpu_data = get_series(host, "cpu", minutes=30)
                ram_data = get_series(host, "ram", minutes=30)
                spark[host] = {
                    "cpu": [v for _, v in cpu_data if v is not None],
                    "ram": [v for _, v in ram_data if v is not None],
                }
            self._ui_queue.put(lambda s=spark: self.dashboard.set_spark_data(s))
        except Exception:
            log.exception("Error building sparkline data")
        # Periodic purge (every ~20 polls = ~10 min)
        self._purge_counter += 1
        if self._purge_counter >= 20:
            self._purge_counter = 0
            try:
                purge_old(24)
            except Exception:
                pass

    def _on_export(self):
        """Export current server data to CSV."""
        export_csv(self.statuses, parent_window=self)

    def _on_send_message_bulk(self, visible_hosts: list):
        """Send a message to all users on visible/filtered servers."""
        from app.server_manager import send_message

        online_hosts = [h for h in visible_hosts
                        if self.statuses.get(h) and self.statuses[h].is_online]

        if not online_hosts:
            dialog = ctk.CTkInputDialog(
                text="No hay servidores en línea para enviar mensaje.",
                title="Sin servidores",
            )
            dialog.get_input()
            return

        dialog = ctk.CTkInputDialog(
            text=f"Escribe el mensaje para los usuarios de\n{len(online_hosts)} servidores en línea:",
            title="Mensaje Masivo a Usuarios",
        )
        msg_text = dialog.get_input()
        if not msg_text or not msg_text.strip():
            return
        msg_text = msg_text.strip()

        # Confirm
        confirm = ctk.CTkInputDialog(
            text=f"Se enviará a {len(online_hosts)} servidores:\n"
                 f"'{msg_text}'\n\nEscribe 'ENVIAR' para confirmar:",
            title="Confirmar Mensaje Masivo",
        )
        result = confirm.get_input()
        if not result or result.strip().upper() != "ENVIAR":
            return

        log.info("Sending bulk message to %d servers", len(online_hosts))

        def _bg():
            results = []
            servers_map = {s.host: s for s in self.servers}
            for host in online_hosts:
                server = servers_map.get(host)
                if server:
                    ok, msg = send_message(server, msg_text)
                    results.append((host, ok, msg))
            self._ui_queue.put(lambda r=results: self._on_bulk_message_done(r))

        threading.Thread(target=_bg, daemon=True).start()

    def _on_bulk_message_done(self, results: list):
        """Show summary of bulk message results."""
        total = len(results)
        ok = sum(1 for _, success, _ in results if success)
        failed = total - ok

        summary = f"Mensaje enviado: {ok}/{total} exitosos"
        if failed:
            errors = [msg for _, success, msg in results if not success]
            summary += f"\n\nErrores ({failed}):\n" + "\n".join(errors[:10])

        dialog = ctk.CTkInputDialog(
            text=summary,
            title="Resultado del Mensaje Masivo",
        )
        dialog.get_input()

    def _refresh_now(self):
        """Cancel pending poll and refresh immediately."""
        if self._poll_job:
            self.after_cancel(self._poll_job)
            self._poll_job = None
        if self._debounce_job is not None:
            self.after_cancel(self._debounce_job)
            self._debounce_job = None
        self._pending_count = 0
        self._init_statuses()
        if not self.selected_host:
            self.dashboard.update_all(self.statuses)
        self._poll_once()

    # --- Cleanup ---

    def _on_close(self):
        self._polling = False
        if self._poll_job:
            self.after_cancel(self._poll_job)
        if self._debounce_job is not None:
            self.after_cancel(self._debounce_job)
        close_history()
        self.destroy()
