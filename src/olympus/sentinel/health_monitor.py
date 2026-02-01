# - Chatgpt - health_monitor.py

from olympus.core.arbiter import OlympusArbiter
from olympus.adapters.jira.jira_client import JiraAdapter

from olympus.ui.console_dashboard import (
    display_banner,
    display_command_envelope,
    display_jury_panels,
    display_final_verdict,
    display_sentinel_action,
)

class SentinelHealthMonitor:
    def __init__(self):
        self.arbiter = OlympusArbiter()
        self.jira = JiraAdapter()

    def run_security_audit(self, check_query: str):
        # 1) Verdict Plane (OLYMPUS) — produce a legal-grade signal first
        result = self.arbiter.run_jury(check_query)  # ConsensusResult (includes case_id)

        # 2) Render Tier-0 Command Center (read-only)
        display_banner()
        display_command_envelope(result.case_id, check_query, result.policy_flags)
        display_jury_panels(result.primary, result.secondary)
        display_final_verdict(result.verdict, result.confidence, result.divergence)

        # 3) System of record check (correlated to THIS case)
        existing_ticket = self.jira.find_open_sentinel_ticket(case_id=result.case_id)

        # 4) Execution Plane (SENTINEL) — workflow only
        if result.verdict == "ESCALATE":
            title = "Supreme Court Escalation — Consensus Divergence"
            body = result.reasoning

            if existing_ticket:
                self.jira.add_comment(existing_ticket.key, body)
                display_sentinel_action(
                    f"Escalation persists (CASE:{result.case_id}). Updated existing incident.",
                    existing_ticket.key
                )
            else:
                key = self.jira.create_incident_ticket(title, body, case_id=result.case_id)
                display_sentinel_action(
                    f"New escalation triggered (CASE:{result.case_id}). Created incident.",
                    key
                )

        elif result.verdict == "DENY":
            title = "Tier-0 Denial — Blocked by Verdict Plane"
            body = result.reasoning

            if existing_ticket:
                self.jira.add_comment(existing_ticket.key, body)
                display_sentinel_action(
                    f"Denial persists (CASE:{result.case_id}). Updated existing incident.",
                    existing_ticket.key
                )
            else:
                key = self.jira.create_incident_ticket(title, body, case_id=result.case_id)
                display_sentinel_action(
                    f"Denial issued (CASE:{result.case_id}). Created incident.",
                    key
                )

        else:  # ALLOW
            if existing_ticket:
                self.jira.add_comment(existing_ticket.key, f"Consensus restored.\n\n{result.reasoning}")
                self.jira.resolve_ticket(existing_ticket.key)
                display_sentinel_action(
                    f"Consensus restored (CASE:{result.case_id}). Resolved incident.",
                    existing_ticket.key
                )
            else:
                display_sentinel_action(f"Verdict=ALLOW (CASE:{result.case_id}). No actions required.")

if __name__ == "__main__":
    monitor = SentinelHealthMonitor()
    monitor.run_security_audit("Is it safe to store API keys in plain text .env files?")
    # monitor.run_security_audit("Is 2+2 equal to 4?")
