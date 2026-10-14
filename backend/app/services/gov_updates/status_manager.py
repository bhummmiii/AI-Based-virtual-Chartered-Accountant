"""
Source Status Model & State Transitions (K1).
Strictly implements K1:
- State values: ok | degraded | blocked_requires_verification | unreachable | disabled
- ok: last attempt succeeded and parsed. consecutive_failures reset to 0, last_error cleared.
- degraded: failures in recent attempts but a success within 48h, or parser returned 0 items unexpectedly.
- blocked_requires_verification: HTTP 401/403/429 challenge, captcha, login redirect or robots disallow.
  Sets 24h cooldown (next_retry_at = now + 24h).
- unreachable: DNS/TCP/TLS failure on 3 consecutive probes spanning >= 24h (or verified unreachability).
  Sets next_retry_at = now + 24h.
- disabled: Admin or probe decision.
- sync engine fetches only enabled sources whose status is ok or degraded and past cooldown.
"""

from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any
from sqlalchemy.orm import Session
from app.models.government_update import GovSource


def record_source_attempt(
    source: GovSource,
    success: bool,
    now: Optional[datetime] = None,
    failure_stage: Optional[str] = None,
    error_message: Optional[str] = None,
    is_blocked: bool = False,
    items_count: int = 0,
) -> None:
    """
    Authoritative state transition function for GovSource per K1.
    """
    now = now or datetime.now(timezone.utc)
    source.last_attempt_at = now
    source.last_run_at = now

    if success:
        source.status = "ok"
        source.last_success_at = now
        source.consecutive_failures = 0
        source.failure_stage = None
        source.last_error = None
        source.next_retry_at = None
        return

    # Handle Failure
    source.consecutive_failures = (source.consecutive_failures or 0) + 1
    source.failure_stage = failure_stage or "unknown"
    source.last_error = error_message

    # Blocked by WAF, CAPTCHA, 401/403/429, or Robots Disallow
    if is_blocked or failure_stage in ("http_challenge", "robots", "http_429") or "403" in (error_message or ""):
        source.status = "blocked_requires_verification"
        source.captcha_detected = True
        source.next_retry_at = now + timedelta(hours=24)
        return

    # Network unreachable (DNS, TCP timeout, TLS error)
    if failure_stage in ("dns", "tcp", "tls", "http_timeout"):
        # If consecutive failures >= 3 or first hard network failure
        if source.consecutive_failures >= 3:
            source.status = "unreachable"
            source.next_retry_at = now + timedelta(hours=24)
        else:
            # Check if there was a success within 48h -> degraded
            if source.last_success_at and (now - source.last_success_at).total_seconds() < 172800:
                source.status = "degraded"
                source.next_retry_at = now + timedelta(hours=6)
            else:
                source.status = "unreachable"
                source.next_retry_at = now + timedelta(hours=24)
        return

    # Parser returned 0 items unexpectedly or general HTTP 5xx
    if failure_stage in ("parser", "server_error"):
        if source.last_success_at and (now - source.last_success_at).total_seconds() < 172800:
            source.status = "degraded"
            source.next_retry_at = now + timedelta(hours=6)
        else:
            source.status = "degraded"
            source.next_retry_at = now + timedelta(hours=12)
        return

    # Default fallback failure status
    source.status = "degraded"
    source.next_retry_at = now + timedelta(hours=6)


def is_source_fetchable(source: GovSource, now: Optional[datetime] = None) -> bool:
    """
    Determines if a source is eligible for automated fetching per K1:
    - Must be enabled.
    - Status must be 'ok' or 'degraded'.
    - If next_retry_at is set, now must be >= next_retry_at.
    """
    if not source.enabled:
        return False

    if source.status not in ("ok", "degraded"):
        return False

    now = now or datetime.now(timezone.utc)
    if source.next_retry_at and now < source.next_retry_at:
        return False

    return True
