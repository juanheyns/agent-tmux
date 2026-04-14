"""Tests for workspace state management."""
import json
import shutil
import tempfile
from pathlib import Path

import pytest

from src.workspace import (
    init_workspace,
    migrate_workspace,
    load_agents,
    save_agents,
    add_agent,
    remove_agent,
    get_agent,
    load_config,
    load_heartbeats,
    set_heartbeat,
    remove_heartbeat,
    find_workspace,
    config_path,
    status_dir,
    widgets_dir,
)


@pytest.fixture
def ws(tmp_path):
    init_workspace(tmp_path)
    return tmp_path


class TestInitWorkspace:
    def test_creates_directory_structure(self, ws):
        assert (ws / ".atmux").is_dir()
        assert (ws / ".atmux" / "config.json").is_file()
        assert (ws / ".atmux" / "agents.json").is_file()
        assert status_dir(ws).is_dir()
        assert widgets_dir(ws).is_dir()

    def test_config_has_session_name(self, ws):
        cfg = load_config(ws)
        assert "session" in cfg
        assert cfg["session"].startswith("atmux-")

    def test_agents_starts_empty(self, ws):
        assert load_agents(ws) == []

    def test_idempotent(self, ws):
        # Init again should not overwrite
        (ws / ".atmux" / "config.json").write_text('{"session": "custom"}')
        init_workspace(ws)
        assert load_config(ws)["session"] == "custom"


class TestAgents:
    def test_add_agent(self, ws):
        add_agent(ws, "dev1", "owner/repo", "/tmp/fake")
        agents = load_agents(ws)
        assert len(agents) == 1
        assert agents[0]["name"] == "dev1"
        assert agents[0]["repo"] == "owner/repo"
        assert agents[0]["dir"] == "/tmp/fake"

    def test_add_agent_with_flags(self, ws):
        add_agent(ws, "dev1", "owner/repo", "/tmp/fake", flags="--model sonnet")
        agent = get_agent(ws, "dev1")
        assert agent["flags"] == "--model sonnet"

    def test_add_agent_without_flags_has_no_key(self, ws):
        add_agent(ws, "dev1", "owner/repo", "/tmp/fake")
        agent = get_agent(ws, "dev1")
        assert "flags" not in agent

    def test_add_replaces_existing(self, ws):
        add_agent(ws, "dev1", "old/repo", "/tmp/old")
        add_agent(ws, "dev1", "new/repo", "/tmp/new")
        agents = load_agents(ws)
        assert len(agents) == 1
        assert agents[0]["repo"] == "new/repo"

    def test_remove_agent(self, ws):
        add_agent(ws, "dev1", "owner/repo", "/tmp/fake")
        add_agent(ws, "dev2", "other/repo", "/tmp/fake2")
        remove_agent(ws, "dev1")
        agents = load_agents(ws)
        assert len(agents) == 1
        assert agents[0]["name"] == "dev2"

    def test_remove_nonexistent(self, ws):
        remove_agent(ws, "nope")  # should not raise
        assert load_agents(ws) == []

    def test_get_agent(self, ws):
        add_agent(ws, "dev1", "owner/repo", "/tmp/fake")
        assert get_agent(ws, "dev1")["name"] == "dev1"
        assert get_agent(ws, "nope") is None

    def test_multiple_agents(self, ws):
        for i in range(5):
            add_agent(ws, f"agent-{i}", f"repo/{i}", f"/tmp/{i}")
        assert len(load_agents(ws)) == 5

    def test_add_agent_with_harness(self, ws):
        add_agent(ws, "dev1", "owner/repo", "/tmp/fake", harness="codex")
        agent = get_agent(ws, "dev1")
        assert agent["harness"] == "codex"

    def test_add_agent_default_has_no_harness_key(self, ws):
        add_agent(ws, "dev1", "owner/repo", "/tmp/fake")
        agent = get_agent(ws, "dev1")
        assert "harness" not in agent


