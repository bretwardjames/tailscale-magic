"""Manage Tailscale funnels for detected web apps."""
import json
import socket
import subprocess
from dataclasses import dataclass
from typing import Optional

from rich.console import Console

from . import validate_port

console = Console()


def is_port_bound_wildcard(port: int) -> bool:
    """Detect whether a process holds INADDR_ANY (0.0.0.0) on this port.

    A wildcard bind on the local machine occupies every IP at that port,
    including the tailscale-managed interface IPs. That collides with
    `tailscale serve --https=PORT` which needs to listen on the tailnet
    IP at PORT. We use this to pick a different external port when a
    conflict would happen.

    Returns True if a wildcard bind is detected, False otherwise (port
    free or only loopback bind, both safe for tailscale to use).
    """
    if not validate_port(port):
        return False  # Invalid port — caller's other validation will reject it
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 0)
        sock.bind(("0.0.0.0", port))
        return False  # Bind succeeded → no wildcard holder
    except OSError:
        # Bind failed — port is held by something. Loopback-only binds
        # don't actually conflict with tailscale (different IP), but
        # detecting that distinction reliably from userspace is tricky.
        # Conservatively assume any failure means "use a different
        # external port" — false-positives just bump the URL number,
        # they don't break anything.
        return True
    finally:
        sock.close()


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


def resolve_external_port(local_port: int, port_offset: int) -> int:
    """Pick the tailnet-side HTTPS port for a given local port.

    If the local port is held by a wildcard bind (0.0.0.0), tailscale
    can't share it on the tailnet IP — so we shift by `port_offset`
    (default 10000) to a guaranteed-free range. If the local port is
    free or only loopback-bound, we keep the same number for URL
    parity with the local app.

    Caller is the source of truth for the offset; the offset itself
    can be 0 to opt out of the shift entirely.
    """
    if port_offset == 0:
        return local_port
    if not is_port_bound_wildcard(local_port):
        return local_port
    candidate = local_port + port_offset
    if not validate_port(candidate):
        # Offset pushed past the valid range — fall back to local port
        # and let tailscale fail loudly so the user sees the real cause.
        return local_port
    return candidate


def setup_funnel(
    port: int,
    https_port: Optional[int] = None,
    background: bool = True,
    port_offset: int = 10000,
) -> int:
    """Set up a Tailscale funnel for a port.

    Args:
        port: Local port to expose
        https_port: Explicit external HTTPS port. When None, derived from
            `port` + `port_offset` if needed (see resolve_external_port).
        background: Run in background
        port_offset: How far to shift the tailnet port when the local
            port is wildcard-bound. 10000 by default. Pass 0 to disable.

    Returns the external HTTPS port that was actually configured (may
    differ from `port` when a conflict was avoided), or 0 on failure.
    """
    if not validate_port(port):
        console.print(f"[red]Invalid port number:[/red] {port}")
        return 0

    if https_port is None:
        https_port = resolve_external_port(port, port_offset)
    if not validate_port(https_port):
        console.print(f"[red]Invalid HTTPS port number:[/red] {https_port}")
        return 0

    try:
        cmd = ["tailscale", "funnel", f"--https={https_port}"]
        if background:
            cmd.append("--bg")
        cmd.append(str(port))

        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            console.print(f"[red]Error setting up funnel for port {port}:[/red] {result.stderr}")
            return 0
        return https_port
    except FileNotFoundError:
        console.print("[red]Tailscale not found. Is it installed?[/red]")
        return 0


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


def setup_serve(
    port: int,
    https_port: Optional[int] = None,
    background: bool = True,
    port_offset: int = 10000,
) -> int:
    """Set up Tailscale serve (tailnet only) for a port.

    Args + return: see setup_funnel — same shape.
    """
    if not validate_port(port):
        console.print(f"[red]Invalid port number:[/red] {port}")
        return 0

    if https_port is None:
        https_port = resolve_external_port(port, port_offset)
    if not validate_port(https_port):
        console.print(f"[red]Invalid HTTPS port number:[/red] {https_port}")
        return 0

    try:
        cmd = ["tailscale", "serve", f"--https={https_port}"]
        if background:
            cmd.append("--bg")
        cmd.append(str(port))

        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            console.print(f"[red]Error setting up serve for port {port}:[/red] {result.stderr}")
            return 0
        return https_port
    except FileNotFoundError:
        console.print("[red]Tailscale not found. Is it installed?[/red]")
        return 0


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
