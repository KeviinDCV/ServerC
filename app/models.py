"""Data models for ServerC monitoring application."""

from dataclasses import dataclass, field
from typing import Optional
from datetime import datetime


@dataclass
class ServerConfig:
    """Configuration for a monitored server."""
    name: str
    host: str
    username: str
    encrypted_password: str
    port: int = 5985
    use_ssl: bool = False
    max_users_warning: int = 10
    max_users_critical: int = 15

    @property
    def display_name(self) -> str:
        return self.name or self.host


@dataclass
class UserSession:
    """Represents a user session on a server."""
    username: str
    session_id: str
    state: str  # Active, Disconnected, etc.
    idle_time: str
    logon_time: str
    client_name: str = ""
    client_ip: str = ""


@dataclass
class ServerMetrics:
    """Server performance metrics."""
    cpu_percent: float = 0.0
    memory_total_gb: float = 0.0
    memory_used_gb: float = 0.0
    memory_percent: float = 0.0
    disk_total_gb: float = 0.0
    disk_used_gb: float = 0.0
    disk_percent: float = 0.0
    uptime_hours: float = 0.0
    total_processes: int = 0


@dataclass
class ServerStatus:
    """Complete status snapshot of a server."""
    server: ServerConfig
    is_online: bool = False
    error_message: str = ""
    sessions: list = field(default_factory=list)
    metrics: Optional[ServerMetrics] = None
    last_updated: Optional[datetime] = None

    @property
    def active_users(self) -> int:
        return len([s for s in self.sessions if s.state.lower() == "active"])

    @property
    def total_sessions(self) -> int:
        return len(self.sessions)

    @property
    def load_level(self) -> str:
        """Returns 'normal', 'warning', or 'critical' based on user count."""
        count = self.total_sessions
        if count >= self.server.max_users_critical:
            return "critical"
        elif count >= self.server.max_users_warning:
            return "warning"
        return "normal"
