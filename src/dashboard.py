"""Curses-based dashboard for atmux."""
import curses
import os
import subprocess
import time

from . import config
from .status import agent_summary
from .status import read_agent_status
from .workspace import (load_agents, load_config, add_agent, remove_agent,
                        load_heartbeats, set_heartbeat, remove_heartbeat)


def _is_local_path(repo: str) -> bool:
    return repo.startswith("/") or repo.startswith(".") or repo.startswith("~")


def _is_url(repo: str) -> bool:
    return repo.startswith("https://") or repo.startswith("http://") or \
           repo.startswith("git@") or repo.startswith("ssh://")


def _clone_repo(repo: str, dest: str) -> subprocess.CompletedProcess:
    """Clone a repo. Uses git clone for URLs, gh repo clone for owner/repo shorthand."""
    if _is_url(repo):
        return subprocess.run(
            ["git", "clone", "--quiet", repo, dest],
            capture_output=True, text=True,
        )
    else:
        return subprocess.run(
            ["gh", "repo", "clone", repo, dest, "--", "--quiet"],
            capture_output=True, text=True,
        )


# Color pair IDs
C_NORMAL = 0
C_IDLE = 1
C_BUSY = 2
C_ACTIVE = 3
C_HEADER = 4
C_DIM = 5
C_ALERT = 6


def init_colors():
    curses.start_color()
    curses.use_default_colors()
    curses.init_pair(C_IDLE, 245, -1)           # gray
    curses.init_pair(C_BUSY, 214, -1)           # yellow
    curses.init_pair(C_ACTIVE, 82, -1)          # bright green
    curses.init_pair(C_HEADER, 255, 236)        # white on dark gray
    curses.init_pair(C_DIM, 245, -1)            # gray
    curses.init_pair(C_ALERT, 196, -1)          # red


