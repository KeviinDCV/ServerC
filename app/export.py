"""Export server status to CSV file.

Generates a snapshot report of all servers with their current metrics.
"""

import csv
import os
from datetime import datetime
from pathlib import Path
from typing import Dict
from tkinter import filedialog

from app.models import ServerStatus


def export_csv(statuses: Dict[str, ServerStatus], parent_window=None) -> str:
    """Open a Save-As dialog and write current server data as CSV.

    Returns the path written, or empty string if cancelled.
    """
    default_name = f"ServerC_Report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    desktop = Path.home() / "Desktop"

    path = filedialog.asksaveasfilename(
        parent=parent_window,
        title="Exportar Reporte CSV",
        defaultextension=".csv",
        initialfile=default_name,
        initialdir=str(desktop) if desktop.exists() else None,
        filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
    )
    if not path:
        return ""

    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)

        # Summary header
        online = sum(1 for s in statuses.values() if s.is_online)
        total = len(statuses)
        sessions = sum(s.total_sessions for s in statuses.values() if s.is_online)
        writer.writerow([f"ServerC Monitor — Reporte {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"])
        writer.writerow([f"Total: {total}", f"En línea: {online}",
                         f"Sin conexión: {total - online}", f"Sesiones: {sessions}"])
        writer.writerow([])

        # Column headers
        writer.writerow([
            "Servidor", "IP / Host", "Estado", "CPU %", "RAM %",
            "RAM Usada (GB)", "RAM Total (GB)", "Disco %",
            "Disco Usado (GB)", "Disco Total (GB)",
            "Sesiones", "Activas", "Procesos", "Uptime (h)",
            "Nivel Carga", "Última Actualización",
        ])

        for host, st in statuses.items():
            m = st.metrics
            writer.writerow([
                st.server.display_name,
                host,
                "Online" if st.is_online else "Offline",
                f"{m.cpu_percent:.1f}" if m else "",
                f"{m.memory_percent:.1f}" if m else "",
                f"{m.memory_used_gb:.1f}" if m else "",
                f"{m.memory_total_gb:.1f}" if m else "",
                f"{m.disk_percent:.1f}" if m else "",
                f"{m.disk_used_gb:.1f}" if m else "",
                f"{m.disk_total_gb:.1f}" if m else "",
                st.total_sessions if st.is_online else "",
                st.active_users if st.is_online else "",
                m.total_processes if m else "",
                f"{m.uptime_hours:.1f}" if m else "",
                st.load_level if st.is_online else "offline",
                st.last_updated.strftime("%H:%M:%S") if st.last_updated else "",
            ])

    return path
