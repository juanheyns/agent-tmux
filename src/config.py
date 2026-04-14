"""atmux configuration."""

import os
from pathlib import Path

# Install directory (where atmux code lives)
ATMUX_DIR = Path(os.environ.get("ATMUX_DIR", Path(__file__).resolve().parent.parent))

# Workspace directory (where the user runs atmux, has .atmux/)
# Set by the launcher via ATMUX_WORKSPACE env var, or passed as arg to dashboard
WORKSPACE_DIR = Path(os.environ.get("ATMUX_WORKSPACE", Path.cwd()))

# Session name (read from workspace config at runtime)
SESSION = "atmux"

SETTINGS_DIR = ATMUX_DIR / "settings"


def status_dir() -> Path:
    return WORKSPACE_DIR / ".atmux" / "status"


def set_workspace(ws: Path) -> None:
    """Set the workspace directory (called by dashboard on startup)."""
    global WORKSPACE_DIR
    WORKSPACE_DIR = ws.resolve()
