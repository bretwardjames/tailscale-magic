"""ts-funnel: Auto-discover and funnel local dev servers through Tailscale."""
import re

__version__ = "0.1.0"


def validate_port(port: int) -> bool:
    """Validate port is in valid range."""
    return isinstance(port, int) and 1 <= port <= 65535


def is_valid_domain(domain: str) -> bool:
    """Validate domain has expected format (no special characters that could break configs)."""
    if not domain or len(domain) > 253:
        return False
    # Allow alphanumeric, hyphens, dots - standard domain format
    return bool(re.match(r'^[a-zA-Z0-9]([a-zA-Z0-9\-\.]*[a-zA-Z0-9])?$', domain))
