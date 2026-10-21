"""Exit when the parent process is gone.

In the desktop app the backend is a child process of Electron. **When the parent is force-killed we get no
notification at all** - `before-quit` only fires on the normal exit path; `SIGKILL`, crashes and "Force Quit"
in Activity Monitor all bypass it. That leaves a Python process holding sqlite and a port; on the next launch
it is still there - the port is random so nothing clashes, but that sqlite connection and the background
tasks are still alive, and the user sees an unkillable thing in Activity Monitor.

The approach is the plainest and most reliable one: watch `os.getppid()`. Once the parent dies, the child is
re-parented by the system to 1 (launchd/init) - this signal is deterministic and cross-platform, and does not
depend on any signal being delivered.

Enabled only when Electron explicitly asks for it (it passes MEMOKET_NOTE_PARENT_PID). A backend started by
hand with `uvicorn` is unaffected.
"""

from __future__ import annotations

import os
import threading
import time

CHECK_SECONDS = 2.0


def watch_parent(expected_ppid: int, *, on_orphan=None) -> threading.Thread | None:
    """Exit the whole process when the parent process changes. Returns the watchdog thread (for tests)."""
    if expected_ppid <= 1:
        return None

    def loop() -> None:
        while True:
            time.sleep(CHECK_SECONDS)
            if os.getppid() == expected_ppid:
                continue

            if on_orphan is not None:
                on_orphan()
                return

            # **Exit first, then talk.** This used to print first and then os._exit, and print
            # writes to exactly the pipe leading to the parent process - once the parent dies the
            # pipe breaks, print raises BrokenPipeError, the exception escapes the thread function,
            # the thread dies silently, and os._exit is never reached. That one log line killed the
            # watchdog in precisely the only scenario where the watchdog matters. Measured: after
            # force-killing Electron the backend lived on for 15+ seconds, while in the controlled
            # test (stdout is a terminal, the pipe does not break) everything was fine.
            try:
                print(f"[watchdog] parent process {expected_ppid} is gone, exiting too", flush=True)
            except Exception:      # noqa: BLE001  broken pipe, missing handle: neither matters
                pass
            os._exit(0)
            # In reality the line above never returns. **But it does when replaced** - tests swap
            # os._exit for a recording function, and without this return the thread would keep
            # spinning in while True; after the test ends and monkeypatch restores it, it would get
            # the real os._exit(0) and kill pytest entirely, exit code 0, output cut off mid-line.
            # Hit for real; the symptom was "the tests vanished halfway and still said success".
            return

    t = threading.Thread(target=loop, name="parent-watchdog", daemon=True)
    t.start()
    return t


def install_from_env(*, on_orphan=None) -> threading.Thread | None:
    raw = os.getenv("MEMOKET_NOTE_PARENT_PID", "")
    if not raw.isdigit():
        return None
    return watch_parent(int(raw), on_orphan=on_orphan)
