# arbiter.py (updated) — Project OLYMPUS
# Tier-0: local jury + optional Supreme Court (local/external) + AEGIS egress proof + PII hard-block

import json
import re
import time
import os
import hashlib
from datetime import datetime, timezone
from dataclasses import dataclass
from dotenv import load_dotenv

import ollama

load_dotenv()


# -----------------------------
# Data contracts
# -----------------------------
@dataclass
class ModelVerdict:
    model: str
    verdict: str        # ALLOW | DENY | ESCALATE
    risk: str           # LOW | MED | HIGH
    reasoning: list[str]


@dataclass
class ConsensusResult:
    verdict: str        # ALLOW | DENY | ESCALATE
    confidence: float   # 0.0 to 1.0
    divergence: float   # 0.0 to 1.0
    reasoning: str      # Forensic bundle for Jira
    primary: ModelVerdict
    secondary: ModelVerdict
    policy_flags: list[str]
    case_id: str        # Correlation key for Jira / replay
    supreme_court: ModelVerdict | None  # optional (local or external)
    hitl_approved: bool  # operator acknowledgement for policy override (case-scoped)

    # --- Operator-visible egress proof ---
    external_packet_raw: str | None = None
    external_packet_redacted: str | None = None
    external_egress_provider: str | None = None
    external_egress_model: str | None = None
    external_egress_allowed: bool = False
    external_egress_block_reason: str | None = None

    # --- PII hard gate metadata (shown in UI + forensics) ---
    pii_detected: bool = False
    pii_types: list[str] | None = None


