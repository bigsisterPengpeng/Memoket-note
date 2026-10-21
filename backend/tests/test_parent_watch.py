"""When the parent process is gone, the backend must exit too.

This comes from a real test: after `pkill`-ing Electron, the uvicorn it started **survived** -
`before-quit` only fires on the normal exit path; force kills, crashes and "Force Quit" in Activity Monitor
all bypass it. The leftover process holds sqlite and a port, and the user sees an unknown Python in Activity Monitor.
"""

from __future__ import annotations

import os
import threading
import time

from app.util import parent_watch


def test_does_nothing_while_parent_unchanged(monkeypatch):
    fired = threading.Event()
    monkeypatch.setattr(parent_watch, "CHECK_SECONDS", 0.01)
    monkeypatch.setattr(os, "getppid", lambda: 4242)
    parent_watch.watch_parent(4242, on_orphan=fired.set)
    assert not fired.wait(0.15), "the parent is still there, must not exit"


def test_exits_when_parent_changes(monkeypatch):
    fired = threading.Event()
    monkeypatch.setattr(parent_watch, "CHECK_SECONDS", 0.01)
    # once the parent dies, the child is re-parented by the system to 1 - that is the signal
    monkeypatch.setattr(os, "getppid", lambda: 1)
    parent_watch.watch_parent(4242, on_orphan=fired.set)
    assert fired.wait(1.0), "the parent is gone but it did not exit"


def test_no_watchdog_without_parent_pid(monkeypatch):
    monkeypatch.delenv("MEMOKET_NOTE_PARENT_PID", raising=False)
    assert parent_watch.install_from_env() is None


def test_not_installed_when_parent_pid_is_1(monkeypatch):
    """Already an orphan (or no parent at all): installing it would only kill itself immediately."""
    monkeypatch.setenv("MEMOKET_NOTE_PARENT_PID", "1")
    assert parent_watch.install_from_env() is None


def test_watchdog_is_daemon_thread_not_blocking_exit(monkeypatch):
    monkeypatch.setattr(parent_watch, "CHECK_SECONDS", 10.0)
    monkeypatch.setattr(os, "getppid", lambda: 4242)
    t = parent_watch.watch_parent(4242, on_orphan=lambda: None)
    assert t is not None and t.daemon, "a non-daemon thread would keep the process from exiting cleanly"
    _ = time


def test_exits_even_when_stdout_is_broken(monkeypatch):
    """**This one is a real bug, reproduced.**

    The watchdog used to print first and then os._exit, and its stdout is the pipe to the parent process.
    Once the parent dies the pipe breaks, print raises BrokenPipeError, the exception escapes the thread function,
    the thread dies silently, and os._exit is never reached - that log line killed the watchdog in precisely the
    only scenario where it matters.

    Measured: after force-killing Electron the backend lived on for 15+ seconds; in the controlled experiment
    stdout was a terminal and the pipe did not break, so everything was fine - **a test environment more
    forgiving than the real one is where this kind of bug hides.**
    """
    import builtins

    exited: list[int] = []
    monkeypatch.setattr(parent_watch, "CHECK_SECONDS", 0.01)
    monkeypatch.setattr(os, "getppid", lambda: 1)
    monkeypatch.setattr(os, "_exit", lambda code: exited.append(code))

    def boom(*a, **kw):
        raise BrokenPipeError("pipe broken")

    monkeypatch.setattr(builtins, "print", boom)
    t = parent_watch.watch_parent(4242)      # no on_orphan passed: take the real exit path
    assert t is not None
    for _ in range(100):
        if exited:
            break
        time.sleep(0.01)
    assert exited == [0], "with stdout broken it can no longer exit"
    # **The thread must end by itself.** Otherwise it outlives this test: after monkeypatch restores
    # things it gets the real os._exit(0) and kills the whole pytest - exit code 0, output cut off
    # mid-line, looking like "finished". Hit for real.
    t.join(timeout=2)
    assert not t.is_alive(), "the watchdog thread did not exit and would fire during later tests"
