"""Update CORS/allowlist configurations in detected projects."""
import os
import re
import tempfile
from pathlib import Path
from typing import Optional

from rich.console import Console

from . import is_valid_domain

console = Console()


def _atomic_write(path: Path, content: str) -> None:
    """Write content to file atomically (write to temp, then rename)."""
    # Create temp file in same directory to ensure same filesystem for rename
    fd, tmp_path = tempfile.mkstemp(dir=path.parent, prefix='.tmp_', suffix='.env')
    try:
        with os.fdopen(fd, 'w') as f:
            f.write(content)
        os.replace(tmp_path, path)  # Atomic on POSIX
    except Exception:
        # Clean up temp file on failure
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def is_safe_path(base_path: Path, target_path: Path) -> bool:
    """Verify target path is within base path (no symlink escapes)."""
    try:
        resolved_target = target_path.resolve()
        resolved_base = base_path.resolve()
        return resolved_target.is_relative_to(resolved_base)
    except (ValueError, OSError):
        return False


def format_new_origins(origins: str, new_domain: str, quote_char: str = '"') -> str:
    """Format new origins string, handling empty lists correctly."""
    if not origins.strip():
        return f'\n    {quote_char}{new_domain}{quote_char},\n'
    elif origins.strip().endswith(","):
        return f'{origins}    {quote_char}{new_domain}{quote_char},\n'
    else:
        return f'{origins},\n    {quote_char}{new_domain}{quote_char},\n'


def _update_django_cors(config_path: Path, domain: str) -> bool:
    """Update Django CORS/CSRF settings to include the domain.

    Internal function - use update_cors_config() for path validation.
    """
    if not is_valid_domain(domain):
        console.print(f"[red]Invalid domain format:[/red] {domain}")
        return False

    try:
        content = config_path.read_text()
        modified = False
        https_domain = f"https://{domain}"

        # Check CSRF_TRUSTED_ORIGINS
        if "CSRF_TRUSTED_ORIGINS" in content:
            # Check if domain already exists
            if domain not in content:
                # Find the CSRF_TRUSTED_ORIGINS tuple/list and add the domain
                pattern = r"(CSRF_TRUSTED_ORIGINS\s*=\s*[\(\[])([^\)\]]*)([\)\]])"
                match = re.search(pattern, content, re.DOTALL)
                if match:
                    origins = match.group(2)
                    new_origins = format_new_origins(origins, https_domain)
                    content = content[:match.start(2)] + new_origins + content[match.end(2):]
                    modified = True

        # Check CORS_ALLOWED_ORIGINS (if not using CORS_ALLOW_ALL_ORIGINS)
        if "CORS_ALLOWED_ORIGINS" in content and "CORS_ALLOW_ALL_ORIGINS = True" not in content:
            if domain not in content:
                pattern = r"(CORS_ALLOWED_ORIGINS\s*=\s*[\[\(])([^\]\)]*)([\]\)])"
                match = re.search(pattern, content, re.DOTALL)
                if match:
                    origins = match.group(2)
                    new_origins = format_new_origins(origins, https_domain)
                    content = content[:match.start(2)] + new_origins + content[match.end(2):]
                    modified = True

        if modified:
            _atomic_write(config_path, content)
            console.print(f"[green]Updated[/green] {config_path}")
            return True
        else:
            if domain in content:
                console.print(f"[dim]Already configured:[/dim] {config_path}")
            return False

    except Exception as e:
        console.print(f"[red]Error updating {config_path}:[/red] {e}")
        return False


def _update_fastapi_cors(config_path: Path, domain: str) -> bool:
    """Update FastAPI CORSMiddleware to include the domain.

    Internal function - use update_cors_config() for path validation.
    """
    if not is_valid_domain(domain):
        console.print(f"[red]Invalid domain format:[/red] {domain}")
        return False

    try:
        content = config_path.read_text()
        https_domain = f"https://{domain}"

        if domain in content:
            console.print(f"[dim]Already configured:[/dim] {config_path}")
            return False

        # Look for allow_origins list
        pattern = r"(allow_origins\s*=\s*\[)([^\]]*?)(\])"
        match = re.search(pattern, content, re.DOTALL)
        if match:
            origins = match.group(2)
            if '"*"' in origins or "'*'" in origins:
                console.print(f"[dim]Using wildcard origins:[/dim] {config_path}")
                return False

            new_origins = format_new_origins(origins, https_domain)
            content = content[:match.start(2)] + new_origins + content[match.end(2):]
            _atomic_write(config_path, content)
            console.print(f"[green]Updated[/green] {config_path}")
            return True

        return False

    except Exception as e:
        console.print(f"[red]Error updating {config_path}:[/red] {e}")
        return False


