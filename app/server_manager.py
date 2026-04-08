"""Server connection and monitoring via WinRM + PowerShell remoting."""

import winrm
from typing import Optional
from datetime import datetime

from app.models import ServerConfig, ServerStatus, ServerMetrics, UserSession
from app.utils.crypto import decrypt_password


# PowerShell script to get user sessions (quser-like info)
PS_GET_SESSIONS = r"""
try {
    $sessions = @()
    $quser = quser 2>&1
    if ($LASTEXITCODE -eq 0 -and $quser) {
        $lines = $quser | Select-Object -Skip 1
        foreach ($line in $lines) {
            $trimmed = $line.ToString().Trim()
            if ($trimmed -eq '') { continue }
            # Parse quser output - handles variable spacing
            if ($trimmed -match '^\s*(\S+)\s+(\d+)\s+(Disc)\s+(\S*)\s+(.+)$') {
                $sessions += @{
                    Username = $Matches[1]
                    SessionId = $Matches[2]
                    State = $Matches[3]
                    IdleTime = $Matches[4]
                    LogonTime = $Matches[5].Trim()
                    ClientName = ''
                }
            }
            elseif ($trimmed -match '^\s*(\S+)\s+(\S+)\s+(\d+)\s+(Active|Activo)\s+(\S*)\s+(.+)$') {
                $sessions += @{
                    Username = $Matches[1]
                    SessionId = $Matches[3]
                    State = $Matches[4]
                    IdleTime = $Matches[5]
                    LogonTime = $Matches[6].Trim()
                    ClientName = $Matches[2]
                }
            }
            elseif ($trimmed -match '^\s*>?\s*(\S+)\s+(\S+)\s+(\d+)\s+(\S+)\s+(\S*)\s+(.+)$') {
                $sessions += @{
                    Username = $Matches[1]
                    SessionId = $Matches[3]
                    State = $Matches[4]
                    IdleTime = $Matches[5]
                    LogonTime = $Matches[6].Trim()
                    ClientName = $Matches[2]
                }
            }
        }
    }
    $sessions | ForEach-Object { [PSCustomObject]$_ } | ConvertTo-Json -Compress
} catch {
    '[]'
}
"""

# PowerShell script to get server metrics
PS_GET_METRICS = r"""
try {
    $cpu = (Get-CimInstance Win32_Processor | Measure-Object -Property LoadPercentage -Average).Average
    $os = Get-CimInstance Win32_OperatingSystem
    $memTotal = [math]::Round($os.TotalVisibleMemorySize / 1MB, 2)
    $memFree = [math]::Round($os.FreePhysicalMemory / 1MB, 2)
    $memUsed = [math]::Round($memTotal - $memFree, 2)
    $memPercent = if ($memTotal -gt 0) { [math]::Round(($memUsed / $memTotal) * 100, 1) } else { 0 }

    $disk = Get-CimInstance Win32_LogicalDisk -Filter "DeviceID='C:'"
    $diskTotal = [math]::Round($disk.Size / 1GB, 2)
    $diskFree = [math]::Round($disk.FreeSpace / 1GB, 2)
    $diskUsed = [math]::Round($diskTotal - $diskFree, 2)
    $diskPercent = if ($diskTotal -gt 0) { [math]::Round(($diskUsed / $diskTotal) * 100, 1) } else { 0 }

    $uptime = (Get-Date) - $os.LastBootUpTime
    $uptimeHours = [math]::Round($uptime.TotalHours, 1)

    $procCount = (Get-Process).Count

    @{
        CpuPercent = $cpu
        MemoryTotalGB = $memTotal
        MemoryUsedGB = $memUsed
        MemoryPercent = $memPercent
        DiskTotalGB = $diskTotal
        DiskUsedGB = $diskUsed
        DiskPercent = $diskPercent
        UptimeHours = $uptimeHours
        TotalProcesses = $procCount
    } | ConvertTo-Json -Compress
} catch {
    '{}'
}
"""


def _create_session(server: ServerConfig) -> winrm.Session:
    """Create a WinRM session to the server."""
    password = decrypt_password(server.encrypted_password)
    protocol = "https" if server.use_ssl else "http"
    endpoint = f"{protocol}://{server.host}:{server.port}/wsman"

    session = winrm.Session(
        endpoint,
        auth=(server.username, password),
        transport="ntlm",
        server_cert_validation="ignore",
    )
    return session