# -----------------------------
# Arbiter
# -----------------------------
class OlympusArbiter:
    def __init__(self):
        # Local jurors
        self.primary = os.getenv("PRIMARY_MODEL", "llama3.1:latest")
        self.secondary = os.getenv("SECONDARY_MODEL", "gemma3:1b")

        # Optional tuning knobs
        self.divergence_threshold = float(os.getenv("OLYMPUS_DIVERGENCE_THRESHOLD", "0.35"))
        self.switch_sleep_seconds = float(os.getenv("OLYMPUS_MODEL_SWITCH_SLEEP", "1"))

        # Supreme Court controls
        self.supreme_enabled = os.getenv("SUPREME_COURT_ENABLED", "false").lower() == "true"
        self.supreme_mode = os.getenv("SUPREME_COURT_MODE", "local").lower()  # local | external
        self.supreme_model_local = os.getenv("SUPREME_COURT_MODEL", "phi3:mini")

        # External court (OpenAI)
        self.external_provider = os.getenv("EXTERNAL_SUPREME_PROVIDER", "openai").lower()
        self.openai_model = os.getenv("OPENAI_SUPREME_MODEL", "o4-mini")

        # Aegis controls (egress policy)
        self.redaction_enabled = os.getenv("AEGIS_REDACTION_ENABLED", "true").lower() == "true"
        self.send_raw_prompt = os.getenv("AEGIS_SEND_RAW_PROMPT", "false").lower() == "true"

        # PII hard-block knobs
        # If true: any PII detection blocks external egress (even if redaction is ON)
        self.block_external_on_pii = os.getenv("AEGIS_BLOCK_EXTERNAL_ON_PII", "true").lower() == "true"
        # If true: also flags PII in policy_flags for Jira/forensics
        self.flag_pii_in_policy_flags = os.getenv("AEGIS_FLAG_PII_IN_POLICY_FLAGS", "true").lower() == "true"

        # HITL ack gate (Tier-0)
        self.hitl_ack_enabled = os.getenv("OLYMPUS_HITL_ACK_ENABLED", "true").lower() == "true"

        # HITL closure policy (Option A - enterprise clean)
        self.hitl_close_requires_both_allow = (
            os.getenv("OLYMPUS_HITL_CLOSE_REQUIRES_BOTH_ALLOW", "true").lower() == "true"
        )

    # -----------------------------
    # Policy + PII detectors
    # -----------------------------
    def _policy_gate(self, prompt: str) -> list[str]:
        p = prompt.lower()
        flags: list[str] = []

        # Tier-0 "command risk" terms (demo set)
        high_risk_terms = [
            "delete", "wipe", "rotate", "secret", "token", "prod", "shutdown",
            "disable logs", "exfiltrate", "grant admin"
        ]
        for term in high_risk_terms:
            if term in p:
                flags.append(f"POLICY_FLAG:{term}")

        return flags

    def _detect_pii(self, text: str) -> tuple[bool, list[str]]:
        """
        Tier-0 PII detection (lightweight v1):
        - SSN patterns (XXX-XX-XXXX)
        - Email patterns
        Extend as needed (phone, CC, address, etc.)
        """
        types: list[str] = []

        # SSN (strict)
        if re.search(r"\b\d{3}-\d{2}-\d{4}\b", text):
            types.append("SSN")

        # Email (basic)
        if re.search(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b", text):
            types.append("EMAIL")

        # Optional: "SSN" intent keyword (so "send me SSN of Andy" flags even without digits)
        # (Keeps your demo consistent with operator expectations)
        if re.search(r"\bssn\b", text, re.IGNORECASE):
            if "SSN_INTENT" not in types:
                types.append("SSN_INTENT")

        return (len(types) > 0, types)

    # -----------------------------
    # Local juror call
    # -----------------------------
    def _ask_structured(self, model: str, prompt: str) -> ModelVerdict:
        system = (
            "You are a Tier-0 command safety juror. "
            "Return STRICT JSON only, with keys: verdict, risk, reasoning. "
            "verdict must be one of: ALLOW, DENY, ESCALATE. "
            "risk must be one of: LOW, MED, HIGH. "
            "reasoning must be an array of 2-5 short bullet strings. "
            "Do not include any other keys. Do not wrap in markdown. "
            "Output must start with '{' and end with '}'."
        )

        res = ollama.chat(
            model=model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
        )

        raw = (res.get("message", {}).get("content") or "").strip()

        # Strict parse first, then minimal recovery (forensic value only)
        try:
            obj = json.loads(raw)
        except Exception:
            match = re.search(r"\{.*\}", raw, re.S)
            if match:
                try:
                    obj = json.loads(match.group())
                except Exception:
                    return ModelVerdict(
                        model=model,
                        verdict="ESCALATE",
                        risk="HIGH",
                        reasoning=[
                            "Model returned malformed JSON.",
                            "JSON recovery attempt failed.",
                            "Fail-closed escalation.",
                        ],
                    )
            else:
                return ModelVerdict(
                    model=model,
                    verdict="ESCALATE",
                    risk="HIGH",
                    reasoning=[
                        "Model did not return JSON.",
                        "No recoverable structure found.",
                        "Fail-closed escalation.",
                    ],
                )

        verdict = str(obj.get("verdict", "ESCALATE")).upper()
        risk = str(obj.get("risk", "HIGH")).upper()
        reasoning = obj.get("reasoning", [])

        if verdict not in {"ALLOW", "DENY", "ESCALATE"}:
            verdict = "ESCALATE"
        if risk not in {"LOW", "MED", "HIGH"}:
            risk = "HIGH"

        if not isinstance(reasoning, list):
            reasoning = [str(reasoning)]
        reasoning = [str(x) for x in reasoning][:5]

        return ModelVerdict(model=model, verdict=verdict, risk=risk, reasoning=reasoning)

    # -----------------------------
    # Scoring helpers
    # -----------------------------
    def _compute_divergence(self, a: ModelVerdict, b: ModelVerdict) -> float:
        score = 0.0
        if a.verdict != b.verdict:
            score += 0.6
        if a.risk != b.risk:
            score += 0.3

        a_words = set(" ".join(a.reasoning).lower().split())
        b_words = set(" ".join(b.reasoning).lower().split())
        overlap = len(a_words & b_words) / max(1, len(a_words | b_words))
        score += (0.1 * (1.0 - overlap))

        return min(1.0, max(0.0, score))

    # -----------------------------
    # External packet + OpenAI court
    # -----------------------------
    def _build_external_packet(
        self,
        prompt: str,
        case_id: str,
        policy_flags: list[str],
        primary: ModelVerdict,
        secondary: ModelVerdict,
        divergence: float,
        timestamp: str,
        hitl_approved: bool,
    ) -> str:
        prompt_field = prompt if self.send_raw_prompt else "[OMITTED_BY_POLICY]"
        return f"""\
OLYMPUS SUPREME COURT PACKET (FOR REVIEW)
CASE_ID: {case_id}
Timestamp (UTC): {timestamp}
HITL_APPROVED: {hitl_approved}
POLICY_FLAGS: {policy_flags if policy_flags else "None"}
DIVERGENCE: {divergence:.2f}

PRIMARY ({primary.model}): verdict={primary.verdict} risk={primary.risk}
PRIMARY_REASONING: {primary.reasoning}

SECONDARY ({secondary.model}): verdict={secondary.verdict} risk={secondary.risk}
SECONDARY_REASONING: {secondary.reasoning}

USER_PROMPT: {prompt_field}

Instructions:
- Provide advisory judgment only (no execution steps).
- Return STRICT JSON only: verdict, risk, reasoning.
"""

    def _call_openai_supreme(self, packet: str) -> ModelVerdict:
        try:
            from openai import OpenAI
        except Exception:
            return ModelVerdict(
                model="openai",
                verdict="ESCALATE",
                risk="HIGH",
                reasoning=[
                    "OpenAI SDK not installed (pip install openai).",
                    "Fail-closed advisory escalation.",
                ],
            )

        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            return ModelVerdict(
                model="openai",
                verdict="ESCALATE",
                risk="HIGH",
                reasoning=[
                    "OPENAI_API_KEY not set.",
                    "Fail-closed advisory escalation.",
                ],
            )

        client = OpenAI(api_key=api_key)

        system = (
            "You are the Supreme Court for a Tier-0 enterprise AI governance system. "
            "You receive a redacted escalation packet. "
            "You MUST respond with STRICT JSON only: {verdict, risk, reasoning}. "
            "verdict must be one of: ALLOW, DENY, ESCALATE. "
            "risk must be one of: LOW, MED, HIGH. "
            "reasoning must be an array of 3-6 short bullet strings. "
            "Do NOT provide execution steps. Do NOT include markdown."
        )

        # NOTE: Some models reject non-default temperature. Keep default.
        resp = client.chat.completions.create(
            model=self.openai_model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": packet},
            ],
        )

        raw = (resp.choices[0].message.content or "").strip()

        try:
            obj = json.loads(raw)
        except Exception:
            match = re.search(r"\{.*\}", raw, re.S)
            if match:
                try:
                    obj = json.loads(match.group())
                except Exception:
                    return ModelVerdict(
                        model=self.openai_model,
                        verdict="ESCALATE",
                        risk="HIGH",
                        reasoning=[
                            "Supreme Court returned malformed JSON.",
                            "Fail-closed advisory escalation.",
                        ],
                    )
            else:
                return ModelVerdict(
                    model=self.openai_model,
                    verdict="ESCALATE",
                    risk="HIGH",
                    reasoning=[
                        "Supreme Court did not return JSON.",
                        "Fail-closed advisory escalation.",
                    ],
                )

        verdict = str(obj.get("verdict", "ESCALATE")).upper()
        risk = str(obj.get("risk", "HIGH")).upper()
        reasoning = obj.get("reasoning", [])

        if verdict not in {"ALLOW", "DENY", "ESCALATE"}:
            verdict = "ESCALATE"
        if risk not in {"LOW", "MED", "HIGH"}:
            risk = "HIGH"
        if not isinstance(reasoning, list):
            reasoning = [str(reasoning)]
        reasoning = [str(x) for x in reasoning][:6]

        return ModelVerdict(model=self.openai_model, verdict=verdict, risk=risk, reasoning=reasoning)

    # -----------------------------
    # Main entry
    # -----------------------------
    def run_jury(self, prompt: str, hitl_approved: bool = False) -> ConsensusResult:
        """
        Tier-0 case-scoped arbitration.

        HITL semantics (case-scoped):
        - hitl_approved=True means a human has acknowledged the risk for THIS case_id.
        - HITL does NOT auto-close; it can relax the *policy flag gate*.
        - Closure still requires safe-enough model signals (see HITL closure policy).

        Safety rules preserved:
        - HIGH risk from any juror always forces ESCALATE (even with HITL).
        - Supreme Court is advisory-only and can only tighten (never loosen).

        NEW:
        - Hard-block external egress on PII when AEGIS_BLOCK_EXTERNAL_ON_PII=true.
        - external_packet_raw / external_packet_redacted returned for UI proof.
        """
        if not self.hitl_ack_enabled:
            hitl_approved = False

        case_id = hashlib.sha1(prompt.encode("utf-8")).hexdigest()[:6].upper()
        timestamp = datetime.now(timezone.utc).isoformat(timespec="seconds")

        # Detect PII early
        pii_detected, pii_types = self._detect_pii(prompt)

        # Policy flags (+ optional PII policy flag)
        policy_flags = self._policy_gate(prompt)
        if pii_detected and self.flag_pii_in_policy_flags:
            policy_flags.append(f"POLICY_FLAG:PII_DETECTED({','.join(pii_types)})")

        # Run jurors (forensic value)
        p_v = self._ask_structured(self.primary, prompt)
        time.sleep(self.switch_sleep_seconds)
        s_v = self._ask_structured(self.secondary, prompt)

        divergence = self._compute_divergence(p_v, s_v)

        # -----------------------------
        # Deterministic Verdict (Tier-0)
        # -----------------------------
        governance_override = "NONE"

        # 1) Policy gate
        if policy_flags and not hitl_approved:
            verdict = "ESCALATE"
            confidence = 0.60
            governance_override = "POLICY_GATE_ENFORCED"
        else:
            # 2) Absolute risk gate
            if "HIGH" in (p_v.risk, s_v.risk):
                verdict = "ESCALATE"
                confidence = 0.60
                governance_override = "HIGH_RISK_ENFORCED"
            # 3) Consensus path
            elif p_v.verdict == s_v.verdict and divergence < self.divergence_threshold:
                verdict = p_v.verdict
                confidence = 0.90 if not hitl_approved else 0.85
                governance_override = "HITL_ACK_APPLIED" if hitl_approved else "NONE"
            else:
                verdict = "ESCALATE"
                confidence = 0.50
                governance_override = "HITL_ACK_APPLIED" if hitl_approved else "NONE"

        # HITL closure policy (Option A)
        if hitl_approved and self.hitl_close_requires_both_allow:
            both_allow = (p_v.verdict == "ALLOW" and s_v.verdict == "ALLOW")
            no_high_risk = ("HIGH" not in (p_v.risk, s_v.risk))
            if both_allow and no_high_risk:
                verdict = "ALLOW"
                confidence = max(confidence, 0.80)
                governance_override = "HITL_CLOSE_ALLOWED"

        # -----------------------------
        # Supreme Court (advisory, tighten-only)
        # -----------------------------
        supreme_v: ModelVerdict | None = None

        # Egress proof fields
        external_packet_raw: str | None = None
        external_packet_redacted: str | None = None
        external_egress_allowed = False
        external_egress_block_reason: str | None = None
        external_egress_provider: str | None = None
        external_egress_model: str | None = None

        if self.supreme_enabled and verdict == "ESCALATE":
            if self.supreme_mode == "local":
                time.sleep(self.switch_sleep_seconds)
                supreme_v = self._ask_structured(self.supreme_model_local, prompt)

            elif self.supreme_mode == "external":
                external_egress_provider = self.external_provider
                external_egress_model = self.openai_model if self.external_provider == "openai" else None

                # Hard-block external egress on PII (enterprise default)
                if self.block_external_on_pii and pii_detected:
                    external_egress_block_reason = (
                        f"PII detected in prompt ({','.join(pii_types)}); external egress blocked"
                    )
                    supreme_v = ModelVerdict(
                        model="EXTERNAL_BLOCKED_PII",
                        verdict="ESCALATE",
                        risk="HIGH",
                        reasoning=[
                            f"External Supreme Court blocked: PII detected ({', '.join(pii_types)}).",
                            "External oversight is prohibited for PII-bearing prompts in Tier-0 mode.",
                            "Fail-closed advisory escalation.",
                        ],
                    )

                # Block external court unless redaction is enabled
                elif not self.redaction_enabled:
                    external_egress_block_reason = "AEGIS_REDACTION_ENABLED=false (egress blocked)"
                    supreme_v = ModelVerdict(
                        model="EXTERNAL_BLOCKED",
                        verdict="ESCALATE",
                        risk="HIGH",
                        reasoning=[
                            "External Supreme Court blocked: AEGIS_REDACTION_ENABLED=false",
                            "Fail-closed advisory escalation.",
                        ],
                    )

                else:
                    # Build packet (respects AEGIS_SEND_RAW_PROMPT)
                    packet = self._build_external_packet(
                        prompt=prompt,
                        case_id=case_id,
                        policy_flags=policy_flags,
                        primary=p_v,
                        secondary=s_v,
                        divergence=divergence,
                        timestamp=timestamp,
                        hitl_approved=hitl_approved,
                    )
                    external_packet_raw = packet

                    # Enforce redaction before egress
                    packet_redacted = None
                    try:
                        from olympus.security.redaction import redact_text
                        packet_redacted = redact_text(packet).redacted_text
                        external_packet_redacted = packet_redacted
                    except Exception:
                        external_egress_block_reason = "Redaction module failed (egress blocked)"
                        supreme_v = ModelVerdict(
                            model="EXTERNAL_BLOCKED",
                            verdict="ESCALATE",
                            risk="HIGH",
                            reasoning=[
                                "External Supreme Court blocked: redaction module failed to load.",
                                "Fail-closed advisory escalation.",
                            ],
                        )

                    if supreme_v is None:
                        if self.external_provider == "openai":
                            if not packet_redacted:
                                external_egress_block_reason = external_egress_block_reason or "No redacted packet available"
                                supreme_v = ModelVerdict(
                                    model="EXTERNAL_BLOCKED",
                                    verdict="ESCALATE",
                                    risk="HIGH",
                                    reasoning=[
                                        "External Supreme Court blocked: no redacted packet available.",
                                        "Fail-closed advisory escalation.",
                                    ],
                                )
                            else:
                                external_egress_allowed = True
                                supreme_v = self._call_openai_supreme(packet_redacted)
                        else:
                            external_egress_block_reason = f"Unsupported provider: {self.external_provider}"
                            supreme_v = ModelVerdict(
                                model="EXTERNAL_UNSUPPORTED",
                                verdict="ESCALATE",
                                risk="HIGH",
                                reasoning=[
                                    f"External provider not supported: {self.external_provider}",
                                    "Set EXTERNAL_SUPREME_PROVIDER=openai",
                                ],
                            )

        # Tighten-only (Supreme Court advisory)
        if supreme_v:
            if supreme_v.risk in {"MED", "HIGH"}:
                verdict = "ESCALATE"
                confidence = min(confidence, 0.60)
                if governance_override == "NONE":
                    governance_override = "SUPREME_RISK_TIGHTENED"

            if supreme_v.verdict in {"DENY", "ESCALATE"}:
                verdict = "ESCALATE"
                confidence = min(confidence, 0.60)
                if governance_override == "NONE":
                    governance_override = "SUPREME_VERDICT_TIGHTENED"

        sentinel_directive = (
            "HITL REQUIRED: open/maintain Jira incident until reviewed."
            if verdict == "ESCALATE"
            else "BLOCKED: do not proceed. Human approval required to override."
            if verdict == "DENY"
            else "APPROVED: safe to proceed under current policy constraints."
        )

        forensic = f"""\
🏛️ PROJECT OLYMPUS — CONSENSUS INCIDENT PACKET
CASE_ID: {case_id}
Timestamp (UTC): {timestamp}

=== GOVERNANCE ENVELOPE ===
HITL_APPROVED: {hitl_approved}
HITL_ACK_ENABLED: {self.hitl_ack_enabled}
HITL_CLOSE_REQUIRES_BOTH_ALLOW: {self.hitl_close_requires_both_allow}
GOVERNANCE_OVERRIDE: {governance_override}

=== PII ENVELOPE (AEGIS) ===
PII_DETECTED: {pii_detected}
PII_TYPES: {pii_types if pii_types else "None"}
BLOCK_EXTERNAL_ON_PII: {self.block_external_on_pii}

=== EGRESS POLICY (AEGIS) ===
REDACTION_ENABLED: {self.redaction_enabled}
SEND_RAW_PROMPT: {self.send_raw_prompt}
EXTERNAL_PROVIDER: {self.external_provider}
EXTERNAL_EGRESS_ALLOWED: {external_egress_allowed}
EXTERNAL_EGRESS_BLOCK_REASON: {external_egress_block_reason or "None"}

=== VERDICT SUMMARY ===
VERDICT:      {verdict}
CONFIDENCE:   {confidence:.2f}
DIVERGENCE:   {divergence:.2f}
POLICY_FLAGS: {policy_flags if policy_flags else "None"}
MODELS:       primary={self.primary} | secondary={self.secondary}

=== USER PROMPT ===
{prompt}

=== PRIMARY JURY — {self.primary} ===
Verdict: {p_v.verdict}
Risk:    {p_v.risk}
Reasoning:
{chr(10).join(f"  - {x}" for x in p_v.reasoning)}

=== SECONDARY JURY — {self.secondary} ===
Verdict: {s_v.verdict}
Risk:    {s_v.risk}
Reasoning:
{chr(10).join(f"  - {x}" for x in s_v.reasoning)}
"""

        if supreme_v:
            forensic += f"""

=== SUPREME COURT — {supreme_v.model} ({self.supreme_mode.upper()}) ===
Verdict: {supreme_v.verdict}
Risk:    {supreme_v.risk}
Reasoning:
{chr(10).join(f"  - {x}" for x in supreme_v.reasoning)}
"""

        forensic += f"""

=== SENTINEL DIRECTIVE ===
{sentinel_directive}
"""

        return ConsensusResult(
            verdict=verdict,
            confidence=confidence,
            divergence=divergence,
            reasoning=forensic,
            primary=p_v,
            secondary=s_v,
            policy_flags=policy_flags,
            case_id=case_id,
            supreme_court=supreme_v,
            hitl_approved=hitl_approved,

            # Egress proof
            external_packet_raw=external_packet_raw,
            external_packet_redacted=external_packet_redacted,
            external_egress_provider=external_egress_provider,
            external_egress_model=external_egress_model,
            external_egress_allowed=external_egress_allowed,
            external_egress_block_reason=external_egress_block_reason,

            # PII metadata
            pii_detected=pii_detected,
            pii_types=pii_types,
        )
