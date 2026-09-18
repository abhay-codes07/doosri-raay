"""Pure, deterministic recovery rules. No AWS, no LLM. Unit-tested.

- validate_fields: UTR ``^\\d{12}$``, amount numeric 1..1e8, timestamp parseable
  (ISO-8601 or dd/mm/yyyy hh:mm), payee non-empty. Never auto-accepts.
- lookup_ezero_threshold: e-Zero FIR thresholds by state.
- mrm_eligibility: <= 50,000 in a single account -> no FIR; > 50,000 -> FIR mandatory.
- ncrp_narrative_ok / sanitize_narrative: NCRP portal narrative constraints.
"""
from __future__ import annotations

import datetime as dt
import re
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Optional, Tuple

UTR_RE = re.compile(r"^\d{12}$")
AMOUNT_MIN = Decimal("1")
AMOUNT_MAX = Decimal("100000000")  # 10,00,00,000
NARRATIVE_MIN_LEN = 200
NARRATIVE_MAX_LEN = 1500
NARRATIVE_ALLOWED_RE = re.compile(r"^[A-Za-z0-9 ,.\n]+$")
_DISALLOWED_CHAR_RE = re.compile(r"[^A-Za-z0-9 ,.\n]")
MRM_SINGLE_ACCOUNT_LIMIT = Decimal("50000")
MRM_PORTAL = "https://mrm-ncrp.mha.gov.in"
NCRP_PORTAL = "https://cybercrime.gov.in"
DDMMYYYY_RE = re.compile(r"^(\d{1,2})/(\d{1,2})/(\d{4})(?:[ T](\d{1,2}):(\d{2})(?::(\d{2}))?)?$")

EZERO_THRESHOLDS: Dict[str, Dict[str, Any]] = {
    "haryana": {"thresholdInr": 100000, "sourceUrl": "https://haryanapolice.gov.in/"},
    "rajasthan": {"thresholdInr": 100000, "sourceUrl": "https://police.rajasthan.gov.in/"},
    "punjab": {"thresholdInr": 500000, "sourceUrl": "https://punjabpolice.gov.in/"},
}
EZERO_DEFAULT_NOTE = "Check with 1930; SC ordered all states to adopt e-Zero FIR (Aug 2026)"
EZERO_DEFAULT_SOURCE = "https://i4c.mha.gov.in/"
NEUTRAL_PAD_SENTENCE = (
    "The complainant requests that the transactions be traced and the beneficiary accounts be frozen "
    "at the earliest so that the amount can be recovered."
)

MRM_CHECKLIST_BASE = [
    "PAN card of the victim",
    "Bank account details of the victim (account number, IFSC, cancelled cheque or passbook)",
    "NCRP acknowledgement number",
    "Indemnity bond (as per the MRM portal format)",
    "Transaction proof (UTR, screenshots, bank statement)",
]


# --- transactions -------------------------------------------------------------

def _to_decimal(value: Any) -> Optional[Decimal]:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float, Decimal)):
        try:
            return Decimal(str(value))
        except InvalidOperation:
            return None
    if isinstance(value, str):
        text = value.strip().replace(",", "").replace("₹", "").replace("Rs.", "").replace("Rs", "").replace("INR", "").strip()
        if not text:
            return None
        try:
            return Decimal(text)
        except InvalidOperation:
            return None
    return None


def parse_timestamp(value: Any) -> Optional[dt.datetime]:
    """Parse ISO-8601 (with Z or offset) or dd/mm/yyyy hh:mm. None if unparseable."""
    if isinstance(value, dt.datetime):
        return value
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    match = DDMMYYYY_RE.match(text)
    if match:
        day, month, year, hour, minute, second = match.groups()
        try:
            return dt.datetime(int(year), int(month), int(day), int(hour or 0), int(minute or 0), int(second or 0))
        except ValueError:
            return None
    iso = text[:-1] + "+00:00" if text.endswith("Z") else text
    try:
        return dt.datetime.fromisoformat(iso)
    except ValueError:
        return None


def validate_txn(txn: Any) -> Dict[str, Any]:
    """Validate one transaction. Returns the txn plus ``valid`` and ``issues``."""
    issues: List[str] = []
    if not isinstance(txn, dict):
        return {"valid": False, "issues": ["not_an_object"]}
    utr = str(txn.get("utr", "") or "").strip()
    if not UTR_RE.match(utr):
        issues.append("utr_invalid")
    amount = _to_decimal(txn.get("amount"))
    if amount is None:
        issues.append("amount_not_numeric")
    elif not AMOUNT_MIN <= amount <= AMOUNT_MAX:
        issues.append("amount_out_of_range")
    if parse_timestamp(txn.get("timestamp")) is None:
        issues.append("timestamp_unparseable")
    payee = str(txn.get("payee", "") or "").strip()
    if not payee:
        issues.append("payee_missing")
    out: Dict[str, Any] = {
        "utr": utr,
        "amount": float(amount) if amount is not None else txn.get("amount"),
        "payee": payee,
        "timestamp": str(txn.get("timestamp", "") or ""),
        "app": str(txn.get("app", "") or ""),
        "valid": not issues,
        "issues": issues,
    }
    if amount is not None and amount == amount.to_integral_value():
        out["amount"] = int(amount)
    return out


