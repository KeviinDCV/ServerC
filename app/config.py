"""Configuration management — load/save server list from JSON."""

import json
import os
from pathlib import Path
from typing import List

from app.models import ServerConfig


def _get_config_path() -> Path:
    """Config file stored in user's AppData/Roaming/ServerC."""
    app_data = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    config_dir = app_data / "ServerC"
    config_dir.mkdir(parents=True, exist_ok=True)
    return config_dir / "servers.json"


def load_servers() -> List[ServerConfig]:
    """Load server configurations from disk."""
    path = _get_config_path()
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return [
            ServerConfig(
                name=s.get("name", ""),
                host=s["host"],
                username=s["username"],
                encrypted_password=s["encrypted_password"],
                port=s.get("port", 5985),
                use_ssl=s.get("use_ssl", False),
                max_users_warning=s.get("max_users_warning", 10),
                max_users_critical=s.get("max_users_critical", 15),
            )
            for s in data.get("servers", [])
        ]
    except (json.JSONDecodeError, KeyError):
        return []


def save_servers(servers: List[ServerConfig]) -> None:
    """Save server configurations to disk."""
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
