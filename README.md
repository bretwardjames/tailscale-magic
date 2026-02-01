# ts-funnel

Auto-discover and funnel local dev servers through Tailscale.

## Features

- **Auto-discovery**: Scans your projects directory for web apps
- **Framework detection**: Supports Nuxt, Next.js, Vite, Django, FastAPI, NestJS, Express
- **Port detection**: Extracts ports from package.json, pyproject.toml, and .env files
- **Conflict resolution**: Detects port conflicts and suggests alternatives
- **Funnel/Serve modes**: Public internet (funnel) or tailnet-only (serve) access
- **CORS updates**: Adds your Tailscale domain to CORS/CSRF configs

## Installation

```bash
cd ts-funnel
pip install -e .
```

## Usage

### Scan for web apps

```bash
# Scan default directory (auto-detected: ~/IdeaProjects, ~/Projects, etc.)
ts-funnel scan

# Scan a specific directory
ts-funnel scan /path/to/projects

# Adjust scan depth for monorepos
ts-funnel scan --depth 3
```

### Set up funnels

```bash
# Set up funnels (public internet) for all detected apps
ts-funnel up

# Set up serves (tailnet only - more secure)
ts-funnel up --mode serve

# Dry run - show what would be done
ts-funnel up --dry-run

# Specific port only
ts-funnel up --port 3000

# Skip CORS updates
ts-funnel up --no-cors
```

### Fix port conflicts

When multiple projects use the same default port, ts-funnel detects this and suggests alternatives:

```bash
# See conflicts in scan output
ts-funnel scan

# Preview what would change
ts-funnel fix-conflicts --dry-run

# Apply changes (with confirmation prompt)
ts-funnel fix-conflicts

# Apply without confirmation
ts-funnel fix-conflicts -y
```

### Check status

```bash
ts-funnel status
```

### Remove funnels

```bash
ts-funnel down --all
```

## Supported Frameworks

### Frontend
- Nuxt.js (port 3000)
- Next.js (port 3000)
- Vite (port 5173)
- Create React App (port 3000)
- Angular (port 4200)
- Vue CLI (port 8080)

### Backend
- Django (port 8000)
- FastAPI (port 8000)
- Flask (port 5000)
- NestJS (port 3000)
- Express (port 3000)

## How it works

1. **Scan**: Looks for framework markers (package.json, manage.py, etc.)
2. **Detect**: Identifies framework type and extracts port configuration
3. **Resolve**: Detects port conflicts and suggests alternatives
4. **Funnel**: Sets up `tailscale funnel` or `tailscale serve` for each unique port
5. **Update**: Adds your Tailscale domain to CORS configs

## Funnel vs Serve

- **Funnel** (`--mode funnel`): Exposes your server to the public internet via `https://yourhost.ts.net:port`
- **Serve** (`--mode serve`): Only accessible within your tailnet (more secure for dev work)

Both modes give you HTTPS with valid certificates automatically.

## Requirements

- Python 3.10+
- Tailscale installed and running
- Tailscale Funnel enabled on your tailnet (for public access)
