"""Scan directories for web app projects and detect their configurations."""
import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

try:
    import tomli
except ImportError:
    import tomllib as tomli

from dotenv import dotenv_values


@dataclass
class WebApp:
    """Represents a detected web application."""
    name: str
    path: Path
    framework: str
    port: int
    app_type: str  # "frontend" or "backend"
    cors_config_path: Optional[Path] = None
    env_file: Optional[Path] = None
    extra_info: dict = field(default_factory=dict)


# Framework detection patterns
FRONTEND_FRAMEWORKS = {
    "nuxt": {"markers": ["nuxt.config.ts", "nuxt.config.js"], "default_port": 3000},
    "next": {"markers": ["next.config.js", "next.config.mjs", "next.config.ts"], "default_port": 3000},
    "vite": {"markers": ["vite.config.ts", "vite.config.js"], "default_port": 5173},
    "react-cra": {"markers": [], "script_pattern": "react-scripts", "default_port": 3000},
    "angular": {"markers": ["angular.json"], "default_port": 4200},
    "vue-cli": {"markers": ["vue.config.js"], "default_port": 8080},
}

BACKEND_FRAMEWORKS = {
    "django": {"markers": ["manage.py"], "default_port": 8000},
    "fastapi": {"markers": [], "pyproject_pattern": "fastapi", "default_port": 8000},
    "flask": {"markers": [], "pyproject_pattern": "flask", "default_port": 5000},
    "nestjs": {"markers": ["nest-cli.json"], "default_port": 3000},
    "express": {"markers": [], "script_pattern": "express", "default_port": 3000},
}


def find_port_in_package_json(pkg_json: dict) -> Optional[int]:
    """Extract port from package.json scripts."""
    scripts = pkg_json.get("scripts", {})
    for script_name in ["dev", "start", "serve"]:
        script = scripts.get(script_name, "")
        # Look for --port flags
        port_match = re.search(r"--port[=\s]+(\d+)", script)
        if port_match:
            return int(port_match.group(1))
        # Look for -p flags
        port_match = re.search(r"\s-p\s+(\d+)", script)
        if port_match:
            return int(port_match.group(1))
    return None


def find_port_in_env(env_path: Path) -> Optional[int]:
    """Extract PORT from .env file."""
    if not env_path.exists():
        return None
    env_vars = dotenv_values(env_path)
    port_str = env_vars.get("PORT") or env_vars.get("VITE_PORT") or env_vars.get("DEV_PORT")
    if port_str:
        try:
            return int(port_str)
        except ValueError:
            pass
    return None


def detect_frontend_framework(project_path: Path) -> Optional[tuple[str, int]]:
    """Detect frontend framework and its port."""
    pkg_json_path = project_path / "package.json"
    if not pkg_json_path.exists():
        return None

    try:
        with open(pkg_json_path) as f:
            pkg_json = json.load(f)
    except (json.JSONDecodeError, IOError):
        return None

    scripts = pkg_json.get("scripts", {})
    dev_script = scripts.get("dev", "") + scripts.get("start", "")

    for framework, config in FRONTEND_FRAMEWORKS.items():
        # Check for marker files
        for marker in config["markers"]:
            if (project_path / marker).exists():
                port = find_port_in_package_json(pkg_json) or config["default_port"]
                return framework, port

        # Check script patterns
        if "script_pattern" in config and config["script_pattern"] in dev_script:
            port = find_port_in_package_json(pkg_json) or config["default_port"]
            return framework, port

    # Check for nuxt/next/vite in dev script
    if "nuxt" in dev_script:
        port = find_port_in_package_json(pkg_json) or 3000
        return "nuxt", port
    if "next" in dev_script:
        port = find_port_in_package_json(pkg_json) or 3000
        return "next", port
    if "vite" in dev_script:
        port = find_port_in_package_json(pkg_json) or 5173
        return "vite", port

    return None


