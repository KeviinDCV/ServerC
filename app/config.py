"""Configuration management — load/save server list from JSON with automatic backups."""

import json
import os
import shutil
from datetime import datetime
from pathlib import Path
from typing import List

from app.models import ServerConfig

MAX_BACKUPS = 10


def _get_config_dir() -> Path:
    app_data = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    config_dir = app_data / "ServerC"
    config_dir.mkdir(parents=True, exist_ok=True)
    return config_dir


def _get_config_path() -> Path:
    return _get_config_dir() / "servers.json"


def _backup_config() -> None:
    """Create a timestamped backup of servers.json before any write."""
    src = _get_config_path()
    if not src.exists():
        return
    try:
        content = src.read_text(encoding="utf-8")
        data = json.loads(content)
        if not data.get("servers"):
            return  # don't backup empty files
    except Exception:
        return

    backup_dir = _get_config_dir() / "backups"
    backup_dir.mkdir(exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    shutil.copy2(src, backup_dir / f"servers_{stamp}.json")

    # Keep only the last MAX_BACKUPS
    backups = sorted(backup_dir.glob("servers_*.json"))
    for old in backups[:-MAX_BACKUPS]:
        old.unlink(missing_ok=True)


def _restore_latest_backup() -> List[ServerConfig]:
    """Try to restore from the most recent backup."""
    backup_dir = _get_config_dir() / "backups"
    if not backup_dir.exists():
        return []
    backups = sorted(backup_dir.glob("servers_*.json"))
    for backup in reversed(backups):
        try:
            data = json.loads(backup.read_text(encoding="utf-8"))
            servers = _parse_server_list(data.get("servers", []))
            if servers:
                # Restore — copy backup to main file
                shutil.copy2(backup, _get_config_path())
                return servers
        except Exception:
            continue
    return []


def _parse_server_list(raw_list: list) -> List[ServerConfig]:
    """Parse server entries individually so one bad entry doesn't kill the rest."""
    servers = []
    for s in raw_list:
        try:
            servers.append(ServerConfig(
                name=s.get("name", ""),
                host=s["host"],
                username=s["username"],
                encrypted_password=s["encrypted_password"],
                port=s.get("port", 5985),
                use_ssl=s.get("use_ssl", False),
                max_users_warning=s.get("max_users_warning", 10),
                max_users_critical=s.get("max_users_critical", 15),
            ))
        except (KeyError, TypeError):
            continue  # skip malformed entry, don't lose the rest
    return servers


def load_servers() -> List[ServerConfig]:
    """Load server configurations from disk. Falls back to backup if main file fails."""
    path = _get_config_path()
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        servers = _parse_server_list(data.get("servers", []))
        if servers:
            return servers
        # Main file is empty or all entries bad — try backups
        return _restore_latest_backup()
    except json.JSONDecodeError:
        return _restore_latest_backup()


def save_servers(servers: List[ServerConfig]) -> None:
    """Save server configurations to disk with automatic backup."""
    _backup_config()
    path = _get_config_path()
    data = {
        "servers": [
            {
                "name": s.name,
                "host": s.host,
                "username": s.username,
                "encrypted_password": s.encrypted_password,
                "port": s.port,
                "use_ssl": s.use_ssl,
                "max_users_warning": s.max_users_warning,
                "max_users_critical": s.max_users_critical,
            }
            for s in servers
        ]
    }
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def add_server(server: ServerConfig) -> List[ServerConfig]:
    """Add a server and save."""
    servers = load_servers()
    servers.append(server)
    save_servers(servers)
    return servers


def remove_server(host: str) -> List[ServerConfig]:
    """Remove a server by host and save."""
    servers = [s for s in load_servers() if s.host != host]
    save_servers(servers)
    return servers


def update_server(old_host: str, updated: ServerConfig) -> List[ServerConfig]:
    """Update a server config and save."""
    servers = load_servers()
    for i, s in enumerate(servers):
        if s.host == old_host:
            servers[i] = updated
            break
    save_servers(servers)
    return servers
