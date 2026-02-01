# ts-funnel

Auto-discover and funnel local dev servers through Tailscale.

## Features

- **Auto-discovery**: Scans your projects directory for web apps
- **Framework detection**: Supports Nuxt, Next.js, Vite, Django, FastAPI, NestJS, Express
- **Port detection**: Extracts ports from package.json, pyproject.toml, and .env files
- **Funnel setup**: Automatically configures Tailscale funnels
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
```

### Set up funnels

```bash
# Set up funnels for all detected apps and update CORS configs
ts-funnel up

# Dry run - show what would be done
ts-funnel up --dry-run

# Specific directory
ts-funnel up /path/to/projects

# Specific port only
ts-funnel up --port 3000

# Skip CORS updates
ts-funnel up --no-cors
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
3. **Funnel**: Sets up `tailscale funnel` for each unique port
4. **Update**: Adds your Tailscale domain to CORS configs

## Requirements

- Python 3.10+
- Tailscale installed and running
- Tailscale Funnel enabled on your tailnet
