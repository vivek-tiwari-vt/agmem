"""
agmem daemon - Auto-sync daemon for automatic commits.
"""

import argparse
import os
import sys
import time
import signal
from pathlib import Path

from ..commands.base import require_repo


class DaemonCommand:
    """Control the auto-sync daemon."""

    name = "daemon"
    help = "Start/stop the auto-sync daemon for automatic commits"

    @staticmethod
    def add_arguments(parser: argparse.ArgumentParser):
        parser.add_argument(
            "action",
            choices=["start", "stop", "status", "run"],
            help="Daemon action: start, stop, status, or run (foreground)",
        )
        parser.add_argument(
            "--debounce",
            type=int,
            default=30,
            help="Seconds to wait after changes before committing (default: 30)",
        )
        parser.add_argument("--pidfile", help="PID file path (default: .mem/daemon.pid)")
        parser.add_argument(
            "--distill", action="store_true", help="Run distillation pipeline nightly (with daemon)"
        )

    @staticmethod
    def execute(args) -> int:
        repo, code = require_repo()
        if code != 0:
            return code

        if args.pidfile:
            pid_file = Path(args.pidfile).resolve()
            try:
                pid_file.relative_to(repo.root.resolve())
            except ValueError:
                print("Error: --pidfile must be under repository root")
                return 1
        else:
            pid_file = repo.root / ".mem" / "daemon.pid"

        if args.action == "start":
            return DaemonCommand._start(repo, pid_file, args.debounce, args.distill)
        elif args.action == "stop":
            return DaemonCommand._stop(pid_file)
        elif args.action == "status":
            return DaemonCommand._status(pid_file)
        elif args.action == "run":
            return DaemonCommand._run(repo, args.debounce, pid_file=pid_file, distill=args.distill)

        return 1

    @staticmethod
    def _start(repo, pid_file: Path, debounce: int, distill: bool = False) -> int:
        """Start daemon in background."""
        # Check if already running
        if pid_file.exists():
            pid = int(pid_file.read_text().strip())
            try:
                os.kill(pid, 0)
                print(f"Daemon already running (PID: {pid})")
                return 1
            except OSError:
                pid_file.unlink()

        # Fork to background (Unix only)
        if os.name != "posix":
            print("Background daemon not supported on this platform.")
            print("Use 'agmem daemon run' to run in foreground.")
            return 1

        # First fork
        try:
            pid = os.fork()
            if pid > 0:
                # Parent exits
                print(f"Daemon started (PID: {pid})")
                return 0
        except OSError as e:
            print(f"Fork failed: {e}")
            return 1

        # Decouple from parent
        os.setsid()
        os.umask(0)

        # Second fork
        try:
            pid = os.fork()
            if pid > 0:
                sys.exit(0)
        except OSError:
            sys.exit(1)

        # Write PID file
        pid_file.write_text(str(os.getpid()))

        # Redirect stdio
        sys.stdout.flush()
        sys.stderr.flush()

        # Run daemon in background
        return DaemonCommand._run(repo, debounce, pid_file, distill)

    @staticmethod
    def _stop(pid_file: Path) -> int:
        """Stop running daemon."""
        if not pid_file.exists():
            print("No daemon running")
            return 0

        pid = int(pid_file.read_text().strip())

        try:
            os.kill(pid, signal.SIGTERM)
            print(f"Stopped daemon (PID: {pid})")
            pid_file.unlink()
            return 0
        except OSError as e:
            print(f"Could not stop daemon: {e}")
            pid_file.unlink()
            return 1

    @staticmethod
    def _status(pid_file: Path) -> int:
        """Show daemon status."""
        if not pid_file.exists():
            print("Daemon is not running")
            return 0

        pid = int(pid_file.read_text().strip())

        try:
            os.kill(pid, 0)
            print(f"Daemon is running (PID: {pid})")
            return 0
        except OSError:
            print("Daemon is not running (stale PID file)")
            pid_file.unlink()
            return 0

    @staticmethod
    def _run(repo, debounce: int, pid_file: Path = None, distill: bool = False) -> int:
        """Run daemon in foreground."""
        try:
            from watchdog.observers import Observer
            from watchdog.events import FileSystemEventHandler
        except ImportError:
            print("Daemon requires watchdog. Install with: pip install agmem[daemon]")
            return 1

        current_dir = repo.root / "current"

        if not current_dir.exists():
            print("No current/ directory to watch")
            return 1

        class MemoryFileHandler(FileSystemEventHandler):
            def __init__(self):
                self.last_change = 0
                self.pending = False

            def on_any_event(self, event):
                # Ignore .mem and hidden files
                if ".mem" in event.src_path or "/." in event.src_path:
                    return

                # Ignore directories
                if event.is_directory:
                    return

                self.last_change = time.time()
                self.pending = True

        handler = MemoryFileHandler()
        observer = Observer()
        observer.schedule(handler, str(current_dir), recursive=True)
        observer.start()

        print(f"Watching {current_dir} (debounce: {debounce}s)")
        print("Press Ctrl+C to stop")

        # Handle signals
        running = True

        def signal_handler(signum, frame):
            nonlocal running
            running = False

        signal.signal(signal.SIGTERM, signal_handler)
        signal.signal(signal.SIGINT, signal_handler)

        try:
            while running:
                time.sleep(1)

                if handler.pending:
                    elapsed = time.time() - handler.last_change
                    if elapsed >= debounce:
                        # Auto-commit
                        DaemonCommand._auto_commit(repo)
                        if distill:
                            try:
                                from ..core.distiller import Distiller, DistillerConfig

                                d = Distiller(repo, DistillerConfig(create_safety_branch=False))
                                d.run()
                            except Exception:
                                pass
                        handler.pending = False
        finally:
            observer.stop()
            observer.join()

            if pid_file and pid_file.exists():
                pid_file.unlink()

        print("Daemon stopped")
        return 0

    @staticmethod
    def _auto_commit(repo):
        """Perform automatic commit."""
        from datetime import datetime

        try:
            # Check for changes
            status = repo.get_status()

            if not status.get("modified") and not status.get("untracked"):
                return

            # Stage all changes in current/ (validate path stays under current/)
            current_dir = repo.root / "current"
            for memory_file in current_dir.glob("**/*"):
                if memory_file.is_file() and ".mem" not in str(memory_file):
                    try:
                        rel_path = memory_file.relative_to(current_dir)
                    except ValueError:
                        continue
                    rel_str = str(rel_path)
                    if repo._path_under_current_dir(rel_str) is None:
                        continue
                    try:
                        repo.stage_file(rel_str)
                    except Exception:
                        pass

            # Commit
            timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
            repo.commit(f"auto: update memory state ({timestamp})", {"auto_commit": True})

            print(f"[{timestamp}] Auto-committed changes")

        except Exception as e:
            # Write conflict lock if there's an issue
            conflict_file = repo.root / ".mem" / "CONFLICT.lock"
            conflict_file.write_text(f"Auto-commit failed: {e}")
            print(f"Warning: Auto-commit failed, wrote CONFLICT.lock: {e}")
