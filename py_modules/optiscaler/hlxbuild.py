"""HLX DLSS built on this Deck by HelixSR's own setup, for when HelixSR Desktop has not.

HLX DLSS is NVIDIA's DLSS network rebuilt from NVIDIA's DLL on the user's own
machine; the result is NVIDIA's and may not be shared, so it can only be made
here. HelixSR's setup does that, and this runs it as it comes in the release
(unmodified, as its licence asks) in the release folder hlx.py unpacked:

    bash helixsr-setup.sh --no-fg --dlss <nvngx_dlss.dll>   (stdin closed)

Its three questions are answered without anyone there: the one about
installing Python with the package manager reads "no" from the closed input
(SteamOS is read-only anyway, and the setup downloads a portable Python
instead); the one about downloading NVIDIA's DLL is never asked, because the
DLL comes with --dlss, downloaded here from the URL and checked against the
SHA-256 the setup itself names, after the user agreed to NVIDIA's licence in
the UI; and the games step that ends the setup reads the end of its input and
changes nothing. --yes is not passed: it would have that last step update
every game HelixSR is in.

The setup keeps what it downloads (portable Python, Microsoft's shader
compiler) in ~/.local/share/HelixSR, where HelixSR Desktop keeps them too, and
writes the network into HelixSR/helixsr.dll, which helixsr.find then reports
built.
"""

import os
import re
import shutil
import signal
import subprocess
import threading
import time
from collections import deque
from pathlib import Path

from . import helixsr, wiki
from .constants import (
    HELIXSR_DIR,
    HELIXSR_DLL,
    HELIXSR_SETUP,
    HELIXSR_SETUP_ARGS,
    HELIXSR_SETUP_PY,
    HELIXSR_WINE_SEARCH,
)
from .payload import sha256

SOURCE_RE = {key: re.compile(rf"^{key}\s*=\s*'([^']+)'", re.M)
             for key in ("DLSS_URL", "DLSS_SHA256", "DLSS_LICENSE")}
# [helixsr-setup] [#########-----------]   45%  3:12  shaders
PERCENT_RE = re.compile(r"\]\s+(\d+)%")
PREFIX = "[helixsr-setup] "
LOG_LINES = 40


def dlss_source(release_dir):
    """NVIDIA's DLL the setup is verified with: {url, sha256, license}, as it names them."""
    text = (Path(release_dir) / HELIXSR_SETUP_PY).read_text(encoding="utf-8", errors="replace")
    found = {key: pattern.search(text) for key, pattern in SOURCE_RE.items()}
    if not found["DLSS_URL"] or not found["DLSS_SHA256"]:
        raise ValueError(f"{HELIXSR_SETUP_PY} does not name NVIDIA's DLL")
    return {"url": found["DLSS_URL"].group(1), "sha256": found["DLSS_SHA256"].group(1).lower(),
            "license": found["DLSS_LICENSE"].group(1) if found["DLSS_LICENSE"] else None}


def find_wine(home):
    """The Wine the setup will run the shader compiler with, or None."""
    for pattern in HELIXSR_WINE_SEARCH:
        for path in sorted(Path(home).glob(pattern)):
            if os.access(path, os.X_OK):
                return path
    found = shutil.which("wine")
    return Path(found) if found else None


def environment(home):
    """The setup's environment: the user's home, and the system's libraries.

    Decky runs plugins from its own bundled Python, whose LD_LIBRARY_PATH would
    otherwise reach curl, tar and Wine in the setup and break them.
    """
    env = dict(os.environ)
    original = env.pop("LD_LIBRARY_PATH_ORIG", None)
    env.pop("LD_LIBRARY_PATH", None)
    if original:
        env["LD_LIBRARY_PATH"] = original
    env["HOME"] = str(home)
    env["XDG_DATA_HOME"] = str(Path(home) / ".local" / "share")
    return env


def setup_command(release_dir, dll):
    """The setup, as the user would run it, with NVIDIA's DLL given."""
    return ["bash", str(Path(release_dir) / HELIXSR_SETUP), *HELIXSR_SETUP_ARGS, "--dlss", str(dll)]