def detect_backend_framework(project_path: Path) -> Optional[tuple[str, int]]:
    """Detect backend framework and its port."""
    # Check for Django
    if (project_path / "manage.py").exists():
        port = find_port_in_env(project_path / ".env") or 8000
        return "django", port

    # Check for NestJS
    if (project_path / "nest-cli.json").exists():
        port = find_port_in_env(project_path / ".env") or 3000
        return "nestjs", port

    # Check pyproject.toml for Python frameworks
    pyproject_path = project_path / "pyproject.toml"
    if pyproject_path.exists():
        try:
            with open(pyproject_path, "rb") as f:
                pyproject = tomli.load(f)
            deps = str(pyproject.get("project", {}).get("dependencies", []))
            if "fastapi" in deps.lower():
                port = find_port_in_env(project_path / ".env") or 8000
                return "fastapi", port
            if "flask" in deps.lower():
                port = find_port_in_env(project_path / ".env") or 5000
                return "flask", port
        except Exception:
            pass

    # Check package.json for Node backends
    pkg_json_path = project_path / "package.json"
    if pkg_json_path.exists():
        try:
            with open(pkg_json_path) as f:
                pkg_json = json.load(f)
            deps = str(pkg_json.get("dependencies", {}))
            if "express" in deps.lower():
                port = find_port_in_package_json(pkg_json) or find_port_in_env(project_path / ".env") or 3000
                return "express", port
        except Exception:
            pass

    return None


def find_cors_config(project_path: Path, framework: str) -> Optional[Path]:
    """Find the CORS configuration file for a project."""
    if framework == "django":
        # Look for settings files
        for pattern in ["**/settings.py", "**/settings/dev.py", "**/settings/local.py", "**/settings/base.py"]:
            matches = list(project_path.glob(pattern))
            for match in matches:
                content = match.read_text()
                if "CORS" in content or "CSRF_TRUSTED" in content:
                    return match

    elif framework == "fastapi":
        # Look for main.py or app.py with CORSMiddleware
        for pattern in ["main.py", "app.py", "app/main.py", "src/main.py"]:
            path = project_path / pattern
            if path.exists():
                content = path.read_text()
                if "CORSMiddleware" in content or "cors" in content.lower():
                    return path

    elif framework in ("express", "nestjs"):
        # Look for cors configuration in JS/TS files
        for pattern in ["**/cors*.ts", "**/cors*.js", "**/app.ts", "**/main.ts", "**/index.ts"]:
            matches = list(project_path.glob(pattern))
            for match in matches:
                content = match.read_text()
                if "cors" in content.lower():
                    return match

    return None


def scan_directory(root_path: Path, max_depth: int = 2) -> list[WebApp]:
    """Scan a directory for web app projects."""
    apps = []
    root_path = root_path.resolve()

    def scan_project(project_path: Path, depth: int = 0):
        if depth > max_depth:
            return

        # Skip hidden directories and common non-project dirs
        if project_path.name.startswith(".") or project_path.name in ("node_modules", "venv", ".venv", "__pycache__", "dist", "build"):
            return

        # Check for frontend
        frontend = detect_frontend_framework(project_path)
        if frontend:
            framework, port = frontend
            cors_path = find_cors_config(project_path, framework)
            env_file = project_path / ".env" if (project_path / ".env").exists() else None
            apps.append(WebApp(
                name=project_path.name,
                path=project_path,
                framework=framework,
                port=port,
                app_type="frontend",
                cors_config_path=cors_path,
                env_file=env_file,
            ))

        # Check for backend
        backend = detect_backend_framework(project_path)
        if backend:
            framework, port = backend
            cors_path = find_cors_config(project_path, framework)
            env_file = project_path / ".env" if (project_path / ".env").exists() else None
            apps.append(WebApp(
                name=project_path.name,
                path=project_path,
                framework=framework,
                port=port,
                app_type="backend",
                cors_config_path=cors_path,
                env_file=env_file,
            ))

        # Recurse into subdirectories (for monorepos)
        if project_path.is_dir():
            for child in project_path.iterdir():
                if child.is_dir():
                    scan_project(child, depth + 1)

    for item in root_path.iterdir():
        if item.is_dir():
            scan_project(item)

    return apps
