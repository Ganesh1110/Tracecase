"""Performance and resource telemetry utilities for Tracecase.

Provides monotonic clock measurements, resource consumption tracking (memory RSS,
load average, CPU), and artifact size calculation.
"""

from __future__ import annotations

import contextlib
import logging
import os
import resource
import sys
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger("tracecase.telemetry")


def get_monotonic_time() -> float:
    """Return the current monotonic clock timestamp in seconds."""
    return time.monotonic()


def elapsed_ms(start_monotonic: float, end_monotonic: float | None = None) -> float:
    """Calculate elapsed duration in milliseconds with two-decimal precision."""
    end = end_monotonic if end_monotonic is not None else time.monotonic()
    return round(max(0.0, end - start_monotonic) * 1000.0, 2)


def get_memory_rss_mb() -> float:
    """Return the peak resident set size (RSS) in megabytes for the current process."""
    try:
        ru = resource.getrusage(resource.RUSAGE_SELF)
        # On macOS, ru_maxrss is in bytes; on Linux, it is in kilobytes
        if sys.platform == "darwin":
            return round(ru.ru_maxrss / (1024.0 * 1024.0), 2)
        return round(ru.ru_maxrss / 1024.0, 2)
    except Exception as exc:
        logger.debug("Failed to read memory RSS: %s", exc)
        return 0.0


def get_load_average() -> float:
    """Return the 1-minute system load average."""
    try:
        return round(os.getloadavg()[0], 2)
    except Exception as exc:
        logger.debug("Failed to read load average: %s", exc)
        return 0.0


def get_cpu_percent() -> float:
    """Return the system CPU utilization percentage if supported (via optional psutil)."""
    try:
        import psutil  # type: ignore[import-untyped]
        return round(float(psutil.cpu_percent(interval=None)), 1)
    except Exception:
        # Graceful fallback when psutil is not available
        return 0.0


def get_directory_size_bytes(path: Path | str | None) -> int:
    """Calculate the total size in bytes of all files in a directory."""
    if not path:
        return 0
    p = Path(path)
    if not p.exists() or not p.is_dir():
        return 0
    total = 0
    with contextlib.suppress(OSError):
        for f in p.rglob("*"):
            if f.is_file():
                with contextlib.suppress(OSError):
                    total += f.stat().st_size
    return total


def capture_resource_snapshot(artifact_dir: Path | str | None = None) -> dict[str, Any]:
    """Capture a snapshot of resource metrics and artifact storage usage."""
    return {
        "memory_rss_mb": get_memory_rss_mb(),
        "load_average": get_load_average(),
        "cpu_percent": get_cpu_percent(),
        "artifact_size_bytes": get_directory_size_bytes(artifact_dir),
    }