def _parse_sessions(json_text: str) -> list:
    """Parse PowerShell JSON output into UserSession list."""
    import json
    try:
        raw = json_text.strip()
        if not raw or raw == "[]":
            return []
        data = json.loads(raw)
        # PowerShell returns single object (not array) when only 1 result
        if isinstance(data, dict):
            data = [data]
        sessions = []
        for item in data:
            sessions.append(UserSession(
                username=item.get("Username", ""),
                session_id=str(item.get("SessionId", "")),
                state=item.get("State", "Unknown"),
                idle_time=item.get("IdleTime", ""),
                logon_time=item.get("LogonTime", ""),
                client_name=item.get("ClientName", ""),
            ))
        return sessions
    except (json.JSONDecodeError, TypeError):
        return []


def _parse_metrics(json_text: str) -> Optional[ServerMetrics]:
    """Parse PowerShell JSON output into ServerMetrics."""
    import json
    try:
        raw = json_text.strip()
        if not raw or raw == "{}":
            return None
        data = json.loads(raw)
        return ServerMetrics(
            cpu_percent=float(data.get("CpuPercent", 0)),
            memory_total_gb=float(data.get("MemoryTotalGB", 0)),
            memory_used_gb=float(data.get("MemoryUsedGB", 0)),
            memory_percent=float(data.get("MemoryPercent", 0)),
            disk_total_gb=float(data.get("DiskTotalGB", 0)),
            disk_used_gb=float(data.get("DiskUsedGB", 0)),
            disk_percent=float(data.get("DiskPercent", 0)),
            uptime_hours=float(data.get("UptimeHours", 0)),
            total_processes=int(data.get("TotalProcesses", 0)),
        )
    except (json.JSONDecodeError, TypeError, ValueError):
        return None


def query_server(server: ServerConfig) -> ServerStatus:
    """Query a server for sessions and metrics. Returns full status."""
    status = ServerStatus(server=server)
    try:
        session = _create_session(server)

        # Get sessions
        result = session.run_ps(PS_GET_SESSIONS)
        if result.status_code == 0:
            status.sessions = _parse_sessions(result.std_out.decode("utf-8", errors="replace"))

        # Get metrics
        result = session.run_ps(PS_GET_METRICS)
        if result.status_code == 0:
            status.metrics = _parse_metrics(result.std_out.decode("utf-8", errors="replace"))

        status.is_online = True
        status.last_updated = datetime.now()

    except Exception as e:
        status.is_online = False
        status.error_message = str(e)
        status.last_updated = datetime.now()

    return status


def test_connection(server: ServerConfig) -> tuple:
    """Test connection to a server. Returns (success: bool, message: str)."""
    try:
        session = _create_session(server)
        result = session.run_ps("$env:COMPUTERNAME")
        if result.status_code == 0:
            name = result.std_out.decode("utf-8", errors="replace").strip()
            return True, f"Conectado exitosamente a {name}"
        else:
            err = result.std_err.decode("utf-8", errors="replace").strip()
            return False, f"Error: {err}"
    except Exception as e:
        return False, f"Error de conexión: {e}"


def logoff_user(server: ServerConfig, session_id: str) -> tuple[bool, str]:
    """Force logoff a specific user session on the server."""
    try:
        session = _create_session(server)
        # Using quser's logoff command which is typically `logoff <session_id>`
        result = session.run_ps(f"logoff {session_id}")
        if result.status_code == 0:
            return True, f"Sesión {session_id} cerrada exitosamente."
        else:
            err = result.std_err.decode("utf-8", errors="replace").strip()
            return False, f"Error al cerrar la sesión: {err}"
    except Exception as e:
        return False, f"Error de conexión al cerrar sesión: {e}"


def send_message(server: ServerConfig, message: str) -> tuple[bool, str]:
    """Send a popup message to ALL connected RDP sessions on the server."""
    try:
        session = _create_session(server)
        # Escape single quotes in the message for PowerShell
        safe_msg = message.replace("'", "''")
        result = session.run_ps(f"msg * '{safe_msg}'")
        if result.status_code == 0:
            return True, f"Mensaje enviado a usuarios en {server.display_name}."
        else:
            err = result.std_err.decode("utf-8", errors="replace").strip()
            # msg.exe returns error if no sessions exist, treat as partial success
            if "no existe" in err.lower() or "not exist" in err.lower():
                return True, f"No hay sesiones activas en {server.display_name}."
            return False, f"Error al enviar mensaje en {server.display_name}: {err}"
    except Exception as e:
        return False, f"Error de conexión a {server.display_name}: {e}"
