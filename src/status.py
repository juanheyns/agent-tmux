"""Read agent status from .atmux/status/ files."""
from . import config


def read_agent_status(name: str) -> str:
    """Return 'busy', 'idle', or '?'."""
    f = config.status_dir() / name
    try:
        return f.read_text().strip()
    except (FileNotFoundError, PermissionError):
        return "?"


def read_subagent_count(name: str) -> int:
    """Return number of active subagents."""
    f = config.status_dir() / f"{name}.subagents"
    try:
        return max(0, int(f.read_text().strip()))
    except (FileNotFoundError, PermissionError, ValueError):
        return 0


def agent_summary(name: str, repo: str = "") -> dict:
    """Get runtime status for an agent."""
    return {
        "name": name,
        "status": read_agent_status(name),
        "subagents": read_subagent_count(name),
        "repo": repo,
    }
