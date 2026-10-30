import threading
from typing import Dict, Any, Optional, List
from datetime import datetime, timezone

class MonitoringService:
    """
    In-memory, thread-safe monitoring & telemetry collector for security events:
    - Auth failure and success rates
    - Token refresh failures and reuse theft alerts
    - Mobile App Lock bypass and anomaly reports
    - Rate limit triggers
    - Prometheus-compatible metrics export
    """

    def __init__(self):
        self._lock = threading.Lock()
        self.reset()

    def reset(self):
        with getattr(self, "_lock", threading.Lock()):
            self._login_successes: int = 0
            self._login_failures: int = 0
            self._refresh_successes: int = 0
            self._refresh_failures: int = 0
            self._token_reuse_events: int = 0
            self._lock_bypass_reports: int = 0
            self._lock_failures: int = 0
            self._rate_limited_events: int = 0
            self._recent_anomalies: List[Dict[str, Any]] = []

    def record_login_success(self):
        with self._lock:
            self._login_successes += 1

    def record_login_failure(self, reason: str = "invalid_credentials"):
        with self._lock:
            self._login_failures += 1

    def record_refresh_success(self):
        with self._lock:
            self._refresh_successes += 1

    def record_refresh_failure(self, reason: str = "expired_or_revoked"):
        with self._lock:
            self._refresh_failures += 1

    def record_token_reuse(self, user_id: Optional[str] = None):
        with self._lock:
            self._token_reuse_events += 1
            self._recent_anomalies.append({
                "type": "TOKEN_REUSE_DETECTED",
                "user_id": user_id,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })
            if len(self._recent_anomalies) > 50:
                self._recent_anomalies.pop(0)

    def record_lock_bypass(self, details: Optional[str] = None, client_ip: Optional[str] = None):
        with self._lock:
            self._lock_bypass_reports += 1
            self._recent_anomalies.append({
                "type": "APP_LOCK_BYPASS_REPORTED",
                "details": details,
                "ip": client_ip,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })
            if len(self._recent_anomalies) > 50:
                self._recent_anomalies.pop(0)

    def record_lock_failure(self):
        with self._lock:
            self._lock_failures += 1

    def record_rate_limit(self, key: str = "general"):
        with self._lock:
            self._rate_limited_events += 1

    def get_stats(self) -> Dict[str, Any]:
        with self._lock:
            total_logins = self._login_successes + self._login_failures
            login_failure_rate = (self._login_failures / total_logins) if total_logins > 0 else 0.0

            total_refreshes = self._refresh_successes + self._refresh_failures
            refresh_failure_rate = (self._refresh_failures / total_refreshes) if total_refreshes > 0 else 0.0

            return {
                "auth": {
                    "login_successes": self._login_successes,
                    "login_failures": self._login_failures,
                    "total_logins": total_logins,
                    "login_failure_rate": round(login_failure_rate, 4),
                },
                "tokens": {
                    "refresh_successes": self._refresh_successes,
                    "refresh_failures": self._refresh_failures,
                    "total_refreshes": total_refreshes,
                    "refresh_failure_rate": round(refresh_failure_rate, 4),
                    "token_reuse_events": self._token_reuse_events,
                },
                "security": {
                    "lock_bypass_reports": self._lock_bypass_reports,
                    "lock_failures": self._lock_failures,
                    "rate_limited_events": self._rate_limited_events,
                    "recent_anomalies": list(self._recent_anomalies),
                },
                "status": "HEALTHY" if self._token_reuse_events == 0 and self._lock_bypass_reports == 0 else "ALERT",
            }

    def get_prometheus_metrics(self) -> str:
        stats = self.get_stats()
        lines = [
            "# HELP auth_login_successes_total Total successful user logins",
            "# TYPE auth_login_successes_total counter",
            f"auth_login_successes_total {stats['auth']['login_successes']}",
            "",
            "# HELP auth_login_failures_total Total failed user logins",
            "# TYPE auth_login_failures_total counter",
            f"auth_login_failures_total {stats['auth']['login_failures']}",
            "",
            "# HELP auth_refresh_successes_total Total successful token refreshes",
            "# TYPE auth_refresh_successes_total counter",
            f"auth_refresh_successes_total {stats['tokens']['refresh_successes']}",
            "",
            "# HELP auth_refresh_failures_total Total failed token refreshes",
            "# TYPE auth_refresh_failures_total counter",
            f"auth_refresh_failures_total {stats['tokens']['refresh_failures']}",
            "",
            "# HELP auth_token_reuse_events_total Token theft/reuse detection alerts",
            "# TYPE auth_token_reuse_events_total counter",
            f"auth_token_reuse_events_total {stats['tokens']['token_reuse_events']}",
            "",
            "# HELP app_lock_bypass_reports_total Total reported app lock bypass events",
            "# TYPE app_lock_bypass_reports_total counter",
            f"app_lock_bypass_reports_total {stats['security']['lock_bypass_reports']}",
            "",
            "# HELP rate_limited_requests_total Total rate limited requests",
            "# TYPE rate_limited_requests_total counter",
            f"rate_limited_requests_total {stats['security']['rate_limited_events']}",
        ]
        return "\n".join(lines) + "\n"

monitoring = MonitoringService()

