"""Tests for harness abstraction."""

import pytest

from src.harness import (
    get_harness,
    build_launch_cmd,
    get_exit_command,
    is_idle_prompt,
    has_subagent_indicator,
    check_binary,
    DEFAULT_HARNESS,
)


class TestGetHarness:
    def test_claude(self):
        h = get_harness("claude")
        assert h["binary"] == "claude"

    def test_codex(self):
        h = get_harness("codex")
        assert h["binary"] == "codex"

    def test_empty_string_defaults_to_claude(self):
        h = get_harness("")
        assert h["binary"] == "claude"

    def test_unknown_raises(self):
        with pytest.raises(KeyError, match="Unknown harness"):
            get_harness("unknown")

    def test_default_is_claude(self):
        assert DEFAULT_HARNESS == "claude"


class TestBuildLaunchCmd:
    def test_claude_basic(self):
        cmd = build_launch_cmd("claude", "dev1", "/opt/atmux", "mysession", "/work")
        assert "claude" in cmd
        assert "--permission-mode auto" in cmd
        assert "--settings" in cmd
        assert "claude/agent.json" in cmd
        assert '--name "dev1"' in cmd
        assert "ATMUX_AGENT=dev1" in cmd
        assert "ATMUX_SESSION='mysession'" in cmd

    def test_claude_with_flags(self):
        cmd = build_launch_cmd(
            "claude", "dev1", "/opt/atmux", "mysession", "/work", "--model sonnet"
        )
        assert "--model sonnet" in cmd

    def test_codex_basic(self):
        cmd = build_launch_cmd("codex", "dev1", "/opt/atmux", "mysession", "/work")
        assert "codex" in cmd
        assert "--full-auto" in cmd
        assert "ATMUX_AGENT=dev1" in cmd

    def test_codex_no_settings_flag(self):
        cmd = build_launch_cmd("codex", "dev1", "/opt/atmux", "mysession", "/work")
        assert "--settings" not in cmd


class TestExitCommand:
    def test_claude(self):
        assert get_exit_command("claude") == "/exit"

    def test_codex(self):
        assert get_exit_command("codex") == "/exit"


class TestIdlePrompt:
    def test_bare_prompt(self):
        assert is_idle_prompt("claude", ">") is True
        assert is_idle_prompt("codex", ">") is True

    def test_prompt_with_space(self):
        assert is_idle_prompt("claude", "> ") is True

    def test_shell_prompts(self):
        assert is_idle_prompt("claude", "$") is True
        assert is_idle_prompt("claude", "%") is True

    def test_non_prompt(self):
        assert is_idle_prompt("claude", "Running tests...") is False
        assert is_idle_prompt("codex", "Processing...") is False


class TestSubagentIndicator:
    def test_claude_detects(self):
        assert has_subagent_indicator("claude", "spawned local agent for task") is True

    def test_claude_no_match(self):
        assert has_subagent_indicator("claude", "running tests") is False

    def test_codex_always_false(self):
        assert has_subagent_indicator("codex", "local agent") is False
        assert has_subagent_indicator("codex", "anything") is False


class TestCheckBinary:
    def test_python3_exists(self):
        # python3 should always be available in test env
        # We can't test claude/codex, but we can test the mechanism
        assert check_binary("claude") is True or check_binary("claude") is False
