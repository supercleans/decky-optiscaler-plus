"""The plugin's own set-up and updates, one at a time, their steps read by the UI.

Setting the plugin up downloads OptiScaler's nightly, cyboman's builds and a
HelixSR release and builds HLX DLSS in it; an update does the same for one of
them. Each runs in the background as a list of steps the UI polls, so a closed
panel does not stop it and an opened one picks it up again.
"""

import copy
import threading
import time

PENDING, RUNNING, DONE, FAILED, SKIPPED = "pending", "running", "done", "failed", "skipped"


class Job:
    """The set-up or update under way, or the last one."""

    def __init__(self):
        self._lock = threading.Lock()
        self._state = {"running": False, "kind": None, "channel": None, "steps": [],
                       "error": None, "ok": None, "started_at": None, "finished_at": None}

    @property
    def running(self):
        return self._state["running"]

    def status(self):
        with self._lock:
            return copy.deepcopy(self._state)

    def begin(self, kind, steps, channel=None):
        """Start ``kind`` with ``steps`` [(key, label)]; False when one is running."""
        with self._lock:
            if self._state["running"]:
                return False
            self._state = {"running": True, "kind": kind, "channel": channel,
                           "steps": [{"key": key, "label": label, "state": PENDING, "detail": None}
                                     for key, label in steps],
                           "error": None, "ok": None, "started_at": time.time(), "finished_at": None}
            return True

    def step(self, key, state, detail=None):
        with self._lock:
            for step in self._state["steps"]:
                if step["key"] == key:
                    step["state"], step["detail"] = state, detail

    def finish(self, error=None):
        with self._lock:
            for step in self._state["steps"]:
                if step["state"] in (PENDING, RUNNING):
                    step["state"] = FAILED if step["state"] == RUNNING else SKIPPED
            self._state.update(running=False, ok=error is None, error=error, finished_at=time.time())
