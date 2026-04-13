# atmux

Run multiple Claude Code agents in a single tmux session. Add agents, point them at repos, and monitor everything from a live dashboard.

## Install

```bash
brew install juanheyns/tmux/atmux
```

Or manually:

```bash
git clone https://github.com/juanheyns/agent-tmux.git
cd agent-tmux
./install.sh
```

### Requirements

- [tmux](https://github.com/tmux/tmux)
- [Claude Code](https://claude.ai/code) (`claude` CLI)
- Python 3.10+
- [gh CLI](https://cli.github.com) (optional, for `owner/repo` cloning)

## Quick start

```bash
# Initialize a workspace
cd ~/projects/my-workspace
atmux init

# Add agents — GitHub repos, URLs, or local paths
atmux add backend owner/api-service
atmux add frontend https://gh.corp.com/team/ui.git
atmux add infra ./terraform

# Launch
atmux start
```

Agents persist across sessions — `atmux stop` then `atmux start` restores everything.

## Dashboard

The overview window shows real-time agent status:

- `●` busy (yellow tab) / `○` idle (gray tab)
- `+N` subagent count
- Widget sections from custom scripts

### Dashboard commands

```
:add <name> <repo>                   Add agent
:send <name> <msg>                   Send message to agent
:remove <name>                       Remove agent
:heartbeat <name|all> <secs> <msg>   Nudge idle agents periodically
:heartbeat stop <name|all>           Stop heartbeat
:stop                                Stop everything
```

### tmux navigation

```
Ctrl-a n/p    Next/previous window
Ctrl-a w      Window picker
Ctrl-a d      Detach (agents keep running)
```

## CLI

```
atmux init                              Initialize workspace
atmux start                             Launch session
atmux stop                              Stop all agents
atmux add <name> <repo> [-- flags]      Add agent (extra claude flags after --)
atmux remove <name>                     Remove agent
atmux send <name> <msg>                 Send message
atmux list                              List agents
atmux heartbeat <name|all> <s> <msg>    Set heartbeat
atmux heartbeat stop <name|all>         Stop heartbeat
atmux heartbeat list                    List heartbeats
```

### Custom Claude flags

```bash
atmux add dev1 owner/repo -- --model sonnet --max-turns 50
```

Flags are persisted and restored on `atmux start`.

## Widgets

Extend the dashboard with executable scripts in `.atmux/widgets/`:

```bash
#!/usr/bin/env bash
# .atmux/widgets/git-status
if [[ "$1" == "--setup" ]]; then
  echo '{"title": "Git Status", "interval": 15}'
  exit 0
fi

for dir in "$ATMUX_WORKSPACE"/agents/*/; do
  name=$(basename "$dir")
  branch=$(git -C "$dir" branch --show-current 2>/dev/null)
  echo "$name: $branch"
done
```

### Widget protocol

- `--setup` — Return JSON with `title` and `interval` (seconds). Optional.
- Normal run — stdout lines become dashboard rows.
- Environment — `ATMUX_WORKSPACE` and `ATMUX_DIR` are available.
- Slow scripts (>2s) are automatically backed off.

## Workspace layout

```
.atmux/
  config.json       # Session name
  agents.json       # Agent registry (persisted)
  heartbeats.json   # Heartbeat configs (persisted)
  status/           # Runtime state (ephemeral)
  widgets/          # Dashboard widget scripts
agents/
  backend/          # Cloned repos
  frontend/
```

## Debugging

```bash
export ATMUX_DEBUG=1
atmux start
tail -f .atmux/status/hooks.log
```

## License

MIT
