"""CLI interface for ts-funnel."""
import subprocess
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from . import __version__
from .allowlist import update_cors_config, update_port_in_env
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
    name="ts-magic",
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

    # Check for conflicts
    conflicts = [a for a in apps if a.suggested_port is not None]

    table = Table(title="Detected Web Apps")
    table.add_column("Name", style="cyan")
    table.add_column("Type", style="green")
    table.add_column("Framework", style="yellow")
    table.add_column("Port", style="magenta")
    table.add_column("Suggested", style="yellow")
    table.add_column("CORS Config", style="dim")

    for app in apps:
        cors_status = "Yes" if app.cors_config_path else "No"
        port_str = str(app.port)
        suggested_str = ""
        if app.suggested_port:
            port_str = f"[red]{app.port}[/red]"
            suggested_str = f"[green]{app.suggested_port}[/green]"

        table.add_row(
            app.name,
            app.app_type,
            app.framework,
            port_str,
            suggested_str,
            cors_status,
        )

    console.print(table)

    if conflicts:
        console.print(f"\n[yellow]⚠ {len(conflicts)} port conflict(s) detected.[/yellow]")
        console.print("Run [bold]ts-funnel fix-conflicts[/bold] to update .env files with suggested ports.")


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


@app.command("fix-conflicts")
def fix_conflicts(
    path: Optional[Path] = typer.Argument(None, help="Directory to scan (default: auto-detect)"),
    max_depth: int = typer.Option(2, "--depth", "-d", help="Maximum depth to scan"),
    dry_run: bool = typer.Option(False, "--dry-run", "-n", help="Show what would be done"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Apply changes without confirmation"),
):
    """Fix port conflicts by updating .env files with suggested ports."""
    scan_path = path or get_default_projects_dir()

    if not scan_path.exists():
        console.print(f"[red]Directory not found:[/red] {scan_path}")
        raise typer.Exit(1)

    apps = scan_directory(scan_path, max_depth)
    conflicts = [a for a in apps if a.suggested_port is not None]

    if not conflicts:
        console.print("[green]No port conflicts detected.[/green]")
        return

    console.print(f"[bold]Found {len(conflicts)} port conflict(s):[/bold]\n")

    for app in conflicts:
        env_path = app.path / ".env"
        console.print(f"  {app.name} ({app.framework})")
        console.print(f"    Current port: [red]{app.port}[/red]")
        console.print(f"    Suggested:    [green]{app.suggested_port}[/green]")
        console.print(f"    .env file:    {env_path}")
        console.print()

    if dry_run:
        console.print("[dim]Dry run - no changes made.[/dim]")
        return

    if not yes:
        confirm = typer.confirm("Apply these changes?")
        if not confirm:
            console.print("[yellow]Cancelled.[/yellow]")
            return

    console.print("\n[bold]Applying changes:[/bold]")
    for app in conflicts:
        if app.suggested_port is None:
            console.print(f"  [yellow]Skipping {app.name}:[/yellow] no valid port available")
            continue
        env_path = app.path / ".env"
        update_port_in_env(env_path, app.suggested_port)


def check_ghp_installed() -> bool:
    """Check if ghp CLI is installed."""
    try:
        result = subprocess.run(
            ["ghp", "--version"],
            capture_output=True,
            text=True,
        )
        return result.returncode == 0
    except FileNotFoundError:
        return False


def get_ghp_hooks() -> list[str]:
    """Get list of installed ghp hook names."""
    try:
        result = subprocess.run(
            ["ghp", "hooks", "list"],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            return []
        # Parse hook names from output (lines starting with ● or ○)
        hooks = []
        for line in result.stdout.splitlines():
            line = line.strip()
            if line.startswith("●") or line.startswith("○"):
                # Extract hook name after the bullet
                name = line.split()[1] if len(line.split()) > 1 else ""
                if name:
                    hooks.append(name)
        return hooks
    except FileNotFoundError:
        return []


def install_ghp_hook(name: str, event: str, command: str) -> bool:
    """Install a ghp event hook."""
    try:
        result = subprocess.run(
            ["ghp", "hooks", "add", name, "--event", event, "--command", command],
            capture_output=True,
            text=True,
        )
        return result.returncode == 0
    except FileNotFoundError:
        return False


@app.command("install-hooks")
def install_hooks(
    yes: bool = typer.Option(False, "--yes", "-y", help="Install without confirmation"),
    remove: bool = typer.Option(False, "--remove", "-r", help="Remove hooks instead of installing"),
):
    """Install ghp hooks for automatic worktree integration."""
    if not check_ghp_installed():
        console.print("[yellow]ghp CLI not found.[/yellow]")
        console.print("Install ghp to enable automatic worktree integration:")
        console.print("  npm install -g @bretwardjames/ghp-cli")
        return

    hooks_to_install = [
        ("ts-magic-up", "worktree-created", "ts-magic up ${worktree.path}"),
        ("ts-magic-down", "worktree-removed", "ts-magic down --all"),
    ]

    existing_hooks = get_ghp_hooks()

    if remove:
        # Remove hooks
        hooks_to_remove = [h[0] for h in hooks_to_install if h[0] in existing_hooks]
        if not hooks_to_remove:
            console.print("[dim]No ts-magic hooks installed.[/dim]")
            return

        console.print("[bold]Hooks to remove:[/bold]")
        for name in hooks_to_remove:
            console.print(f"  • {name}")

        if not yes:
            confirm = typer.confirm("\nRemove these hooks?")
            if not confirm:
                console.print("[yellow]Cancelled.[/yellow]")
                return

        for name in hooks_to_remove:
            result = subprocess.run(
                ["ghp", "hooks", "remove", name],
                capture_output=True,
                text=True,
            )
            if result.returncode == 0:
                console.print(f"  [green]✓[/green] Removed {name}")
            else:
                console.print(f"  [red]✗[/red] Failed to remove {name}")
        return

    # Install hooks
    hooks_needed = [(n, e, c) for n, e, c in hooks_to_install if n not in existing_hooks]

    if not hooks_needed:
        console.print("[green]✓ All ts-magic hooks already installed.[/green]")
        console.print("\nInstalled hooks:")
        for name, event, cmd in hooks_to_install:
            console.print(f"  • {name} ({event})")
        return

    console.print("[bold]ghp hooks for automatic worktree integration:[/bold]\n")
    for name, event, cmd in hooks_needed:
        console.print(f"  [cyan]{name}[/cyan] on [yellow]{event}[/yellow]")
        console.print(f"    {cmd}\n")

    console.print("These hooks will automatically set up/tear down Tailscale")
    console.print("funnels when you create or remove worktrees with ghp.\n")

    if not yes:
        confirm = typer.confirm("Install these hooks?")
        if not confirm:
            console.print("[yellow]Cancelled.[/yellow]")
            return

    console.print()
    for name, event, cmd in hooks_needed:
        if install_ghp_hook(name, event, cmd):
            console.print(f"  [green]✓[/green] Installed {name}")
        else:
            console.print(f"  [red]✗[/red] Failed to install {name}")

    console.print("\n[green]Done![/green] Funnels will be set up automatically when you run:")
    console.print("  ghp start <issue> --parallel")


@app.command()
def version():
    """Show version information."""
    console.print(f"ts-magic {__version__}")


if __name__ == "__main__":
    app()
