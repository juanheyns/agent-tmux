"""Workspace state management — .atmux/ directory."""

import json
from pathlib import Path

WORKSPACE_DIR_NAME = ".atmux"
AGENTS_FILE = "agents.json"
HEARTBEATS_FILE = "heartbeats.json"
CONFIG_FILE = "config.json"
STATUS_DIR = "status"


def find_workspace(start: Path | None = None) -> Path | None:
    """Find the workspace root by looking for .atmux/ in start dir and parents."""
    d = (start or Path.cwd()).resolve()
    for _ in range(50):  # safety limit
        if (d / WORKSPACE_DIR_NAME).is_dir():
            return d
        parent = d.parent
        if parent == d:
            break
        d = parent
    return None


def workspace_dir(ws: Path) -> Path:
    return ws / WORKSPACE_DIR_NAME


def status_dir(ws: Path) -> Path:
    return ws / WORKSPACE_DIR_NAME / STATUS_DIR


def agents_dir(ws: Path) -> Path:
    return ws / "agents"


def config_path(ws: Path) -> Path:
    return ws / WORKSPACE_DIR_NAME / CONFIG_FILE


def agents_path(ws: Path) -> Path:
    return ws / WORKSPACE_DIR_NAME / AGENTS_FILE


def widgets_dir(ws: Path) -> Path:
    return ws / WORKSPACE_DIR_NAME / "widgets"


def init_workspace(ws: Path) -> None:
    """Initialize a new workspace at the given path."""
    d = workspace_dir(ws)
    d.mkdir(parents=True, exist_ok=True)
    status_dir(ws).mkdir(exist_ok=True)
    widgets_dir(ws).mkdir(exist_ok=True)

    cfg = config_path(ws)
    if not cfg.exists():
        session_name = "atmux-" + ws.resolve().name
        cfg.write_text(
            json.dumps({"session": session_name, "version": 1}, indent=2) + "\n"
        )

    agents = agents_path(ws)
    if not agents.exists():
        agents.write_text(json.dumps([], indent=2) + "\n")


def load_config(ws: Path) -> dict:
    """Load workspace config."""
    cfg = config_path(ws)
    if cfg.exists():
        return json.loads(cfg.read_text())
    return {"session": "atmux"}


def load_agents(ws: Path) -> list[dict]:
    """Load the persisted agent list.

    Each agent: {"name": "dev1", "repo": "owner/repo", "dir": "/abs/path"}
    """
    p = agents_path(ws)
    if p.exists():
        return json.loads(p.read_text())
    return []


def save_agents(ws: Path, agents: list[dict]) -> None:
    """Save the agent list."""
    p = agents_path(ws)
    p.write_text(json.dumps(agents, indent=2) + "\n")


def add_agent(
    ws: Path, name: str, repo: str, directory: str, flags: str = "", harness: str = ""
) -> None:
    """Add an agent to the persisted list."""
    agents = load_agents(ws)
    agents = [a for a in agents if a["name"] != name]
    entry = {"name": name, "repo": repo, "dir": directory}
    if flags:
        entry["flags"] = flags
    if harness:
        entry["harness"] = harness
    agents.append(entry)
    save_agents(ws, agents)


def migrate_workspace(ws: Path) -> None:
    """Migrate a workspace created before multi-harness support.

    Adds "harness": "claude" to any agent entries missing it and bumps the
    config version so the migration only runs once.
    """
    cfg = load_config(ws)
    version = cfg.get("version", 0)
    if version >= 1:
        return

    # Backfill harness field on existing agents
    agents = load_agents(ws)
    changed = False
    for a in agents:
        if "harness" not in a:
            a["harness"] = "claude"
            changed = True
    if changed:
        save_agents(ws, agents)

    # Stamp version so we don't re-run
    cfg["version"] = 1
    config_path(ws).write_text(json.dumps(cfg, indent=2) + "\n")


def remove_agent(ws: Path, name: str) -> None:
    """Remove an agent from the persisted list."""
    agents = load_agents(ws)
    agents = [a for a in agents if a["name"] != name]
    save_agents(ws, agents)


def get_agent(ws: Path, name: str) -> dict | None:
    """Get a single agent by name."""
    for a in load_agents(ws):
        if a["name"] == name:
            return a
    return None


# -- Heartbeats --


def heartbeats_path(ws: Path) -> Path:
    return ws / WORKSPACE_DIR_NAME / HEARTBEATS_FILE


def load_heartbeats(ws: Path) -> list[dict]:
    """Load heartbeat configs.

    Each: {"agent": "dev1" or "all", "interval": 60, "message": "..."}
    """
    p = heartbeats_path(ws)
    if p.exists():
        return json.loads(p.read_text())
    return []


def save_heartbeats(ws: Path, heartbeats: list[dict]) -> None:
    p = heartbeats_path(ws)
    p.write_text(json.dumps(heartbeats, indent=2) + "\n")


def set_heartbeat(ws: Path, agent: str, interval: int, message: str) -> None:
    """Set a heartbeat for an agent (or 'all'). Replaces existing."""
    hbs = load_heartbeats(ws)
    hbs = [h for h in hbs if h["agent"] != agent]
    hbs.append({"agent": agent, "interval": interval, "message": message})
    save_heartbeats(ws, hbs)


def remove_heartbeat(ws: Path, agent: str) -> None:
    """Remove heartbeat for an agent (or 'all')."""
    hbs = load_heartbeats(ws)
    hbs = [h for h in hbs if h["agent"] != agent]
    save_heartbeats(ws, hbs)
