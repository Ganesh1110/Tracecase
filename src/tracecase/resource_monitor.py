"""Resource monitoring and pressure evaluation for Tracecase worker management.

Provides host capability detection, system load average monitoring, and safe
resource threshold evaluations to prevent execution workers from overwhelming
the host system.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from typing import Any

from tracecase.telemetry import get_load_average, get_memory_rss_mb

logger = logging.getLogger("tracecase.resource_monitor")


@dataclass(frozen=True)
class ResourcePressure:
    """Represents current host resource pressure state."""

    is_under_pressure: bool
    reasons: list[str] = field(default_factory=list)
    load_average: float = 0.0
    load_ratio: float = 0.0
    peak_memory_rss_mb: float = 0.0
    cpu_cores: int = 1

    def to_dict(self) -> dict[str, Any]:
        return {
            "is_under_pressure": self.is_under_pressure,
            "reasons": self.reasons,
            "load_average": self.load_average,
            "load_ratio": self.load_ratio,
            "peak_memory_rss_mb": self.peak_memory_rss_mb,
            "cpu_cores": self.cpu_cores,
        }


class ResourceMonitor:
    """Monitors host load and memory to signal backpressure to worker pools."""

    def __init__(
        self,
        max_load_ratio: float = 2.5,
        max_peak_memory_mb: float | None = None,
        max_contexts_per_browser: int = 8,
    ) -> None:
        """Initialize resource monitor with safety thresholds.

        Args:
            max_load_ratio: Maximum load average divided by CPU cores before flagging pressure.
                           Default 2.5 allows normal spikes while protecting against severe thrashing.
            max_peak_memory_mb: Optional hard cap on peak runner process memory (ru_maxrss).
            max_contexts_per_browser: Maximum active contexts per browser process.
        """
        self.max_load_ratio = max_load_ratio
        self.max_peak_memory_mb = max_peak_memory_mb
        self.max_contexts_per_browser = max_contexts_per_browser
        self.cpu_cores = max(1, os.cpu_count() or 1)

    def get_safe_concurrency_ceiling(self, requested_concurrency: int = 2) -> int:
        """Clamp requested worker concurrency within safe host resource limits.

        Ensures concurrency does not exceed available CPU cores by more than 2x
        while respecting Tracecase's bounded concurrency envelope (1 to 8).
        """
        host_safe_max = max(1, min(8, self.cpu_cores * 2))
        bounded = max(1, min(host_safe_max, int(requested_concurrency)))
        return bounded

    def check_pressure(self, active_contexts: int = 0) -> ResourcePressure:
        """Inspect system metrics and evaluate whether workers should apply backpressure."""
        load_avg = get_load_average()
        load_ratio = round(load_avg / self.cpu_cores, 2)
        peak_rss = get_memory_rss_mb()
        reasons: list[str] = []

        # 1. Check load average ratio against physical CPU cores
        if self.max_load_ratio > 0 and load_ratio > self.max_load_ratio:
            reasons.append(
                f"System load ratio {load_ratio:.1f} exceeds threshold {self.max_load_ratio:.1f} "
                f"(Load {load_avg:.1f} on {self.cpu_cores} cores)"
            )

        # 2. Check peak runner process memory if configured
        if self.max_peak_memory_mb and peak_rss > self.max_peak_memory_mb:
            reasons.append(
                f"Peak runner RSS {peak_rss:.1f}MB exceeds limit {self.max_peak_memory_mb:.1f}MB"
            )

        # 3. Check active context density per browser
        if self.max_contexts_per_browser > 0 and active_contexts >= self.max_contexts_per_browser:
            reasons.append(
                f"Active browser contexts ({active_contexts}) reached process safety limit ({self.max_contexts_per_browser})"
            )

        is_under_pressure = len(reasons) > 0
        if is_under_pressure:
            logger.warning("Resource pressure detected: %s", "; ".join(reasons))

        return ResourcePressure(
            is_under_pressure=is_under_pressure,
            reasons=reasons,
            load_average=load_avg,
            load_ratio=load_ratio,
            peak_memory_rss_mb=peak_rss,
            cpu_cores=self.cpu_cores,
        )