class Build:
    """The one HLX DLSS build at a time, run in a worker thread, read by the UI."""

    def __init__(self):
        self._lock = threading.Lock()
        self._process = None
        self._cancelled = False
        self._state = {"running": False, "step": None, "percent": None, "log": [],
                       "error": None, "ok": None, "tag": None,
                       "started_at": None, "finished_at": None}
        self._log = deque(maxlen=LOG_LINES)

    @property
    def running(self):
        return self._state["running"]

    def status(self):
        with self._lock:
            return {**self._state, "log": list(self._log)}

    def begin(self):
        """Mark a build started; False when one is running already."""
        with self._lock:
            if self._state["running"]:
                return False
            self._cancelled = False
            self._log.clear()
            self._state.update(running=True, step="준비 중", percent=None, error=None, ok=None,
                               tag=None, started_at=time.time(), finished_at=None)
            return True

    def say(self, step, tag=None):
        with self._lock:
            self._state["step"] = step
            if tag:
                self._state["tag"] = tag

    def finish(self, error=None):
        with self._lock:
            if self._cancelled and error:
                error = "빌드를 취소했습니다."
            self._state.update(running=False, ok=error is None, error=error, finished_at=time.time(),
                               percent=100 if error is None else self._state["percent"])
            self._process = None

    def cancel(self):
        """Stop the setup and everything it started (Wine, the compiler)."""
        with self._lock:
            if not self._state["running"]:
                return False
            self._cancelled = True
            process = self._process
        if process and process.poll() is None:
            try:
                if hasattr(os, "killpg"):
                    os.killpg(process.pid, signal.SIGTERM)
                else:
                    process.terminate()
            except OSError:
                pass
        return True

    def _check_cancelled(self):
        if self._cancelled:
            raise RuntimeError("빌드를 취소했습니다.")

    def _line(self, line, logger):
        line = line.rstrip()
        if not line:
            return
        if logger:
            logger.info("helixsr-setup: %s", line)
        with self._lock:
            self._log.append(line)
            percent = PERCENT_RE.search(line)
            if percent:
                self._state["percent"] = int(percent.group(1))
            elif line.startswith(PREFIX):
                self._state["step"] = line[len(PREFIX):]

    def run(self, release_dir, home, logger=None):
        """Build HLX DLSS in ``release_dir``; raise with the reason when it is not built."""
        release_dir = Path(release_dir)
        if not find_wine(home):
            raise RuntimeError("Proton을 찾지 못했습니다. HelixSR 설정은 Proton(또는 Wine)으로 셰이더 "
                               "컴파일러를 실행합니다. Steam에서 Proton을 설치한 뒤 다시 시도하세요.")
        source = dlss_source(release_dir)
        dll = release_dir.parent / f"{release_dir.name}.nvngx_dlss.dll"
        try:
            self.say("NVIDIA DLSS DLL 받는 중")
            if logger:
                logger.info("downloading %s for HLX DLSS", source["url"])
            wiki.download(source["url"], dll, timeout=300)
            if sha256(dll) != source["sha256"]:
                raise ValueError("받은 nvngx_dlss.dll이 HelixSR 설정이 요구하는 파일과 다릅니다.")
            self._check_cancelled()
            self.say("HelixSR 설정 실행 중")
            with self._lock:
                self._process = subprocess.Popen(
                    setup_command(release_dir, dll), cwd=str(release_dir), env=environment(home),
                    stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                    text=True, errors="replace", bufsize=1, start_new_session=True)
                process = self._process
            for line in process.stdout:
                self._line(line, logger)
            code = process.wait()
            self._check_cancelled()
        finally:
            dll.unlink(missing_ok=True)
        # Built is what counts: the games step after the build can fail on a
        # game folder it reads without the network being any less there.
        if not helixsr.network_built(release_dir / HELIXSR_DIR / HELIXSR_DLL):
            last = next((line for line in reversed(self._log) if line.strip()), "")
            raise RuntimeError(f"HelixSR 설정이 HLX DLSS를 빌드하지 못했습니다 (exit {code}). {last}".strip())