class Dashboard:
    def __init__(self, stdscr):
        self.stdscr = stdscr
        self.ws = config.WORKSPACE_DIR
        self.session = load_config(self.ws).get("session", "atmux")
        self.running = True
        self.command = ""
        self.message = ""
        self.message_time = 0
        # Seed with current time so first heartbeat waits a full interval
        agent_names = [a["name"] for a in load_agents(self.ws)]
        now = time.time()
        self._last_nudge: dict[str, float] = {n: now for n in agent_names}
        # Widget metadata from --setup: {name: {"script", "title", "interval"}}
        self._widget_meta: dict[str, dict] = {}
        # Widget output cache: {name: {"lines", "time", "duration"}}
        self._widget_cache: dict[str, dict] = {}
        # Pane poller: last check time
        self._last_pane_check = 0.0
        self._pane_check_interval = 15  # seconds

    def run(self):
        self.stdscr.timeout(100)
        curses.curs_set(0)
        init_colors()

        while self.running:
            self._draw()
            self._check_heartbeats()
            self._check_pane_status()
            # Drain all available keystrokes before redrawing
            while self._handle_input():
                pass

    def _check_heartbeats(self):
        """Send heartbeat messages to idle agents when interval elapses."""
        heartbeats = load_heartbeats(self.ws)
        if not heartbeats:
            return

        now = time.time()
        agents = load_agents(self.ws)
        agent_names = [a["name"] for a in agents]

        for hb in heartbeats:
            target = hb["agent"]
            interval = hb["interval"]
            msg = hb["message"]

            targets = agent_names if target == "all" else [target]

            for name in targets:
                if name not in agent_names:
                    continue
                last = self._last_nudge.get(name, 0)
                if now - last < interval:
                    continue
                status = read_agent_status(name)
                if status != "idle":
                    continue

                try:
                    subprocess.run(
                        ["tmux", "send-keys", "-t", f"{self.session}:{name}", "-l", msg],
                        capture_output=True, timeout=5,
                    )
                    subprocess.run(
                        ["tmux", "send-keys", "-t", f"{self.session}:{name}", "Enter"],
                        capture_output=True, timeout=5,
                    )
                    self._last_nudge[name] = now
                except Exception:
                    pass

    def _check_pane_status(self):
        """Safety net: detect stale busy status via pane content + file age.

        Only resets if the status file hasn't been updated recently AND
        the pane shows Claude's idle prompt. This avoids false positives
        when subagents are running (main agent shows > but is legitimately busy).
        """
        now = time.time()
        if now - self._last_pane_check < self._pane_check_interval:
            return
        self._last_pane_check = now

        sd = config.status_dir()
        agents = load_agents(self.ws)
        for agent_def in agents:
            name = agent_def["name"]
            status = read_agent_status(name)
            if status != "busy":
                continue

            # Only intervene if the status file is stale (no hook activity for 2+ minutes)
            status_file = sd / name
            try:
                age = now - status_file.stat().st_mtime
            except (FileNotFoundError, OSError):
                continue
            if age < 120:
                continue

            # Capture the last few lines of the pane
            try:
                r = subprocess.run(
                    ["tmux", "capture-pane", "-t", f"{self.session}:{name}", "-p", "-l", "5"],
                    capture_output=True, text=True, timeout=5,
                )
                if r.returncode != 0:
                    continue
                pane = r.stdout
            except Exception:
                continue

            lines = [l.strip() for l in pane.strip().split("\n") if l.strip()]
            if not lines:
                continue

            # Check if any line mentions active local agents — means subagents running
            pane_text = " ".join(lines)
            if "local agent" in pane_text:
                continue

            last = lines[-1]

            # Detect idle: Claude's input prompt or a bare shell prompt
            if last in (">", "$", "%") or last.startswith("> "):
                (sd / name).write_text("idle")
                (sd / f"{name}.subagents").write_text("0")
                subprocess.run(
                    ["tmux", "set-window-option", "-t", f"{self.session}:{name}",
                     "window-status-style", "fg=colour245"],
                    capture_output=True,
                )
                subprocess.run(
                    ["tmux", "set-window-option", "-t", f"{self.session}:{name}",
                     "window-status-current-style", "fg=colour235,bg=colour248,bold"],
                    capture_output=True,
                )

    def _draw(self):
        h, w = self.stdscr.getmaxyx()
        self.stdscr.erase()

        row = 0
        row = self._draw_header(row, w)
        row = self._draw_agents(row, w)
        row = self._draw_widgets(row, w)
        row = self._draw_nav(row, w)
        self._draw_command_bar(h, w)

        self.stdscr.noutrefresh()
        curses.doupdate()

    def _safe_addstr(self, row, col, text, attr=0):
        h, w = self.stdscr.getmaxyx()
        if row < 0 or row >= h:
            return
        max_len = w - col - 1
        if max_len <= 0:
            return
        try:
            self.stdscr.addnstr(row, col, text, max_len, attr)
        except curses.error:
            pass  # writing to bottom-right corner can raise

    # -- Header --

    def _draw_header(self, row, w):
        title = " atmux "
        self._safe_addstr(row, 0, title.center(w), curses.color_pair(C_HEADER) | curses.A_BOLD)
        row += 1
        self._safe_addstr(row, 0, f"  workspace: {self.ws}", curses.color_pair(C_DIM))
        row += 2
        return row

    # -- Agents --

    def _draw_agents(self, row, w):
        self._safe_addstr(row, 0, "\u2500" * w, curses.color_pair(C_DIM))
        row += 1
        self._safe_addstr(row, 2, "Agents", curses.A_BOLD)
        row += 1

        agents = load_agents(self.ws)
        if not agents:
            self._safe_addstr(row, 4, "No agents configured", curses.color_pair(C_DIM))
            row += 1
            self._safe_addstr(row, 4, "Use :add <name> <repo> to create one", curses.color_pair(C_DIM))
            row += 2
            return row

        for agent_def in agents:
            name = agent_def["name"]
            repo = agent_def.get("repo", "")
            info = agent_summary(name, repo)
            status = info["status"]
            subs = info["subagents"]

            if status == "busy":
                row_attr = curses.color_pair(C_BUSY)
            else:
                row_attr = curses.color_pair(C_DIM)

            # Indicator: ● busy, ○ idle, +N subagents
            if status == "busy":
                self._safe_addstr(row, 3, "\u25cf", curses.color_pair(C_BUSY) | curses.A_BOLD)
            elif status == "idle":
                self._safe_addstr(row, 3, "\u25cb", curses.color_pair(C_DIM))
            else:
                self._safe_addstr(row, 3, "?", curses.color_pair(C_DIM))

            if subs > 0:
                self._safe_addstr(row, 4, f"+{subs}", curses.color_pair(C_BUSY) | curses.A_BOLD)

            line = f" {name:<14} {repo}"
            self._safe_addstr(row, 7, line, row_attr)
            row += 1

        row += 1
        return row

    # -- Widgets --

    def _widget_env(self):
        return {**os.environ,
                "ATMUX_WORKSPACE": str(self.ws),
                "ATMUX_DIR": str(config.ATMUX_DIR)}

    def _widget_setup(self, script):
        """Run script --setup to get widget metadata. Returns dict with title, interval."""
        try:
            r = subprocess.run(
                [str(script), "--setup"],
                capture_output=True, text=True, timeout=5,
                cwd=str(self.ws), env=self._widget_env(),
            )
            if r.returncode == 0 and r.stdout.strip():
                import json
                return json.loads(r.stdout)
        except Exception:
            pass
        # Fallback: derive from filename
        name = script.stem
        return {"title": name.replace("-", " ").replace("_", " ")}

    def _init_widgets(self):
        """Discover widget scripts and run --setup on each."""
        widgets_dir = self.ws / ".atmux" / "widgets"
        if not widgets_dir.is_dir():
            return

        for script in sorted(widgets_dir.iterdir()):
            if not script.is_file() or not os.access(str(script), os.X_OK):
                continue
            name = script.stem
            if name in self._widget_meta:
                continue
            meta = self._widget_setup(script)
            self._widget_meta[name] = {
                "script": str(script),
                "title": meta.get("title", name),
                "interval": meta.get("interval", 10),
            }

    def _refresh_widgets(self):
        """Run widget scripts and cache their output."""
        self._init_widgets()
        if not self._widget_meta:
            return

        now = time.time()
        for name, meta in self._widget_meta.items():
            cached = self._widget_cache.get(name)
            interval = meta["interval"]

            # Dynamic adjustment: if last run was slow, back off
            if cached and cached.get("duration", 0) > 2:
                interval = max(interval, cached["duration"] * 3)

            if cached and now - cached["time"] < interval:
                continue

            start = time.time()
            try:
                r = subprocess.run(
                    [meta["script"]],
                    capture_output=True, text=True,
                    timeout=max(10, meta["interval"]),
                    cwd=str(self.ws), env=self._widget_env(),
                )
                duration = time.time() - start
                lines = r.stdout.rstrip("\n").split("\n") if r.stdout.strip() else []
                self._widget_cache[name] = {
                    "lines": lines,
                    "time": now,
                    "duration": duration,
                }
            except subprocess.TimeoutExpired:
                self._widget_cache[name] = {
                    "lines": ["(timed out)"],
                    "time": now,
                    "duration": time.time() - start,
                }
            except Exception:
                self._widget_cache[name] = {
                    "lines": ["(error)"],
                    "time": now,
                    "duration": 0,
                }

    def _draw_widgets(self, row, w):
        self._refresh_widgets()
        if not self._widget_cache:
            return row

        for name, meta in self._widget_meta.items():
            widget = self._widget_cache.get(name)
            if not widget or not widget["lines"]:
                continue
            self._safe_addstr(row, 0, "\u2500" * w, curses.color_pair(C_DIM))
            row += 1
            self._safe_addstr(row, 2, meta["title"], curses.A_BOLD)
            row += 1
            for line in widget["lines"]:
                self._safe_addstr(row, 4, line, curses.color_pair(C_DIM))
                row += 1
            row += 1

        return row

    # -- Navigation --

    def _draw_nav(self, row, w):
        self._safe_addstr(row, 0, "\u2500" * w, curses.color_pair(C_DIM))
        row += 1
        self._safe_addstr(row, 2, "Navigation", curses.A_BOLD)
        row += 1
        nav = [
            ("Ctrl-a n/p", "next/prev window"),
            ("Ctrl-a #", "select window by number"),
            ("Ctrl-a d", "detach"),
        ]
        for key, desc in nav:
            self._safe_addstr(row, 4, f"{key:<14} {desc}", curses.color_pair(C_DIM))
            row += 1
        row += 1

        self._safe_addstr(row, 2, "Commands", curses.A_BOLD)
        row += 1
        cmds = [
            ("add <name> <repo>", "Add a new Claude agent"),
            ("send <name> <msg>", "Send message to agent"),
            ("remove <name>", "Stop and remove agent"),
            ("heartbeat <a|all> <s> <msg>", "Nudge idle agents"),
            ("heartbeat stop <a|all>", "Stop heartbeat"),
            ("stop", "Stop everything and exit"),
        ]
        for cmd, desc in cmds:
            self._safe_addstr(row, 4, f"{cmd:<30} {desc}", curses.color_pair(C_DIM))
            row += 1

        # Show active heartbeats
        hbs = load_heartbeats(self.ws)
        if hbs:
            row += 1
            self._safe_addstr(row, 2, "Heartbeats", curses.A_BOLD)
            row += 1
            for hb in hbs:
                line = f"{hb['agent']:<14} every {hb['interval']}s: {hb['message']}"
                self._safe_addstr(row, 4, line, curses.color_pair(C_DIM))
                row += 1

        row += 1
        return row

    # -- Command bar --

    def _draw_command_bar(self, h, w):
        # Layout from bottom:
        #   h-4: message (if any)
        #   h-3: ─────────────────
        #   h-2: ❯ command text
        #   h-1: ─────────────────
        top_line = h - 3
        input_row = h - 2
        bot_line = h - 1

        if self.message and time.time() - self.message_time < 3:
            self._safe_addstr(top_line - 1, 2, self.message, curses.color_pair(C_ACTIVE))

        self._safe_addstr(top_line, 0, "\u2500" * w, curses.color_pair(C_DIM))

        prompt = " \u276f "
        self._safe_addstr(input_row, 0, prompt + self.command, curses.A_BOLD)

        self._safe_addstr(bot_line, 0, "\u2500" * w, curses.color_pair(C_DIM))

        # Show cursor at end of command input
        cursor_col = len(prompt) + len(self.command)
        if cursor_col < w:
            try:
                self.stdscr.move(input_row, cursor_col)
                curses.curs_set(1)
            except curses.error:
                pass

    # -- Input --

    def _handle_input(self) -> bool:
        """Process one keystroke. Returns True if a key was handled."""
        try:
            ch = self.stdscr.getch()
        except curses.error:
            return False

        if ch == -1:
            return False
        elif ch == ord("\n"):
            if self.command:
                self._exec_command(self.command)
                self.command = ""
        elif ch in (curses.KEY_BACKSPACE, 127, 8):
            self.command = self.command[:-1]
        elif ch == 27:  # ESC
            self.command = ""
        elif 32 <= ch <= 126:
            self.command += chr(ch)
        return True

    def _exec_command(self, cmd):
        cmd = cmd.strip()
        if cmd.startswith("add "):
            self._cmd_add(cmd[4:])
        elif cmd.startswith("send "):
            self._cmd_send(cmd[5:])
        elif cmd.startswith("remove "):
            self._cmd_remove(cmd[7:].strip())
        elif cmd.startswith("heartbeat "):
            self._cmd_heartbeat(cmd[10:])
        elif cmd == "stop":
            self._cmd_stop()
        elif cmd in ("quit", "q"):
            self.running = False
        elif cmd == "help":
            self._show_message("add | send | remove | heartbeat | stop | quit")
        else:
            self._show_message(f"Unknown: {cmd}. Type 'help' for commands.")

    def _show_message(self, msg):
        self.message = msg
        self.message_time = time.time()

    def _cmd_add(self, args):
        # Split on -- to extract extra claude flags
        flags = ""
        if " -- " in args:
            args, flags = args.split(" -- ", 1)

        parts = args.strip().split(None, 1)
        if len(parts) < 2:
            self._show_message("Usage: add <name> <repo> [-- flags]")
            return

        name, repo = parts

        # Check if already exists
        existing = load_agents(self.ws)
        if any(a["name"] == name for a in existing):
            self._show_message(f"Agent '{name}' already exists")
            return

        # Determine working directory
        if _is_local_path(repo):
            work_dir = os.path.expanduser(repo)
            if not os.path.isabs(work_dir):
                work_dir = os.path.join(str(self.ws), work_dir)
            work_dir = os.path.realpath(work_dir)
            if not os.path.isdir(work_dir):
                self._show_message(f"Directory not found: {work_dir}")
                return
            repo_display = repo
        else:
            work_dir = os.path.join(str(self.ws), "agents", name)

            # Drop out of curses to show clone progress
            curses.endwin()
            print(f"\n  Cloning {repo} into agents/{name}/...")
            os.makedirs(work_dir, exist_ok=True)
            r = _clone_repo(repo, work_dir)
            if r.returncode != 0:
                if not os.path.isdir(os.path.join(work_dir, ".git")):
                    print(f"  Clone failed: {r.stderr.strip()}")
                    input("  Press Enter to continue...")
                    self.stdscr.refresh()
                    return
                else:
                    print("  Already cloned.")
            else:
                print("  Done.")
            self.stdscr.refresh()
            repo_display = repo

        # Persist agent
        add_agent(self.ws, name, repo_display, work_dir, flags=flags)

        # Launch in tmux
        self._launch_agent(name, work_dir, flags=flags)
        self._show_message(f"Added agent '{name}' -> {repo_display}")

    def _launch_agent(self, name, work_dir, flags=""):
        atmux_dir = str(config.ATMUX_DIR)
        ws = str(self.ws)

        subprocess.run(
            ["tmux", "new-window", "-t", self.session, "-n", name, "-c", work_dir],
            capture_output=True,
        )

        # Init status
        sd = config.status_dir()
        sd.mkdir(parents=True, exist_ok=True)
        (sd / name).write_text("idle")
        (sd / f"{name}.subagents").write_text("0")

        # Export env vars and launch claude in a single command so env is guaranteed set
        settings_path = config.SETTINGS_DIR / "agent.json"
        extra = f" {flags}" if flags else ""
        launch_cmd = (
            f"export ATMUX_AGENT={name} ATMUX_SESSION='{self.session}' ATMUX_DIR='{atmux_dir}' ATMUX_WORKSPACE='{ws}' && "
            f"claude --permission-mode auto --settings '{settings_path}' --name \"{name}\"{extra}"
        )
        subprocess.run(
            ["tmux", "send-keys", "-t", f"{self.session}:{name}", launch_cmd, "Enter"],
            capture_output=True,
        )

    def _cmd_send(self, args):
        parts = args.split(" ", 1)
        if len(parts) < 2:
            self._show_message("Usage: send <agent> <message>")
            return
        agent, msg = parts
        try:
            subprocess.run(
                ["tmux", "send-keys", "-t", f"{self.session}:{agent}", msg, "Enter"],
                capture_output=True, timeout=5,
            )
            self._show_message(f"Sent to {agent}")
        except Exception as e:
            self._show_message(f"Failed: {e}")

    def _cmd_remove(self, name):
        if not name:
            self._show_message("Usage: remove <name>")
            return

        # Send /exit to claude
        subprocess.run(
            ["tmux", "send-keys", "-t", f"{self.session}:{name}", "/exit", "Enter"],
            capture_output=True,
        )
        time.sleep(1)
        subprocess.run(
            ["tmux", "kill-window", "-t", f"{self.session}:{name}"],
            capture_output=True,
        )

        # Remove from persisted state
        remove_agent(self.ws, name)

        # Clean status
        sd = config.status_dir()
        for suffix in ["", ".subagents", ".repo"]:
            path = sd / f"{name}{suffix}"
            if path.exists():
                path.unlink()

        self._show_message(f"Removed agent '{name}'")

    def _cmd_heartbeat(self, args):
        """heartbeat <agent|all> <seconds> <message>  or  heartbeat stop <agent|all>  or  heartbeat list"""
        parts = args.strip().split(None, 2)
        if not parts:
            self._show_message("heartbeat <agent|all> <secs> <msg> | heartbeat stop <agent|all> | heartbeat list")
            return

        if parts[0] == "list":
            hbs = load_heartbeats(self.ws)
            if not hbs:
                self._show_message("No heartbeats configured")
            else:
                summary = ", ".join(f"{h['agent']} {h['interval']}s" for h in hbs)
                self._show_message(summary)
            return

        if parts[0] == "stop":
            target = parts[1] if len(parts) > 1 else "all"
            remove_heartbeat(self.ws, target)
            self._show_message(f"Heartbeat stopped for {target}")
            return

        if len(parts) < 3:
            self._show_message("heartbeat <agent|all> <seconds> <message>")
            return

        agent = parts[0]
        try:
            interval = int(parts[1])
        except ValueError:
            self._show_message("Interval must be a number (seconds)")
            return
        msg = parts[2]

        set_heartbeat(self.ws, agent, interval, msg)
        self._show_message(f"Heartbeat set: {agent} every {interval}s")

    def _cmd_stop(self):
        stop_script = config.ATMUX_DIR / "stop"
        if stop_script.exists():
            subprocess.run(
                [str(stop_script)],
                capture_output=True, timeout=30,
                env={**os.environ, "ATMUX_WORKSPACE": str(self.ws)},
            )
        self.running = False


def main(stdscr):
    Dashboard(stdscr).run()


def run():
    curses.wrapper(main)


if __name__ == "__main__":
    run()
