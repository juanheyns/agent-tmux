"""Harness abstraction — defines how each AI coding agent CLI is launched and managed."""

import os
import shutil
from pathlib import Path


HARNESSES = {
    "claude": {
        "binary": "claude",
        "exit_command": "/exit",
        "idle_prompts": {">", "$", "%"},
        "idle_prompt_prefixes": ["> "],
        "subagent_text": "local agent",
        "has_subagent_hooks": True,
        "settings_file": "claude/agent.json",
    },
    "codex": {
        "binary": "codex",
        "exit_command": "/exit",
        "idle_prompts": {">", "$", "%"},
        "idle_prompt_prefixes": ["> "],
        "subagent_text": None,
        "has_subagent_hooks": False,
        "settings_file": "codex/config.toml",
    },
}

DEFAULT_HARNESS = "claude"


def get_harness(name: str) -> dict:
    """Return harness config dict. Falls back to default for empty/missing name."""
    if not name:
        name = DEFAULT_HARNESS
    if name not in HARNESSES:
        raise KeyError(f"Unknown harness: {name!r}. Available: {', '.join(HARNESSES)}")
    return HARNESSES[name]


def check_binary(harness_name: str) -> bool:
    """Check if the harness binary is on PATH."""
    h = get_harness(harness_name)
    return shutil.which(h["binary"]) is not None


def get_exit_command(harness_name: str) -> str:
    return get_harness(harness_name)["exit_command"]


def is_idle_prompt(harness_name: str, line: str) -> bool:
    """Check if a pane last-line matches this harness's idle prompt."""
    h = get_harness(harness_name)
    if line in h["idle_prompts"]:
        return True
    return any(line.startswith(p) for p in h["idle_prompt_prefixes"])


def has_subagent_indicator(harness_name: str, pane_text: str) -> bool:
    """Check if pane text indicates active subagents."""
    h = get_harness(harness_name)
    if h["subagent_text"] is None:
        return False
    return h["subagent_text"] in pane_text


def get_settings_path(harness_name: str, atmux_dir: Path) -> Path:
    """Return absolute path to the harness settings file."""
    h = get_harness(harness_name)
    return atmux_dir / "settings" / h["settings_file"]


def ensure_settings(harness_name: str, agent_dir: str, atmux_dir: str) -> None:
    """Ensure harness settings are available to the agent.

    Claude: no-op (uses --settings flag).
    Codex: copies config.toml into agent_dir/.codex/ since Codex reads from cwd.
    """
    if harness_name == "codex":
        src = Path(atmux_dir) / "settings" / "codex" / "config.toml"
        if not src.exists():
            return
        dest_dir = Path(agent_dir) / ".codex"
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / "config.toml"
        shutil.copy2(str(src), str(dest))


def build_launch_cmd(
    harness_name: str,
    agent_name: str,
    atmux_dir: str,
    session: str,
    workspace: str,
    flags: str = "",
) -> str:
    """Build the full shell command string to launch an agent in tmux."""
    h = get_harness(harness_name)
    binary = h["binary"]

    env_exports = (
        f"export ATMUX_AGENT={agent_name} "
        f"ATMUX_SESSION='{session}' "
        f"ATMUX_DIR='{atmux_dir}' "
        f"ATMUX_WORKSPACE='{workspace}'"
    )

    if harness_name == "claude":
        settings_path = os.path.join(atmux_dir, "settings", "claude", "agent.json")
        cmd = f"{binary} --permission-mode auto --settings '{settings_path}' --name \"{agent_name}\""
    elif harness_name == "codex":
        cmd = f"{binary} --full-auto"
    else:
        cmd = binary

    if flags:
        cmd += f" {flags}"

    return f"{env_exports} && {cmd}"
