"""Manage Tailscale funnels for detected web apps."""
import json
import subprocess
from dataclasses import dataclass
from typing import Optional

from rich.console import Console

console = Console()


def validate_port(port: int) -> bool:
    """Validate port is in valid range."""
    return isinstance(port, int) and 1 <= port <= 65535


@dataclass
class FunnelConfig:
    """Configuration for a Tailscale funnel."""
    port: int
    path: str = "/"
    https: bool = True


def get_tailscale_domain() -> Optional[str]:
    """Get the Tailscale funnel domain for this machine."""
    try:
        result = subprocess.run(
            ["tailscale", "status", "--json"],
            capture_output=True,
            text=True,
            check=True,
        )
        status = json.loads(result.stdout)
        # Get the DNS name for this machine
        self_info = status.get("Self", {})
        dns_name = self_info.get("DNSName", "")
        if dns_name:
            # Remove trailing dot if present
            return dns_name.rstrip(".")
        return None
    except (subprocess.CalledProcessError, json.JSONDecodeError, KeyError):
        return None


def get_current_funnels() -> dict:
    """Get currently configured funnels."""
    try:
        result = subprocess.run(
            ["tailscale", "serve", "status", "--json"],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0 and result.stdout.strip():
            return json.loads(result.stdout)
        return {}
    except (subprocess.CalledProcessError, json.JSONDecodeError):
        return {}


def setup_funnel(port: int, https_port: int = None, background: bool = True) -> bool:
    """Set up a Tailscale funnel for a port.

    Args:
        port: Local port to expose
        https_port: External HTTPS port (defaults to same as local port)
        background: Run in background
    """
    if not validate_port(port):
        console.print(f"[red]Invalid port number:[/red] {port}")
        return False

    https_port = https_port or port
    if not validate_port(https_port):
        console.print(f"[red]Invalid HTTPS port number:[/red] {https_port}")
        return False

    try:
        cmd = ["tailscale", "funnel", f"--https={https_port}"]
        if background:
            cmd.append("--bg")
        cmd.append(str(port))

        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            console.print(f"[red]Error setting up funnel for port {port}:[/red] {result.stderr}")
            return False
        return True
    except FileNotFoundError:
        console.print("[red]Tailscale not found. Is it installed?[/red]")
        return False


def remove_funnel(port: int) -> bool:
    """Remove a Tailscale funnel for a port."""
    if not validate_port(port):
        return False

    try:
        result = subprocess.run(
            ["tailscale", "funnel", "--remove", str(port)],
            capture_output=True,
            text=True,
        )
        return result.returncode == 0
    except FileNotFoundError:
        return False


def setup_serve(port: int, https_port: int = 443, path: str = "/") -> bool:
    """Set up Tailscale serve (local proxy) for a port."""
    if not validate_port(port) or not validate_port(https_port):
        console.print(f"[red]Invalid port number[/red]")
        return False

    try:
        # tailscale serve https:<https_port> / http://127.0.0.1:<port>
        target = f"http://127.0.0.1:{port}"
        cmd = ["tailscale", "serve", f"https:{https_port}", path, target]

        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            console.print(f"[red]Error setting up serve for port {port}:[/red] {result.stderr}")
            return False
        return True
    except FileNotFoundError:
        console.print("[red]Tailscale not found. Is it installed?[/red]")
        return False


def reset_serve() -> bool:
    """Reset all serve/funnel configurations."""
    try:
        result = subprocess.run(
            ["tailscale", "serve", "reset"],
            capture_output=True,
            text=True,
        )
        return result.returncode == 0
    except FileNotFoundError:
        return False


def check_tailscale_running() -> bool:
    """Check if Tailscale is running and connected."""
    try:
        result = subprocess.run(
            ["tailscale", "status"],
            capture_output=True,
            text=True,
        )
        return result.returncode == 0 and "Tailscale is stopped" not in result.stdout
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False
