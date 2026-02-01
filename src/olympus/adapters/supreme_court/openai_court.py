import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()

@dataclass
class SupremeOpinion:
    model: str
    verdict: str
    risk: str
    reasoning: list[str]

def call_openai_supreme(packet: str) -> SupremeOpinion:
    """
    External advisory-only Supreme Court.
    Expects *already redacted* packet. Never send raw prompts.
    """
    from openai import OpenAI  # pip install openai

    api_key = os.getenv("OPENAI_API_KEY")
    model = os.getenv("OPENAI_SUPREME_MODEL", "o4-mini")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY not set")

    client = OpenAI(api_key=api_key)

    system = (
        "You are the Supreme Court for a Tier-0 enterprise AI governance system. "
        "You receive a redacted escalation packet. "
        "You MUST respond with STRICT JSON only: {verdict, risk, reasoning}. "
        "verdict must be one of: ALLOW, DENY, ESCALATE. "
        "risk must be one of: LOW, MED, HIGH. "
        "reasoning must be an array of 3-6 short bullets. "
        "Do NOT provide execution steps."
    )

    resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": packet},
        ],
        temperature=0.2,
    )

    raw = resp.choices[0].message.content.strip()

    # parse JSON defensively
    import json, re
    try:
        obj = json.loads(raw)
    except Exception:
        m = re.search(r"\{.*\}", raw, re.S)
        if not m:
            return SupremeOpinion(model=model, verdict="ESCALATE", risk="HIGH",
                                  reasoning=["Invalid JSON from Supreme Court.", "Fail-closed advisory escalation."])
        obj = json.loads(m.group())

    verdict = str(obj.get("verdict", "ESCALATE")).upper()
    risk = str(obj.get("risk", "HIGH")).upper()
    reasoning = obj.get("reasoning", [])
    if not isinstance(reasoning, list):
        reasoning = [str(reasoning)]
    reasoning = [str(x) for x in reasoning][:6]

    if verdict not in {"ALLOW", "DENY", "ESCALATE"}:
        verdict = "ESCALATE"
    if risk not in {"LOW", "MED", "HIGH"}:
        risk = "HIGH"

    return SupremeOpinion(model=model, verdict=verdict, risk=risk, reasoning=reasoning)
