from __future__ import annotations
import re
from dataclasses import dataclass
from typing import Dict, List, Tuple

@dataclass
class RedactionResult:
    redacted_text: str
    hits: Dict[str, int]
    notes: List[str]

# --- High-signal patterns (PII + secrets) ---
_PATTERNS: List[Tuple[str, re.Pattern]] = [
    ("EMAIL", re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.I)),
    ("PHONE", re.compile(r"\b(?:\+?1[-.\s]?)?(?:\(\d{3}\)|\d{3})[-.\s]?\d{3}[-.\s]?\d{4}\b")),
    ("SSN", re.compile(r"\b\d{3}-\d{2}-\d{4}\b")),
    ("CREDIT_CARD", re.compile(r"\b(?:\d[ -]*?){13,19}\b")),
    ("IPV4", re.compile(r"\b(?:(?:25[0-5]|2[0-4]\d|[01]?\d?\d)\.){3}(?:25[0-5]|2[0-4]\d|[01]?\d?\d)\b")),
    ("AWS_ACCESS_KEY", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("AWS_SECRET_KEY", re.compile(r"\b(?<![A-Za-z0-9/+=])[A-Za-z0-9/+=]{40}(?![A-Za-z0-9/+=])\b")),
    ("OPENAI_KEY", re.compile(r"\bsk-[A-Za-z0-9]{20,}\b")),
    ("GOOGLE_API_KEY", re.compile(r"\bAIza[0-9A-Za-z\-_]{35}\b")),
    ("JWT", re.compile(r"\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b")),
    ("PRIVATE_KEY_BLOCK", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----[\s\S]+?-----END (?:RSA |EC |OPENSSH )?PRIVATE KEY-----")),
]

# Common “key=value” secret lines (covers .env style)
_ENV_SECRET_LINE = re.compile(
    r"(?im)^\s*([A-Z0-9_]{3,})\s*=\s*([^\n#]+)\s*$"
)

# Keys that are almost always sensitive if they appear in .env or configs
_SENSITIVE_ENV_KEYS = {
    "OPENAI_API_KEY",
    "GEMINI_API_KEY",
    "GOOGLE_API_KEY",
    "JIRA_API_TOKEN",
    "AWS_SECRET_ACCESS_KEY",
    "AWS_ACCESS_KEY_ID",
    "AZURE_CLIENT_SECRET",
    "TOKEN",
    "SECRET",
    "PASSWORD",
    "API_KEY",
}


def _mask(label: str) -> str:
    return f"[REDACTED:{label}]"


def redact_text(text: str, *, redact_env_values: bool = True) -> RedactionResult:
    hits: Dict[str, int] = {}
    notes: List[str] = []
    out = text

    # 1) Pattern-based redaction
    for label, pat in _PATTERNS:
        out, n = pat.subn(_mask(label), out)
        if n:
            hits[label] = hits.get(label, 0) + n

    # 2) .env line protection (optional)
    if redact_env_values:
        def repl(m: re.Match) -> str:
            key = m.group(1).strip().upper()
            val = m.group(2).strip()

            # Always redact if key looks sensitive or value looks like a token
            if (
                key in _SENSITIVE_ENV_KEYS
                or "KEY" in key
                or "SECRET" in key
                or "TOKEN" in key
                or len(val) >= 20  # long values are likely secrets
            ):
                hits["ENV_SECRET_VALUE"] = hits.get("ENV_SECRET_VALUE", 0) + 1
                return f"{key}={_mask('ENV_SECRET_VALUE')}"
            return m.group(0)

        out = _ENV_SECRET_LINE.sub(repl, out)

    if hits:
        notes.append("Redaction applied. External egress is safer, but not guaranteed perfect.")
    else:
        notes.append("No redaction hits detected.")

    return RedactionResult(redacted_text=out, hits=hits, notes=notes)
