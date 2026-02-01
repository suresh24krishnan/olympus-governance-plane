from olympus.core.arbiter import OlympusArbiter
from olympus.adapters.jira.jira_client import JiraAdapter

from olympus.ui.console_dashboard import (
    display_banner,
    display_command_envelope,
    display_jury_panels,
    display_final_verdict,
    display_sentinel_action,
)

class OlympusCommandCenter:
    """
    Tier-0 Operator UI:
    - Takes a human prompt (command)
    - Asks Olympus (Verdict Plane)
    - Sentinel enforces (Jira as system-of-record)
    """

    def __init__(self):
        self.arbiter = OlympusArbiter()
        self.jira = JiraAdapter()

    def run_once(self, prompt: str):
        # 1) Verdict Plane
        result = self.arbiter.run_jury(prompt)

        # 2) Render Rich UI
        display_banner()
        display_command_envelope(result.case_id, prompt, result.policy_flags)
        display_jury_panels(result.primary, result.secondary)
        display_final_verdict(result.verdict, result.confidence, result.divergence)

        # 3) System-of-record enforcement (correlated)
        existing_ticket = self.jira.find_open_sentinel_ticket(case_id=result.case_id)

        if result.verdict == "ESCALATE":
            title = "Supreme Court Escalation — Consensus Divergence"
            if existing_ticket:
                self.jira.add_comment(existing_ticket.key, result.reasoning)
                display_sentinel_action("Escalation persists. Updated existing incident.", existing_ticket.key)
            else:
                key = self.jira.create_incident_ticket(title, result.reasoning, case_id=result.case_id)
                display_sentinel_action("New escalation triggered. Jira incident created.", key)

        elif result.verdict == "DENY":
            title = "Tier-0 Denial — Blocked by Verdict Plane"
            if existing_ticket:
                self.jira.add_comment(existing_ticket.key, result.reasoning)
                display_sentinel_action("Denial persists. Updated existing incident.", existing_ticket.key)
            else:
                key = self.jira.create_incident_ticket(title, result.reasoning, case_id=result.case_id)
                display_sentinel_action("Denial issued. Jira incident created.", key)

        else:  # ALLOW
            if existing_ticket:
                self.jira.add_comment(existing_ticket.key, f"Consensus restored.\n\n{result.reasoning}")
                self.jira.resolve_ticket(existing_ticket.key)
                display_sentinel_action("Consensus restored. Ticket resolved.", existing_ticket.key)
            else:
                display_sentinel_action("Verdict=ALLOW. No actions required.")

    def loop(self):
        while True:
            print("\nEnter a Tier-0 command (or type 'exit'):\n")
            prompt = input("> ").strip()

            if not prompt:
                continue
            if prompt.lower() in {"exit", "quit", "q"}:
                print("Exiting OLYMPUS Command Center.")
                return

            self.run_once(prompt)


if __name__ == "__main__":
    OlympusCommandCenter().loop()