def _update_express_cors(config_path: Path, domain: str) -> bool:
    """Update Express CORS config to include the domain.

    Internal function - use update_cors_config() for path validation.
    """
    if not is_valid_domain(domain):
        console.print(f"[red]Invalid domain format:[/red] {domain}")
        return False

    try:
        content = config_path.read_text()
        https_domain = f"https://{domain}"

        if domain in content:
            console.print(f"[dim]Already configured:[/dim] {config_path}")
            return False

        # Look for origin array in cors config
        pattern = r"(origin\s*:\s*\[)([^\]]*?)(\])"
        match = re.search(pattern, content, re.DOTALL)
        if match:
            origins = match.group(2)
            new_origins = format_new_origins(origins, https_domain, quote_char="'")
            content = content[:match.start(2)] + new_origins + content[match.end(2):]
            _atomic_write(config_path, content)
            console.print(f"[green]Updated[/green] {config_path}")
            return True

        return False

    except Exception as e:
        console.print(f"[red]Error updating {config_path}:[/red] {e}")
        return False


def _update_env_file(env_path: Path, domain: str, var_name: str = "ALLOWED_HOSTS") -> bool:
    """Add or update an environment variable with the domain.

    Internal function - callers should validate paths.
    """
    if not is_valid_domain(domain):
        console.print(f"[red]Invalid domain format:[/red] {domain}")
        return False

    try:
        https_domain = f"https://{domain}"

        if env_path.exists():
            content = env_path.read_text()
            if domain in content:
                console.print(f"[dim]Already in env:[/dim] {env_path}")
                return False

            # Check if the variable exists
            pattern = rf"^{var_name}=(.*)$"
            match = re.search(pattern, content, re.MULTILINE)
            if match:
                current_value = match.group(1)
                if current_value:
                    new_value = f"{current_value},{https_domain}"
                else:
                    new_value = https_domain
                content = re.sub(pattern, f"{var_name}={new_value}", content, flags=re.MULTILINE)
            else:
                content += f"\n{var_name}={https_domain}\n"

            _atomic_write(env_path, content)
            console.print(f"[green]Updated[/green] {env_path}")
            return True
        else:
            _atomic_write(env_path, f"{var_name}={https_domain}\n")
            console.print(f"[green]Created[/green] {env_path}")
            return True

    except Exception as e:
        console.print(f"[red]Error updating {env_path}:[/red] {e}")
        return False


def update_port_in_env(env_path: Path, new_port: int, var_names: list[str] = None) -> bool:
    """Update port number in .env file.

    Args:
        env_path: Path to .env file
        new_port: New port number to set
        var_names: List of variable names to check (e.g., ["PORT", "VITE_PORT"])
    """
    from . import validate_port

    if not validate_port(new_port):
        console.print(f"[red]Invalid port number:[/red] {new_port}")
        return False

    if var_names is None:
        var_names = ["PORT", "VITE_PORT", "DEV_PORT", "WEB_PORT", "SERVER_PORT"]

    try:
        if not env_path.exists():
            # Create new .env with PORT
            _atomic_write(env_path, f"PORT={new_port}\n")
            console.print(f"[green]Created[/green] {env_path} with PORT={new_port}")
            return True

        content = env_path.read_text()
        modified = False

        for var_name in var_names:
            pattern = rf"^({var_name})=(\d+)(.*)$"
            match = re.search(pattern, content, re.MULTILINE)
            if match:
                old_port = match.group(2)
                suffix = match.group(3)  # Preserve any trailing comments
                content = re.sub(
                    pattern,
                    f"{var_name}={new_port}{suffix}",
                    content,
                    flags=re.MULTILINE
                )
                console.print(f"[green]Updated[/green] {env_path}: {var_name} {old_port} → {new_port}")
                modified = True
                break  # Only update the first matching variable

        if modified:
            _atomic_write(env_path, content)
            return True
        else:
            # No existing port variable found, add PORT
            content = content.rstrip() + f"\nPORT={new_port}\n"
            _atomic_write(env_path, content)
            console.print(f"[green]Added[/green] PORT={new_port} to {env_path}")
            return True

    except Exception as e:
        console.print(f"[red]Error updating {env_path}:[/red] {e}")
        return False


def update_cors_config(config_path: Path, framework: str, domain: str, project_path: Optional[Path] = None) -> bool:
    """Update CORS config based on framework type.

    This is the public API - it validates paths before delegating to internal functions.
    """
    # Safety check: ensure config_path is within project_path if provided
    if project_path and not is_safe_path(project_path, config_path):
        console.print(f"[red]Skipping unsafe path:[/red] {config_path}")
        return False

    if framework == "django":
        return _update_django_cors(config_path, domain)
    elif framework == "fastapi":
        return _update_fastapi_cors(config_path, domain)
    elif framework in ("express", "nestjs"):
        return _update_express_cors(config_path, domain)
    else:
        console.print(f"[yellow]Unsupported framework for CORS update:[/yellow] {framework}")
        return False
