"""CLI interface for ts-funnel."""
import subprocess
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from . import __version__
from .allowlist import update_cors_config
from .funnel import (
    check_tailscale_running,
    get_current_funnels,
    get_tailscale_domain,
    reset_serve,
    setup_funnel,
    setup_serve,
)
from .scanner import WebApp, scan_directory

# Mode enum for funnel vs serve
class Mode:
    FUNNEL = "funnel"  # Public internet
    SERVE = "serve"    # Tailnet only

app = typer.Typer(
    name="ts-funnel",
    help="Auto-discover and funnel local dev servers through Tailscale",
    no_args_is_help=True,
)
console = Console()


def get_default_projects_dir() -> Path:
    """Get the default projects directory."""
    # Check common locations
    home = Path.home()
    for candidate in ["IdeaProjects", "Projects", "projects", "code", "Code", "dev", "src"]:
        path = home / candidate
        if path.exists():
            return path
    return Path.cwd()


@app.command()
def scan(
    path: Optional[Path] = typer.Argument(None, help="Directory to scan (default: auto-detect)"),
    max_depth: int = typer.Option(2, "--depth", "-d", help="Maximum depth to scan"),
):
    """Scan for web app projects and show their configurations."""
    scan_path = path or get_default_projects_dir()

    if not scan_path.exists():
        console.print(f"[red]Directory not found:[/red] {scan_path}")
        raise typer.Exit(1)

    console.print(f"[bold]Scanning:[/bold] {scan_path}")
    apps = scan_directory(scan_path, max_depth)

    if not apps:
        console.print("[yellow]No web apps found.[/yellow]")
        return

    table = Table(title="Detected Web Apps")
    table.add_column("Name", style="cyan")
    table.add_column("Type", style="green")
    table.add_column("Framework", style="yellow")
    table.add_column("Port", style="magenta")
    table.add_column("CORS Config", style="dim")

    for app in apps:
        cors_status = "Yes" if app.cors_config_path else "No"
        table.add_row(
            app.name,
            app.app_type,
            app.framework,
            str(app.port),
            cors_status,
        )

    console.print(table)


@app.command()
def up(
    path: Optional[Path] = typer.Argument(None, help="Directory to scan (default: auto-detect)"),
    port: Optional[int] = typer.Option(None, "--port", "-p", help="Specific port to expose"),
    mode: str = typer.Option(Mode.FUNNEL, "--mode", "-m", help="funnel (public) or serve (tailnet only)"),
    update_cors: bool = typer.Option(True, "--cors/--no-cors", help="Update CORS configs"),
    dry_run: bool = typer.Option(False, "--dry-run", "-n", help="Show what would be done"),
):
    """Set up Tailscale funnels/serves for detected web apps."""
    if not check_tailscale_running():
        console.print("[red]Tailscale is not running. Please start it first.[/red]")
        raise typer.Exit(1)

    domain = get_tailscale_domain()
    if not domain:
        console.print("[red]Could not determine Tailscale domain.[/red]")
        raise typer.Exit(1)

    console.print(f"[bold]Tailscale domain:[/bold] {domain}")

    scan_path = path or get_default_projects_dir()
    apps = scan_directory(scan_path)

    if not apps:
        console.print("[yellow]No web apps found.[/yellow]")
        return

    # Filter by port if specified
    if port:
        apps = [a for a in apps if a.port == port]
        if not apps:
            console.print(f"[yellow]No apps found on port {port}.[/yellow]")
            return

    # Validate mode
    if mode not in (Mode.FUNNEL, Mode.SERVE):
        console.print(f"[red]Invalid mode:[/red] {mode}. Use 'funnel' or 'serve'.")
        raise typer.Exit(1)

    # Get unique ports
    ports = sorted(set(a.port for a in apps))

    mode_label = "funnels" if mode == Mode.FUNNEL else "serves"
    mode_desc = "(public)" if mode == Mode.FUNNEL else "(tailnet only)"
    console.print(f"\n[bold]Setting up {mode_label} {mode_desc} for ports:[/bold] {', '.join(map(str, ports))}")

    setup_fn = setup_funnel if mode == Mode.FUNNEL else setup_serve
    for p in ports:
        if dry_run:
            console.print(f"  [dim]Would {mode} port {p}[/dim]")
        else:
            if setup_fn(p):
                console.print(f"  [green]✓[/green] {mode.capitalize()} set up for port {p}")
            else:
                console.print(f"  [red]✗[/red] Failed to set up {mode} for port {p}")

    if update_cors:
        console.print(f"\n[bold]Updating CORS configs for domain:[/bold] {domain}")
        for app in apps:
            if app.cors_config_path:
                if dry_run:
                    console.print(f"  [dim]Would update {app.cors_config_path}[/dim]")
                else:
                    update_cors_config(app.cors_config_path, app.framework, domain, app.path)

    console.print(f"\n[bold green]Done![/bold green] Your apps are accessible at:")
    for p in ports:
        console.print(f"  https://{domain}:{p}/")


@app.command()
def down(
    all_funnels: bool = typer.Option(False, "--all", "-a", help="Remove all funnels"),
):
    """Remove Tailscale funnels."""
    if all_funnels:
        if reset_serve():
            console.print("[green]All funnels removed.[/green]")
        else:
            console.print("[red]Failed to remove funnels.[/red]")
    else:
        console.print("Use --all to remove all funnels, or specify ports manually.")


@app.command()
def status():
    """Show current Tailscale funnel status."""
    if not check_tailscale_running():
        console.print("[red]Tailscale is not running.[/red]")
        raise typer.Exit(1)

    domain = get_tailscale_domain()
    console.print(f"[bold]Tailscale domain:[/bold] {domain or 'unknown'}")

    # Show funnel status
    try:
        result = subprocess.run(
            ["tailscale", "funnel", "status"],
            capture_output=True,
            text=True,
        )
        if result.stdout.strip():
            console.print("\n[bold]Current funnels:[/bold]")
            console.print(result.stdout)
        else:
            console.print("\n[dim]No funnels currently configured.[/dim]")
    except FileNotFoundError:
        console.print("[red]Tailscale not found. Is it installed?[/red]")
        raise typer.Exit(1)


@app.command()
def version():
    """Show version information."""
    console.print(f"ts-funnel {__version__}")


if __name__ == "__main__":
    app()
