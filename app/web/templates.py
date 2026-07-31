"""Shared Jinja2 templates instance for the HTMX dashboard (Phase 5, item 2)."""
from pathlib import Path

from fastapi.templating import Jinja2Templates

TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


def humanize_time(seconds: int) -> str:
    """Convert seconds to human-readable relative time (e.g., '2 minutes ago')."""
    if seconds < 60:
        return "just now"
    elif seconds < 3600:
        minutes = seconds // 60
        return f"{minutes}m ago"
    elif seconds < 86400:
        hours = seconds // 3600
        return f"{hours}h ago"
    else:
        days = seconds // 86400
        return f"{days}d ago"


# Register custom filters
templates.env.filters["humanize_time"] = humanize_time
