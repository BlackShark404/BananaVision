"""
AUTH-04: In-memory rate limiter for login and PIN swap attempts.

Limits authentication attempts per-username to prevent brute-force attacks.
No external dependency (no Redis needed) — uses an in-memory sliding window.
"""

from __future__ import annotations

import time
import threading
from collections import defaultdict
from dataclasses import dataclass, field

# ── Configuration ────────────────────────────────────────────────────────────

MAX_ATTEMPTS = 5           # Max failed attempts before lockout
LOCKOUT_SECONDS = 300      # 5-minute lockout window
WINDOW_SECONDS = 300       # Sliding window for counting attempts


@dataclass
class _AttemptRecord:
    timestamps: list[float] = field(default_factory=list)
    locked_until: float = 0.0


class RateLimiter:
    """Per-username sliding-window rate limiter with lockout."""

    def __init__(
        self,
        max_attempts: int = MAX_ATTEMPTS,
        lockout_seconds: int = LOCKOUT_SECONDS,
        window_seconds: int = WINDOW_SECONDS,
    ):
        self._max_attempts = max_attempts
        self._lockout_seconds = lockout_seconds
        self._window_seconds = window_seconds
        self._records: dict[str, _AttemptRecord] = defaultdict(_AttemptRecord)
        self._lock = threading.Lock()

    def is_locked(self, key: str) -> tuple[bool, int]:
        """Check if the key is currently locked out.

        Returns:
            (is_locked, remaining_seconds)
        """
        now = time.time()
        with self._lock:
            record = self._records.get(key)
            if not record:
                return False, 0
            if record.locked_until > now:
                return True, int(record.locked_until - now)
            return False, 0

    def record_failure(self, key: str) -> tuple[bool, int]:
        """Record a failed attempt and check if lockout should trigger.

        Returns:
            (is_now_locked, remaining_seconds)
        """
        now = time.time()
        with self._lock:
            record = self._records[key]

            # If already locked, extend lockout
            if record.locked_until > now:
                return True, int(record.locked_until - now)

            # Prune old timestamps outside the sliding window
            cutoff = now - self._window_seconds
            record.timestamps = [t for t in record.timestamps if t > cutoff]

            # Add this failure
            record.timestamps.append(now)

            # Check if we exceeded the threshold
            if len(record.timestamps) >= self._max_attempts:
                record.locked_until = now + self._lockout_seconds
                record.timestamps.clear()
                return True, self._lockout_seconds

            remaining_attempts = self._max_attempts - len(record.timestamps)
            return False, remaining_attempts

    def record_success(self, key: str) -> None:
        """Clear the failure record on successful authentication."""
        with self._lock:
            if key in self._records:
                del self._records[key]


# Singleton instances — one for login (password), one for PIN swap.
login_limiter = RateLimiter()
pin_limiter = RateLimiter()
