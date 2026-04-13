"""Entry point: python3 -m src <command> [args]"""
import sys
from pathlib import Path


def main():
    if len(sys.argv) < 2:
        print("Usage: python3 -m src <dashboard> [workspace_path]", file=sys.stderr)
        sys.exit(1)

    cmd = sys.argv[1]
    if cmd == "dashboard":
        # Optional workspace path argument
        if len(sys.argv) >= 3:
            from . import config
            config.set_workspace(Path(sys.argv[2]))
        from .dashboard import run
        run()
    else:
        print(f"Unknown command: {cmd}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
