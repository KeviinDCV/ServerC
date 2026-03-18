"""Executive summary panel — aggregate KPIs, top-5 loaded servers, and alert ticker."""

import customtkinter as ctk
from typing import Dict, List
from app.models import ServerStatus
from app.ui.styles import COLORS, FONTS


class SummaryPanel(ctk.CTkFrame):
    """Top-of-dashboard panel with KPI gauges, top-5 list, and alert ticker."""

    def __init__(self, parent):
        super().__init__(parent, fg_color=COLORS["bg_medium"], corner_radius=14)
        self._build_ui()

    def _build_ui(self):
        # ── Row 1: KPI gauges ──
        self._kpi_row = ctk.CTkFrame(self, fg_color="transparent")
        self._kpi_row.pack(fill="x", padx=16, pady=(14, 4))

        self._gauges: Dict[str, dict] = {}
        gauge_defs = [
            ("servers", "Servidores", "📊", COLORS["accent"]),
            ("online", "En línea", "✅", COLORS["success"]),
            ("offline", "Sin conexión", "❌", COLORS["critical"]),
            ("sessions", "Sesiones", "👥", COLORS["accent"]),
            ("cpu", "CPU Prom.", "⚡", COLORS["warning"]),
            ("ram", "RAM Prom.", "🧠", COLORS["warning"]),
            ("disk", "Disco Prom.", "💾", COLORS["warning"]),
        ]
        for key, label, icon, color in gauge_defs:
            g = self._make_gauge(self._kpi_row, icon, "0", label, color)
            g["frame"].pack(side="left", fill="x", expand=True, padx=2)
            self._gauges[key] = g

        # ── Row 2: Top-5 loaded + recent alerts ──
        self._bottom_row = ctk.CTkFrame(self, fg_color="transparent")
        self._bottom_row.pack(fill="x", padx=16, pady=(4, 12))

        # Top-5 servers
        top5_frame = ctk.CTkFrame(self._bottom_row, fg_color=COLORS["bg_dark"],
                                   corner_radius=10)
        top5_frame.pack(side="left", fill="both", expand=True, padx=(0, 6))

        ctk.CTkLabel(top5_frame, text="🔥 Top 5 servidores más cargados",
                      font=FONTS["small_bold"],
                      text_color=COLORS["text_secondary"]).pack(anchor="w", padx=10, pady=(6, 2))

        self._top5_labels: List[ctk.CTkLabel] = []
        for i in range(5):
            lbl = ctk.CTkLabel(top5_frame, text="", font=FONTS["small"],
                                text_color=COLORS["text_muted"], anchor="w")
            lbl.pack(fill="x", padx=10, pady=1)
            self._top5_labels.append(lbl)

        # Recent alerts
        alert_frame = ctk.CTkFrame(self._bottom_row, fg_color=COLORS["bg_dark"],
                                    corner_radius=10)
        alert_frame.pack(side="left", fill="both", expand=True, padx=(6, 0))

        ctk.CTkLabel(alert_frame, text="🔔 Alertas recientes",
                      font=FONTS["small_bold"],
                      text_color=COLORS["text_secondary"]).pack(anchor="w", padx=10, pady=(6, 2))

        self._alert_labels: List[ctk.CTkLabel] = []
        for i in range(5):
            lbl = ctk.CTkLabel(alert_frame, text="Sin alertas", font=FONTS["small"],
                                text_color=COLORS["text_muted"], anchor="w")
            lbl.pack(fill="x", padx=10, pady=1)
            self._alert_labels.append(lbl)

    def _make_gauge(self, parent, icon: str, value: str, label: str,
                    color: str) -> dict:
        frame = ctk.CTkFrame(parent, fg_color=COLORS["bg_dark"], corner_radius=10,
                              height=72)
        frame.pack_propagate(False)

        top = ctk.CTkFrame(frame, fg_color="transparent")
        top.pack(fill="x", padx=10, pady=(8, 0))

        ctk.CTkLabel(top, text=icon, font=("Segoe UI", 14)).pack(side="left")
        val_lbl = ctk.CTkLabel(top, text=value, font=("Segoe UI", 22, "bold"),
                                text_color=color)
        val_lbl.pack(side="right")

        lbl = ctk.CTkLabel(frame, text=label, font=FONTS["small"],
                            text_color=COLORS["text_muted"])
        lbl.pack(anchor="w", padx=10, pady=(0, 6))

        return {"frame": frame, "value": val_lbl, "label": lbl, "color": color}

    # ── Public API ──

    def update(self, statuses: Dict[str, ServerStatus],
               alerts: List[Dict] = None):
        """Refresh all KPIs from current statuses dict."""
        total = len(statuses)
        online = sum(1 for s in statuses.values() if s.is_online)
        offline = total - online
        sessions = sum(s.total_sessions for s in statuses.values() if s.is_online)

        online_with_metrics = [s for s in statuses.values()
                                if s.is_online and s.metrics]
        n = len(online_with_metrics) or 1
        avg_cpu = sum(s.metrics.cpu_percent for s in online_with_metrics) / n
        avg_ram = sum(s.metrics.memory_percent for s in online_with_metrics) / n
        avg_disk = sum(s.metrics.disk_percent for s in online_with_metrics) / n

        self._gauges["servers"]["value"].configure(text=str(total))
        self._gauges["online"]["value"].configure(text=str(online))
        self._gauges["offline"]["value"].configure(text=str(offline))
        self._gauges["sessions"]["value"].configure(text=str(sessions))
        self._gauges["cpu"]["value"].configure(text=f"{avg_cpu:.0f}%")
        self._gauges["ram"]["value"].configure(text=f"{avg_ram:.0f}%")
        self._gauges["disk"]["value"].configure(text=f"{avg_disk:.0f}%")

        # Color code averages
        for key, val in [("cpu", avg_cpu), ("ram", avg_ram), ("disk", avg_disk)]:
            if val >= 90:
                c = COLORS["critical"]
            elif val >= 75:
                c = COLORS["warning"]
            else:
                c = COLORS["success"]
            self._gauges[key]["value"].configure(text_color=c)

        # Top-5 by CPU
        ranked = sorted(online_with_metrics,
                        key=lambda s: s.metrics.cpu_percent, reverse=True)[:5]
        for i, lbl in enumerate(self._top5_labels):
            if i < len(ranked):
                s = ranked[i]
                m = s.metrics
                color = COLORS["critical"] if m.cpu_percent >= 90 else (
                    COLORS["warning"] if m.cpu_percent >= 75 else COLORS["text_secondary"])
                lbl.configure(
                    text=f"{i+1}. {s.server.display_name}  —  "
                         f"CPU {m.cpu_percent:.0f}%  RAM {m.memory_percent:.0f}%  "
                         f"👥 {s.total_sessions}",
                    text_color=color,
                )
            else:
                lbl.configure(text="", text_color=COLORS["text_muted"])

        # Alerts
        if alerts:
            recent = alerts[-5:]
            recent.reverse()  # newest first
            for i, lbl in enumerate(self._alert_labels):
                if i < len(recent):
                    a = recent[i]
                    col = {"critical": COLORS["critical"],
                           "warning": COLORS["warning"],
                           "success": COLORS["success"]}.get(a["level"], COLORS["text_muted"])
                    time_str = a["time"].split(" ")[1] if " " in a["time"] else a["time"]
                    lbl.configure(text=f"[{time_str}] {a['message']}", text_color=col)
                else:
                    lbl.configure(text="", text_color=COLORS["text_muted"])
