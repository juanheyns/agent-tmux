"""Tests for agent status reading."""
import pytest

from src import config
from src.status import read_agent_status, read_subagent_count, agent_summary
from src.workspace import init_workspace


@pytest.fixture
def ws(tmp_path):
    init_workspace(tmp_path)
    config.set_workspace(tmp_path)
    return tmp_path


class TestReadStatus:
    def test_missing_file_returns_question(self, ws):
        assert read_agent_status("nonexistent") == "?"

    def test_reads_idle(self, ws):
        (config.status_dir() / "dev1").write_text("idle")
        assert read_agent_status("dev1") == "idle"

    def test_reads_busy(self, ws):
        (config.status_dir() / "dev1").write_text("busy")
        assert read_agent_status("dev1") == "busy"

    def test_strips_whitespace(self, ws):
        (config.status_dir() / "dev1").write_text("  idle  \n")
        assert read_agent_status("dev1") == "idle"


class TestSubagentCount:
    def test_missing_file_returns_zero(self, ws):
        assert read_subagent_count("nonexistent") == 0

    def test_reads_count(self, ws):
        (config.status_dir() / "dev1.subagents").write_text("3")
        assert read_subagent_count("dev1") == 3

    def test_negative_returns_zero(self, ws):
        (config.status_dir() / "dev1.subagents").write_text("-1")
        assert read_subagent_count("dev1") == 0

    def test_invalid_returns_zero(self, ws):
        (config.status_dir() / "dev1.subagents").write_text("garbage")
        assert read_subagent_count("dev1") == 0


class TestAgentSummary:
    def test_summary(self, ws):
        (config.status_dir() / "dev1").write_text("busy")
        (config.status_dir() / "dev1.subagents").write_text("2")
        s = agent_summary("dev1", "owner/repo")
        assert s == {
            "name": "dev1",
            "status": "busy",
            "subagents": 2,
            "repo": "owner/repo",
        }
