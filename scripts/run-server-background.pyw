"""Task Scheduler tracks this console-free process and retries nonzero exits."""

from datetime import datetime
import os
from pathlib import Path
import runpy
import sys
import traceback

root = Path(__file__).resolve().parents[1]
logs = root / "logs"
logs.mkdir(exist_ok=True)
stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
# Separate files preserve startup errors that occur before application logging.
with (logs / f"startup-{stamp}.log").open("a", encoding="utf-8", buffering=1) as log:
    sys.stdout = sys.stderr = log
    os.chdir(root)
    sys.path.insert(0, str(root))
    try:
        runpy.run_module("pocket_clip_selector", run_name="__main__")
    except BaseException:
        traceback.print_exc()
        raise
