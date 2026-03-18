"""Lightweight SQLite-based history for server metrics.

Stores a snapshot per server every poll cycle (~30s).  Data is kept for 24 hours
by default to avoid unbounded growth.  All public functions are thread-safe.
"""

import sqlite3
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Tuple, Optional

from app.models import ServerStatus

_RETENTION_HOURS = 24
_DB_NAME = "history.db"

_lock = threading.Lock()
_conn: Optional[sqlite3.Connection] = None


def _get_db_path() -> Path:
    import os
    app_data = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    d = app_data / "ServerC"
    d.mkdir(parents=True, exist_ok=True)
    return d / _DB_NAME


def _get_conn() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        _conn = sqlite3.connect(str(_get_db_path()), check_same_thread=False)
        _conn.execute("PRAGMA journal_mode=WAL")
        _conn.execute("""
            CREATE TABLE IF NOT EXISTS snapshots (
                id       INTEGER PRIMARY KEY AUTOINCREMENT,
                host     TEXT    NOT NULL,
                ts       REAL    NOT NULL,
                cpu      REAL,
                ram      REAL,
                disk     REAL,
                sessions INTEGER,
                online   INTEGER
            )
        """)
        _conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_host_ts ON snapshots(host, ts)
        """)
        _conn.commit()
    return _conn


def record_statuses(statuses: Dict[str, ServerStatus]) -> None:
    """Persist current metrics for all servers.  Called once per poll cycle."""
    now = time.time()
    rows = []
    for host, st in statuses.items():
        m = st.metrics
        rows.append((
            host,
            now,
            m.cpu_percent if m else None,
            m.memory_percent if m else None,
            m.disk_percent if m else None,
            st.total_sessions if st.is_online else None,
            1 if st.is_online else 0,
        ))
    with _lock:
        conn = _get_conn()
        conn.executemany(
            "INSERT INTO snapshots (host, ts, cpu, ram, disk, sessions, online) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            rows,
        )
        conn.commit()


def purge_old(hours: int = _RETENTION_HOURS) -> None:
    """Delete records older than *hours*."""
    cutoff = time.time() - hours * 3600
    with _lock:
        conn = _get_conn()
        conn.execute("DELETE FROM snapshots WHERE ts < ?", (cutoff,))
        conn.commit()


def get_series(host: str, metric: str = "cpu",
               minutes: int = 60) -> List[Tuple[float, Optional[float]]]:
    """Return [(timestamp, value), ...] for *host* over the last *minutes*.

    *metric* can be ``'cpu'``, ``'ram'``, ``'disk'``, or ``'sessions'``.
    """
    col = {"cpu": "cpu", "ram": "ram", "disk": "disk", "sessions": "sessions"}.get(metric, "cpu")
    since = time.time() - minutes * 60
    with _lock:
        conn = _get_conn()
        rows = conn.execute(
            f"SELECT ts, {col} FROM snapshots WHERE host = ? AND ts >= ? ORDER BY ts",
            (host, since),
        ).fetchall()
    return rows


def get_latest_averages(minutes: int = 5) -> Dict[str, Dict[str, float]]:
    """Return {host: {cpu, ram, disk, sessions}} averaged over the last *minutes*.

    Only includes hosts that have data.
    """
    since = time.time() - minutes * 60
    with _lock:
        conn = _get_conn()
        rows = conn.execute(
            "SELECT host, AVG(cpu), AVG(ram), AVG(disk), AVG(sessions) "
            "FROM snapshots WHERE ts >= ? AND online = 1 GROUP BY host",
            (since,),
        ).fetchall()
    return {
        r[0]: {"cpu": r[1] or 0, "ram": r[2] or 0, "disk": r[3] or 0, "sessions": r[4] or 0}
        for r in rows
    }


def close() -> None:
    global _conn
    with _lock:
        if _conn:
            _conn.close()
            _conn = None