def validate_fields(txns: Any) -> List[Dict[str, Any]]:
    """Validate a list of transactions; every entry gets ``valid`` and ``issues``."""
    if not isinstance(txns, list):
        return []
    return [validate_txn(t) for t in txns]


# --- e-Zero FIR -------------------------------------------------------------------

def lookup_ezero_threshold(state: Any) -> Dict[str, Any]:
    name = str(state or "").strip()
    entry = EZERO_THRESHOLDS.get(name.lower())
    if entry:
        return {
            "state": name,
            "thresholdInr": entry["thresholdInr"],
            "note": "e-Zero FIR is registered automatically for cyber financial fraud of Rs %s or more reported on 1930/NCRP."
                    % format(entry["thresholdInr"], ","),
            "sourceUrl": entry["sourceUrl"],
        }
    return {"state": name, "thresholdInr": None, "note": EZERO_DEFAULT_NOTE, "sourceUrl": EZERO_DEFAULT_SOURCE}


# --- MRM ------------------------------------------------------------------------

def _amount_by_payee(txns: List[Dict[str, Any]]) -> Dict[str, Decimal]:
    totals: Dict[str, Decimal] = {}
    for txn in txns:
        amount = _to_decimal(txn.get("amount")) or Decimal("0")
        payee = str(txn.get("payee", "") or "").strip().lower() or "unknown"
        totals[payee] = totals.get(payee, Decimal("0")) + amount
    return totals


def mrm_eligibility(confirmed_txns: Any, frozen_amount_by_account: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Mule Account Refund Mechanism rule.

    Eligible when some money is frozen (or, if unknown, when there is at least one
    confirmed transaction, so the guardian is walked through the checklist).
    FIR is mandatory when the amount in any single account exceeds Rs 50,000.
    """
    txns = [t for t in (confirmed_txns or []) if isinstance(t, dict)]
    if frozen_amount_by_account:
        per_account = {str(k): _to_decimal(v) or Decimal("0") for k, v in frozen_amount_by_account.items()}
        eligible = any(v > 0 for v in per_account.values())
        basis = "frozen"
    else:
        per_account = _amount_by_payee(txns)
        eligible = bool(txns)
        basis = "confirmed"
    max_single = max(per_account.values()) if per_account else Decimal("0")
    fir_required = max_single > MRM_SINGLE_ACCOUNT_LIMIT
    checklist = list(MRM_CHECKLIST_BASE)
    if fir_required:
        checklist.append("FIR copy (mandatory: more than Rs 50,000 in a single account)")
    else:
        checklist.append("No FIR needed (Rs 50,000 or less in a single account); NCRP complaint is enough")
    rule = ("amount in a single account > Rs 50,000 -> FIR mandatory" if fir_required
            else "amount in a single account <= Rs 50,000 -> no FIR required")
    return {
        "eligible": bool(eligible),
        "firRequired": bool(fir_required),
        "checklist": checklist,
        "portal": MRM_PORTAL,
        "rule": rule,
        "basis": basis,
        "maxSingleAccountInr": int(max_single) if max_single == max_single.to_integral_value() else float(max_single),
    }


# --- NCRP narrative -----------------------------------------------------------------

def ncrp_narrative_ok(text: Any) -> Tuple[bool, List[str]]:
    reasons: List[str] = []
    if not isinstance(text, str):
        return False, ["not_a_string"]
    if len(text) < NARRATIVE_MIN_LEN:
        reasons.append("too_short")
    if len(text) > NARRATIVE_MAX_LEN:
        reasons.append("too_long")
    if not text or not NARRATIVE_ALLOWED_RE.match(text):
        reasons.append("disallowed_characters")
    return not reasons, reasons


_REPLACEMENTS = {
    "₹": "Rs ", "&": " and ", "@": " at ", "/": " ", "-": " ", "_": " ", ":": " ", ";": ",", "(": ",", ")": ",",
    "'": "", '"': "", "\r": "\n", "\t": " ", "!": ".", "?": ".", "%": " percent", "+": " plus ",
}


def sanitize_narrative(text: Any) -> str:
    """Replace disallowed characters, collapse whitespace, pad to >= 200 chars, cap length."""
    raw = "" if text is None else str(text)
    for old, new in _REPLACEMENTS.items():
        raw = raw.replace(old, new)
    raw = _DISALLOWED_CHAR_RE.sub(" ", raw)
    raw = re.sub(r"[ ]{2,}", " ", raw)
    raw = re.sub(r"\n{2,}", "\n", raw)
    raw = re.sub(r" ,", ",", raw).strip()
    while len(raw) < NARRATIVE_MIN_LEN:
        raw = (raw + " " if raw else "") + NEUTRAL_PAD_SENTENCE
    if len(raw) > NARRATIVE_MAX_LEN:
        raw = raw[:NARRATIVE_MAX_LEN].rstrip()
    if not raw.endswith("."):
        raw = raw + "."
    return raw
