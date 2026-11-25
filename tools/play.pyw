"""Portable Windows entry point with a startup log for the GUI interpreter."""

import ctypes
import os
import traceback
from pathlib import Path
from tempfile import gettempdir

os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

try:
    from main import main

    main()
except Exception:
    trace = traceback.format_exc()
    log = None
    for root in (os.environ.get("LOCALAPPDATA"), gettempdir()):
        if not root:
            continue
        candidate = Path(root) / "MiniFactory" / "startup-error.log"
        try:
            candidate.parent.mkdir(parents=True, exist_ok=True)
            candidate.write_text(trace, encoding="utf-8")
            log = candidate
            break
        except OSError:
            continue
    message = f"MiniFactory stopped unexpectedly.\nDetails: {log}" if log else trace
    ctypes.windll.user32.MessageBoxW(None, message, "MiniFactory", 0x10)
    raise SystemExit(1)