class TestHeartbeats:
    def test_empty_by_default(self, ws):
        assert load_heartbeats(ws) == []

    def test_set_heartbeat(self, ws):
        set_heartbeat(ws, "all", 60, "check work")
        hbs = load_heartbeats(ws)
        assert len(hbs) == 1
        assert hbs[0]["agent"] == "all"
        assert hbs[0]["interval"] == 60
        assert hbs[0]["message"] == "check work"

    def test_set_replaces_existing(self, ws):
        set_heartbeat(ws, "dev1", 30, "old msg")
        set_heartbeat(ws, "dev1", 60, "new msg")
        hbs = load_heartbeats(ws)
        assert len(hbs) == 1
        assert hbs[0]["interval"] == 60

    def test_remove_heartbeat(self, ws):
        set_heartbeat(ws, "all", 60, "msg")
        set_heartbeat(ws, "dev1", 30, "msg")
        remove_heartbeat(ws, "all")
        hbs = load_heartbeats(ws)
        assert len(hbs) == 1
        assert hbs[0]["agent"] == "dev1"


class TestFindWorkspace:
    def test_finds_in_current_dir(self, ws):
        assert find_workspace(ws) == ws

    def test_finds_in_parent(self, ws):
        child = ws / "some" / "nested" / "dir"
        child.mkdir(parents=True)
        assert find_workspace(child) == ws

    def test_returns_none_when_missing(self, tmp_path):
        assert find_workspace(tmp_path) is None


class TestMigrateWorkspace:
    def _make_old_workspace(self, tmp_path):
        """Create a workspace as it would look before multi-harness support."""
        d = tmp_path / ".atmux"
        d.mkdir()
        (d / "status").mkdir()
        (d / "widgets").mkdir()
        # Old config: no version field
        (d / "config.json").write_text(json.dumps({"session": "atmux-old"}) + "\n")
        # Old agents: no harness field
        agents = [
            {"name": "dev1", "repo": "owner/repo", "dir": "/tmp/a"},
            {"name": "dev2", "repo": "other/repo", "dir": "/tmp/b", "flags": "--model sonnet"},
        ]
        (d / "agents.json").write_text(json.dumps(agents, indent=2) + "\n")
        return tmp_path

    def test_adds_harness_to_existing_agents(self, tmp_path):
        ws = self._make_old_workspace(tmp_path)
        migrate_workspace(ws)
        agents = load_agents(ws)
        assert all(a["harness"] == "claude" for a in agents)

    def test_preserves_existing_fields(self, tmp_path):
        ws = self._make_old_workspace(tmp_path)
        migrate_workspace(ws)
        agents = load_agents(ws)
        assert agents[0]["name"] == "dev1"
        assert agents[1]["flags"] == "--model sonnet"

    def test_stamps_version(self, tmp_path):
        ws = self._make_old_workspace(tmp_path)
        migrate_workspace(ws)
        cfg = load_config(ws)
        assert cfg["version"] == 1

    def test_idempotent(self, tmp_path):
        ws = self._make_old_workspace(tmp_path)
        migrate_workspace(ws)
        migrate_workspace(ws)  # should not error or double-modify
        agents = load_agents(ws)
        assert len(agents) == 2
        assert all(a["harness"] == "claude" for a in agents)

    def test_skips_already_migrated(self, ws):
        """New workspaces (version >= 1) should be skipped."""
        add_agent(ws, "dev1", "repo", "/tmp/a", harness="codex")
        migrate_workspace(ws)
        # Should NOT overwrite codex -> claude
        agent = get_agent(ws, "dev1")
        assert agent["harness"] == "codex"

    def test_no_agents_still_stamps_version(self, tmp_path):
        d = tmp_path / ".atmux"
        d.mkdir()
        (d / "config.json").write_text(json.dumps({"session": "atmux-empty"}) + "\n")
        (d / "agents.json").write_text("[]" + "\n")
        migrate_workspace(tmp_path)
        cfg = load_config(tmp_path)
        assert cfg["version"] == 1
