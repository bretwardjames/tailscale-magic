"""Update CORS/allowlist configurations in detected projects."""
import re
from pathlib import Path
from typing import Optional

from rich.console import Console

console = Console()


def update_django_cors(config_path: Path, domain: str) -> bool:
    """Update Django CORS/CSRF settings to include the domain."""
    try:
        content = config_path.read_text()
        modified = False
        https_domain = f"https://{domain}"
        http_domain = f"http://{domain}"

        # Check CSRF_TRUSTED_ORIGINS
        if "CSRF_TRUSTED_ORIGINS" in content:
            # Check if domain already exists
            if domain not in content:
                # Find the CSRF_TRUSTED_ORIGINS tuple/list and add the domain
                pattern = r"(CSRF_TRUSTED_ORIGINS\s*=\s*[\(\[])([^\)\]]*)([\)\]])"
                match = re.search(pattern, content, re.DOTALL)
                if match:
                    origins = match.group(2)
                    # Add the new domain before the closing bracket
                    if origins.strip().endswith(","):
                        new_origins = f'{origins}    "{https_domain}",\n'
                    else:
                        new_origins = f'{origins},\n    "{https_domain}",\n'
                    content = content[:match.start(2)] + new_origins + content[match.end(2):]
                    modified = True

        # Check CORS_ALLOWED_ORIGINS (if not using CORS_ALLOW_ALL_ORIGINS)
        if "CORS_ALLOWED_ORIGINS" in content and "CORS_ALLOW_ALL_ORIGINS = True" not in content:
            if domain not in content:
                pattern = r"(CORS_ALLOWED_ORIGINS\s*=\s*[\[\(])([^\]\)]*)([\]\)])"
                match = re.search(pattern, content, re.DOTALL)
                if match:
                    origins = match.group(2)
                    if origins.strip().endswith(","):
                        new_origins = f'{origins}    "{https_domain}",\n'
                    else:
                        new_origins = f'{origins},\n    "{https_domain}",\n'
                    content = content[:match.start(2)] + new_origins + content[match.end(2):]
                    modified = True

        if modified:
            config_path.write_text(content)
            console.print(f"[green]Updated[/green] {config_path}")
            return True
        else:
            if domain in content:
                console.print(f"[dim]Already configured:[/dim] {config_path}")
            return False

    except Exception as e:
        console.print(f"[red]Error updating {config_path}:[/red] {e}")
        return False


def update_fastapi_cors(config_path: Path, domain: str) -> bool:
    """Update FastAPI CORSMiddleware to include the domain."""
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

            if origins.strip().endswith(","):
                new_origins = f'{origins}    "{https_domain}",\n'
            else:
                new_origins = f'{origins},\n    "{https_domain}",\n'

            content = content[:match.start(2)] + new_origins + content[match.end(2):]
            config_path.write_text(content)
            console.print(f"[green]Updated[/green] {config_path}")
            return True

        return False

    except Exception as e:
        console.print(f"[red]Error updating {config_path}:[/red] {e}")
        return False


def update_express_cors(config_path: Path, domain: str) -> bool:
    """Update Express CORS config to include the domain."""
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
            if origins.strip().endswith(","):
                new_origins = f"{origins}    '{https_domain}',\n"
            else:
                new_origins = f"{origins},\n    '{https_domain}',\n"

            content = content[:match.start(2)] + new_origins + content[match.end(2):]
            config_path.write_text(content)
            console.print(f"[green]Updated[/green] {config_path}")
            return True

        return False

    except Exception as e:
        console.print(f"[red]Error updating {config_path}:[/red] {e}")
        return False


def update_env_file(env_path: Path, domain: str, var_name: str = "ALLOWED_HOSTS") -> bool:
    """Add or update an environment variable with the domain."""
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

            env_path.write_text(content)
            console.print(f"[green]Updated[/green] {env_path}")
            return True
        else:
            env_path.write_text(f"{var_name}={https_domain}\n")
            console.print(f"[green]Created[/green] {env_path}")
            return True

    except Exception as e:
        console.print(f"[red]Error updating {env_path}:[/red] {e}")
        return False


def update_cors_config(config_path: Path, framework: str, domain: str) -> bool:
    """Update CORS config based on framework type."""
    if framework == "django":
        return update_django_cors(config_path, domain)
    elif framework == "fastapi":
        return update_fastapi_cors(config_path, domain)
    elif framework in ("express", "nestjs"):
        return update_express_cors(config_path, domain)
    else:
        console.print(f"[yellow]Unsupported framework for CORS update:[/yellow] {framework}")
        return False
