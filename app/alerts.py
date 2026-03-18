"""Alert system — detects state transitions and notifies via Windows toast & log.

Alerts are triggered when:
- A server goes offline (was online, now offline).
- CPU, RAM or Disk exceeds 90%.
- User count exceeds the critical threshold.

Each alert is logged to ``%APPDATA%\\ServerC\\alerts.log`` and optionally shown as
a Windows 10/11 toast notification.
"""

import os
import threading
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from app.models import ServerStatus

_ALERT_THRESHOLD_CPU = 90.0
_ALERT_THRESHOLD_RAM = 90.0
_ALERT_THRESHOLD_DISK = 95.0

# Cooldown: same alert for same host won't fire again within this many seconds
_COOLDOWN_SECONDS = 300  # 5 minutes


def _get_log_path() -> Path:
    d = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming")) / "ServerC"
    d.mkdir(parents=True, exist_ok=True)
    return d / "alerts.log"


class AlertManager:
    """Stateful alert manager — call :meth:`check` after every poll cycle."""

    def __init__(self):
        self._prev_online: Dict[str, bool] = {}
        self._cooldowns: Dict[str, float] = {}  # "host|type" → timestamp
        self._log_path = _get_log_path()
        self._lock = threading.Lock()
        self._toast_available = self._check_toast()
        self.alerts_log: List[Dict] = []  # in-memory recent alerts for UI

    @staticmethod
    def _check_toast() -> bool:
        try:
            from win10toast import ToastNotifier
            return True
        except ImportError:
            return False

    def check(self, statuses: Dict[str, ServerStatus]) -> List[Dict]:
        """Evaluate all servers, emit alerts, return list of new alerts."""
        now = datetime.now()
        ts = now.timestamp()
        new_alerts: List[Dict] = []

        for host, st in statuses.items():
            was_online = self._prev_online.get(host)

            # --- Server went offline ---
            if was_online is True and not st.is_online:
                self._emit(new_alerts, ts, host, "offline",
                           f"{st.server.display_name} se desconectó",
                           "critical")

            if st.is_online and st.metrics:
                m = st.metrics
                name = st.server.display_name

                if m.cpu_percent >= _ALERT_THRESHOLD_CPU:
                    self._emit(new_alerts, ts, host, "cpu",
                               f"{name}: CPU al {m.cpu_percent:.0f}%", "warning")

                if m.memory_percent >= _ALERT_THRESHOLD_RAM:
                    self._emit(new_alerts, ts, host, "ram",
                               f"{name}: RAM al {m.memory_percent:.0f}%", "warning")

                if m.disk_percent >= _ALERT_THRESHOLD_DISK:
                    self._emit(new_alerts, ts, host, "disk",
                               f"{name}: Disco al {m.disk_percent:.0f}%", "warning")

                if st.load_level == "critical":
                    self._emit(new_alerts, ts, host, "users",
                               f"{name}: {st.total_sessions} usuarios (crítico)",
                               "critical")

            # --- Server came back online ---
            if was_online is False and st.is_online:
                self._emit(new_alerts, ts, host, "online",
                           f"{st.server.display_name} volvió a conectarse",
                           "success")

            self._prev_online[host] = st.is_online

        # Trim in-memory log to last 200
        with self._lock:
            self.alerts_log.extend(new_alerts)
            if len(self.alerts_log) > 200:
                self.alerts_log = self.alerts_log[-200:]

        return new_alerts

    def _emit(self, bucket: list, ts: float, host: str, kind: str,
              message: str, level: str):
        key = f"{host}|{kind}"
        if ts - self._cooldowns.get(key, 0) < _COOLDOWN_SECONDS:
            return
        self._cooldowns[key] = ts

        alert = {
            "time": datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S"),
            "host": host,
            "kind": kind,
            "message": message,
            "level": level,
        }
        bucket.append(alert)
        self._write_log(alert)
        if self._toast_available and level in ("critical", "warning"):
            self._show_toast(message, level)

    def _write_log(self, alert: dict):
        try:
            with open(self._log_path, "a", encoding="utf-8") as f:
                f.write(f"[{alert['time']}] [{alert['level'].upper()}] {alert['message']}\n")
        except OSError:
            pass

    def _show_toast(self, message: str, level: str):
        """Fire-and-forget Windows toast notification."""
        def _toast():
            try:
                from win10toast import ToastNotifier
                t = ToastNotifier()
                icon_path = None  # could set .ico path here
                t.show_toast(
                    "ServerC Monitor",
                    message,
                    icon_path=icon_path,
                    duration=5,
                    threaded=False,
                )
            except Exception:
                pass
        threading.Thread(target=_toast, daemon=True).start()

    def get_recent(self, count: int = 50) -> List[Dict]:
        with self._lock:
            return list(self.alerts_log[-count:])
