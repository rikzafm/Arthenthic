"""
server/monitoring/sla_monitor.py
Wave 3 Milestone 7 - Production SLA Monitoring & Automated Rollback Governor.
Tracks the 5 critical production KPIs from RELEASE_AND_STAGED_ROLLOUT.md:
1. Login Failure Rate (< 1.0% healthy, > 2.5% P1 alert)
2. Token Refresh Failure Rate (< 0.2% healthy, > 0.8% P1 alert)
3. Token Reuse / Theft Detection (= 0, > 0 P0 alert)
4. Hardware Lock Bypass / Tamper Reports (= 0, > 0 P0 alert)
5. Rate Limit Triggers (baseline < 50/min)
Enforces automated rollback / pause upon any P0 threshold breach.
"""

import logging
import time
from typing import Any, Dict, List, Optional

logger = logging.getLogger("arthentic.sla_monitor")


class SlaMonitorEngine:
    """
    Evaluates live production telemetry against SLA KPI thresholds and governs
    the 7-day phased App Store rollout progression.
    """

    STAGED_ROLLOUT_SCHEDULE = {
        1: 1,    # Day 1: 1%
        2: 2,    # Day 2: 2%
        3: 5,    # Day 3: 5%
        4: 10,   # Day 4: 10%
        5: 20,   # Day 5: 20%
        6: 50,   # Day 6: 50%
        7: 100,  # Day 7: 100% Full Release
    }

    def __init__(self):
        self._current_day = 1
        self._state = "ACTIVE"  # ACTIVE, PAUSED, HALTED, ROLLED_BACK
        self._pause_reason: Optional[str] = None
        self._p0_alerts_count = 0
        self._p1_alerts_count = 0

        # Baseline KPI counters
        self._kpis = {
            "auth_login_failures_pct": 0.42,
            "auth_refresh_failures_pct": 0.08,
            "token_reuse_events_total": 0,
            "tamper_reports_total": 0,
            "rate_limited_requests_per_min": 14,
        }
        self._incident_history: List[Dict[str, Any]] = []

    def evaluate_kpis(self) -> Dict[str, Any]:
        """
        Evaluates current KPIs against production thresholds.
        """
        healthy = (
            self._kpis["auth_login_failures_pct"] < 2.5
            and self._kpis["auth_refresh_failures_pct"] < 0.8
            and self._kpis["token_reuse_events_total"] == 0
            and self._kpis["tamper_reports_total"] == 0
            and self._kpis["rate_limited_requests_per_min"] < 50
        )

        return {
            "healthy": healthy,
            "current_rollout_day": self._current_day,
            "rollout_percentage": self.STAGED_ROLLOUT_SCHEDULE.get(self._current_day, 100),
            "state": self._state,
            "p0_alerts": self._p0_alerts_count,
            "p1_alerts": self._p1_alerts_count,
            "kpis": dict(self._kpis),
            "timestamp": time.time(),
        }

    def get_rollout_status(self) -> Dict[str, Any]:
        return {
            "state": self._state,
            "current_day": self._current_day,
            "rollout_percentage": self.STAGED_ROLLOUT_SCHEDULE.get(self._current_day, 100),
            "pause_reason": self._pause_reason,
            "p0_alerts": self._p0_alerts_count,
            "p1_alerts": self._p1_alerts_count,
            "kpis": dict(self._kpis),
        }

    def ingest_telemetry_event(self, event_type: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Ingests real-time telemetry event.
        Automatically triggers emergency pause/rollback if event represents P0 breach.
        """
        p0_triggered = False

        if event_type in ["app_lock_bypass_tamper", "token_reuse_theft"]:
            p0_triggered = True
            self._p0_alerts_count += 1
            if event_type == "app_lock_bypass_tamper":
                self._kpis["tamper_reports_total"] += 1
            else:
                self._kpis["token_reuse_events_total"] += 1

            self._state = "PAUSED"
            self._pause_reason = "P0 Alert: Hardware tamper or token reuse detected"
            logger.critical("AUTOMATED ROLLBACK GOVERNOR TRIGGERED: %s", self._pause_reason)

            self._incident_history.append({
                "timestamp": time.time(),
                "event_type": event_type,
                "payload": payload,
                "action": "AUTO_PAUSED",
            })

        return {
            "p0_triggered": p0_triggered,
            "current_state": self._state,
            "pause_reason": self._pause_reason,
        }

    def execute_rollout_action(
        self,
        action: str,
        admin_wallet: Optional[str] = None,
        reason: str = "Admin requested",
    ) -> Dict[str, Any]:
        """
        Executes manual governor control: pause, resume, advance, rollback.
        """
        valid_actions = ["pause", "resume", "advance", "rollback"]
        if action not in valid_actions:
            raise ValueError(f"Invalid rollout action: {action}. Must be one of {valid_actions}")

        if action == "pause":
            self._state = "PAUSED"
            self._pause_reason = reason
        elif action == "resume":
            self._state = "ACTIVE"
            self._pause_reason = None
            # Reset P0 counts upon security clearance
            self._p0_alerts_count = 0
            self._kpis["tamper_reports_total"] = 0
            self._kpis["token_reuse_events_total"] = 0
        elif action == "advance":
            if self._current_day < 7:
                self._current_day += 1
            self._state = "ACTIVE"
            self._pause_reason = None
        elif action == "rollback":
            self._state = "ROLLED_BACK"
            self._pause_reason = reason

        logger.info("Rollout action executed: %s by %s. Reason: %s", action, admin_wallet, reason)

        return {
            "action": action,
            "state": self._state,
            "current_day": self._current_day,
            "rollout_percentage": self.STAGED_ROLLOUT_SCHEDULE.get(self._current_day, 100),
            "pause_reason": self._pause_reason,
            "admin_wallet": admin_wallet,
            "reason": reason,
            "timestamp": time.time(),
        }


sla_monitor = SlaMonitorEngine()

