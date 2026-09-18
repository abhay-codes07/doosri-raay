"""Fixed templates filled from confirmed fields (no LLM)."""
from __future__ import annotations

from typing import Any, Dict, List

from recovery_agent import rules


def _amount(txn: Dict[str, Any]) -> str:
    value = txn.get("amount")
    try:
        return format(int(float(value)), ",")
    except (TypeError, ValueError):
        return str(value or "")


def _total(txns: List[Dict[str, Any]]) -> str:
    total = 0.0
    for t in txns:
        try:
            total += float(t.get("amount") or 0)
        except (TypeError, ValueError):
            continue
    return format(int(total), ",")


def _txn_lines(txns: List[Dict[str, Any]]) -> str:
    if not txns:
        return "  (no confirmed transactions yet)"
    return "\n".join(
        "  %d. Rs %s to %s on %s via %s, UTR %s"
        % (i, _amount(t), t.get("payee", ""), t.get("timestamp", ""), t.get("app") or "UPI", t.get("utr", ""))
        for i, t in enumerate(txns, 1)
    )


def script_1930(case: Dict[str, Any], txns: List[Dict[str, Any]]) -> Dict[str, str]:
    victim = case.get("victimName") or "the victim"
    state = case.get("state") or "our state"
    date = case.get("incidentDate") or "today"
    en = (
        "Script for 1930 (National Cyber Crime Helpline)\n\n"
        "Namaste. I am calling on behalf of %s from %s. On %s, %s was cheated online and money was sent "
        "from their account. I want to report a financial fraud so the money can be frozen.\n\n"
        "Transactions (please note each one):\n%s\n\n"
        "Total: Rs %s.\n\n"
        "Please register the complaint, share the acknowledgement number, and tell me which bank to contact "
        "for a freeze request. I will also file on cybercrime.gov.in.\n\n"
        "Keep ready: the victim's bank name, account number, registered mobile number, and these UTRs."
    ) % (victim, state, date, victim, _txn_lines(txns), _total(txns))
    hi = (
        "1930 (राष्ट्रीय साइबर अपराध हेल्पलाइन) के लिए स्क्रिप्ट\n\n"
        "नमस्ते। मैं %s (%s) की ओर से बोल रहा/रही हूँ। %s को %s के साथ ऑनलाइन धोखाधड़ी हुई और उनके खाते से "
        "पैसा भेजा गया। मैं यह धोखाधड़ी दर्ज करवाना चाहता/चाहती हूँ ताकि पैसा रोका जा सके।\n\n"
        "लेन-देन:\n%s\n\n"
        "कुल: ₹%s।\n\n"
        "कृपया शिकायत दर्ज करें, पावती नंबर दें, और बताएँ कि फ़्रीज़ के लिए किस बैंक से संपर्क करना है। "
        "मैं cybercrime.gov.in पर भी शिकायत दर्ज करूँगा/करूँगी।\n\n"
        "तैयार रखें: बैंक का नाम, खाता नंबर, रजिस्टर्ड मोबाइल नंबर और ये UTR।"
    ) % (victim, state, date, victim, _txn_lines(txns), _total(txns))
    return {"en": en, "hi": hi}


def freeze_letter(case: Dict[str, Any], txns: List[Dict[str, Any]]) -> str:
    victim = case.get("victimName") or "the account holder"
    date = case.get("incidentDate") or "the incident date"
    ack = case.get("ackNo") or "<NCRP acknowledgement number, once available>"
    return (
        "Subject: Urgent request to freeze fraudulent transactions and beneficiary accounts\n\n"
        "To: The Branch Manager / Nodal Officer (Cyber Fraud)\n\n"
        "Dear Sir/Madam,\n\n"
        "I, %s, am the victim of an online financial fraud on %s. The following transactions were made from my "
        "account under deception:\n%s\n\n"
        "Total amount: Rs %s.\n\n"
        "I request you to (1) mark these transactions as fraudulent, (2) place a lien/freeze on the beneficiary "
        "accounts under the RBI fraud reporting guidelines, and (3) share the beneficiary account details with the "
        "cyber crime cell. A complaint has been lodged on the National Cyber Crime Reporting Portal "
        "(acknowledgement number: %s) and on the 1930 helpline.\n\n"
        "Please treat this as urgent; every hour matters for recovery.\n\n"
        "Yours faithfully,\n%s\n"
        "Registered mobile: <mobile>\nAccount number: <last 4 digits>"
    ) % (victim, date, _txn_lines(txns), _total(txns), ack, victim)


def ncrp_template_narrative(case: Dict[str, Any], txns: List[Dict[str, Any]]) -> str:
    """Deterministic fallback narrative: >= 200 chars, only allowed characters."""
    victim = case.get("victimName") or "the complainant"
    date = case.get("incidentDate") or "the incident date"
    hint = case.get("narrativeHint") or "a fraudulent caller who pretended to be an official"
    parts = [
        "On %s, %s was contacted by %s." % (date, victim, hint),
        "Under this deception the complainant was made to transfer money from their own account to accounts "
        "controlled by the fraudsters.",
    ]
    for t in txns:
        parts.append(
            "Rs %s was sent to %s on %s using %s with UTR %s."
            % (_amount(t), t.get("payee", ""), t.get("timestamp", ""), t.get("app") or "UPI", t.get("utr", ""))
        )
    parts.append(
        "The complainant requests that the beneficiary accounts be frozen immediately, the amount be traced and "
        "returned, and action be taken against the persons responsible."
    )
    return rules.sanitize_narrative(" ".join(parts))


def mrm_checklist(case: Dict[str, Any], mrm: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "victim": case.get("victimName"),
        "portal": mrm.get("portal", rules.MRM_PORTAL),
        "eligible": mrm.get("eligible"),
        "firRequired": mrm.get("firRequired"),
        "rule": mrm.get("rule"),
        "checklist": list(mrm.get("checklist", [])),
    }
