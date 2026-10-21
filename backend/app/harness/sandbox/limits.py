"""Kernel sandbox command construction and resource limits for third-party skill scripts."""

from __future__ import annotations

CPU_SECONDS = 10
MEMORY_BYTES = 256 * 1024 * 1024
OUTPUT_BYTES = 20 * 1024 * 1024        # what the script may write
STDOUT_CHARS = 20_000                  # what comes back into context
WALL_CLOCK_SECONDS = 30                # covers sleeping, which CPU time doesn't
MAX_RUNS_PER_HARNESS_RUN = 3
