# - Chatgpt - jira_client.py

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from jira import JIRA


# Load .env from current working directory explicitly (Streamlit-friendly)
load_dotenv(dotenv_path=Path.cwd() / ".env")


class JiraAdapter:
    """
    Jira System-of-Record adapter for Project OLYMPUS / SENTINEL.

    Key behaviors:
    - CASE-scoped lookup via summary tag: [CASE:<id>]
    - "Resolve latest" is intentionally broad (operator override)
    - "Resolve case ticket" is safe + deterministic: resolves ONLY the open ticket for a given case_id
    """

    def __init__(self):
        self.url = os.getenv("JIRA_URL")
        self.email = os.getenv("JIRA_EMAIL")
        self.token = os.getenv("JIRA_API_TOKEN")
        self.project = os.getenv("JIRA_PROJECT_KEY")

        if not self.url or not self.email or not self.token or not self.project:
            raise ValueError(
                "Missing Jira configuration. Ensure JIRA_URL, JIRA_EMAIL, JIRA_API_TOKEN, JIRA_PROJECT_KEY are set."
            )

        # Configurable (Tier-0 portability)
        self.issue_type = os.getenv("JIRA_ISSUE_TYPE", "Report an incident")

        # NOTE: Transition IDs differ per Jira workflow; keep configurable.
        self.resolve_transition_id = os.getenv("JIRA_RESOLVE_TRANSITION_ID", "9014")

        self.client = JIRA(server=self.url, basic_auth=(self.email, self.token))

    def create_incident_ticket(self, summary: str, description: str, case_id: Optional[str] = None) -> str:
        """Creates a Jira incident ticket. Correlates by case_id to prevent clobbering."""
        case_tag = f"[CASE:{case_id}] " if case_id else ""
        issue_dict = {
            "project": {"key": self.project},
            "summary": f"[SENTINEL][OLYMPUS] {case_tag}{summary}",
            "description": description,
            "issuetype": {"name": self.issue_type},
        }
        try:
            new_issue = self.client.create_issue(fields=issue_dict)
            return new_issue.key
        except Exception as e:
            print(f"❌ Failed to create ticket: {e}")
            print("💡 TIP: Verify JIRA_ISSUE_TYPE matches your project's issue types (e.g., Task/Bug/Story).")
            raise

    def find_open_sentinel_ticket(self, case_id: Optional[str] = None):
        """
        Finds the most recent open OLYMPUS/SENTINEL ticket.
        - If case_id is provided: returns the most recent OPEN ticket for that case only.
        - If case_id is None: returns the most recent OPEN OLYMPUS/SENTINEL ticket (operator override behavior).
        """
        # Robust JQL: search for the substring CASE:<id> (avoids bracket quirks)
        case_clause = f' AND summary ~ "CASE:{case_id}"' if case_id else ""

        jql = (
            f'project = "{self.project}" '
            f"AND statusCategory != Done "
            f'AND summary ~ "[SENTINEL]" '
            f'AND summary ~ "[OLYMPUS]"'
            f"{case_clause} "
            f"ORDER BY created DESC"
        )
        issues = self.client.search_issues(jql, maxResults=1)
        return issues[0] if issues else None

    # -------------------------
    # Safe operator helpers
    # -------------------------
    def resolve_case_ticket(self, case_id: str) -> Optional[str]:
        """
        Resolves ONLY the open ticket for a given case_id.
        Returns the resolved ticket key, or None if no open ticket exists.
        """
        issue = self.find_open_sentinel_ticket(case_id=case_id)
        if not issue:
            return None

        self.add_comment(
            issue.key,
            f"Operator action: resolving CASE-scoped OLYMPUS incident for CASE:{case_id}.",
        )
        self.resolve_ticket(issue.key)
        return issue.key

    def resolve_latest_open_olympus_ticket(self) -> Optional[str]:
        """
        Resolves the latest open OLYMPUS ticket (NOT case-scoped).
        Returns the resolved ticket key, or None if none exist.
        """
        issue = self.find_open_sentinel_ticket(case_id=None)
        if not issue:
            return None

        self.add_comment(issue.key, "Operator override: resolving latest open OLYMPUS incident (not case-scoped).")
        self.resolve_ticket(issue.key)
        return issue.key

    # -------------------------
    # Jira primitives
    # -------------------------
    def resolve_ticket(self, ticket_key: str) -> None:
        """Moves the ticket to the configured resolve/done transition."""
        try:
            self.client.transition_issue(ticket_key, transition=self.resolve_transition_id)
            print(f"✅ Self-Healing Complete: {ticket_key} moved to Done/Resolved.")
        except Exception as e:
            print(f"❌ Failed to resolve {ticket_key}: {e}")
            raise

    def add_comment(self, ticket_key: str, comment: str) -> None:
        """Small helper so Sentinel doesn't touch self.client directly."""
        self.client.add_comment(ticket_key, comment)

    def update_description(self, ticket_key: str, description: str) -> None:
        """Optional: keep latest forensic packet as the issue description."""
        issue = self.client.issue(ticket_key)
        issue.update(fields={"description": description})
