"""Pure, deterministic recovery rules. No AWS, no LLM. Unit-tested.

- validate_fields: reference on one of three rails - UPI/IMPS 12 digits (``^\\d{12}$``) or
  NEFT/RTGS 16-22 alphanumerics (``^[A-Z0-9]{16,22}$``, upper-cased first); amount numeric
  1..1e8, timestamp parseable (ISO-8601 or dd/mm/yyyy hh:mm), payee non-empty. Never auto-accepts.
- lookup_ezero_threshold: e-Zero FIR thresholds by state, each with its press ``source`` and a ``caveat``.
- mrm_eligibility: <= 50,000 in a single account -> no FIR; > 50,000 -> FIR mandatory (with sources).
- ncrp_facts / validate_ack: NCRP portal form rules and the 14-digit acknowledgement number.
- ncrp_narrative_ok / sanitize_narrative: NCRP portal narrative constraints.

Every legal/threshold fact carries ``source`` {outlet, date, url} and a ``caveat`` string so the
UI can render "Source: outlet, date" and never present press reports as law.
"""
from __future__ import annotations

import datetime as dt
import re
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Optional, Tuple

UTR_RE = re.compile(r"^\d{12}$")
NEFT_RTGS_RE = re.compile(r"^[A-Z0-9]{16,22}$")
RAIL_UPI_IMPS = "upi_imps"
RAIL_NEFT_RTGS = "neft_rtgs"
RAIL_UNKNOWN = "unknown"
ACK_RE = re.compile(r"^\d{14}$")
ACK_PREFIX = "329"
ACK_WARNING = "Ack numbers reported in the press start with 329; double-check"
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


# --- sources (press reports; never law) ------------------------------------------

def source(outlet: str, date: Optional[str], url: str) -> Dict[str, Any]:
    return {"outlet": outlet, "date": date, "url": url}


def caveat_for(src: Dict[str, Any]) -> str:
    """'Reported by <outlet> on <date>; confirm with 1930 before relying on it'."""
    when = " on %s" % src["date"] if src.get("date") else ""
    return "Reported by %s%s; confirm with 1930 before relying on it" % (src.get("outlet", "the press"), when)


SOURCES: Dict[str, Dict[str, Any]] = {
    "haryana": source("Hindustan Times", "25 Jun 2026",
                      "https://www.hindustantimes.com/cities/chandigarh-news/haryana-to-lodge-e-zero-fir-in-cyber-financial-fraud-cases-101782412687221.html"),
    "rajasthan": source("Times of India", "23 Jul 2026",
                        "https://timesofindia.indiatimes.com/city/jaipur/cyber-fraud-of-rs-1l-or-more-to-trigger-automatic-e-zero-fir-in-state/amp_articleshow/132591321.cms"),
    "punjab": source("New Indian Express", "29 Jul 2026",
                     "https://www.newindianexpress.com/india/2026/Jul/29/punjab-police-launches-e-zero-fir-mechanism-for-swift-action-in-cyber-fraud-cases"),
    "sc_direction": source("New Indian Express", "4 Aug 2026",
                           "https://www.newindianexpress.com/india/2026/Aug/04/sc-issues-13-point-directions-to-fight-digital-arrest-scams"),
    "mrm_primary": source("Deccan Chronicle", None,
                          "https://www.deccanchronicle.com/southern-states/telangana/cybercrime-victims-to-get-refunds-online-1962253"),
    "mrm_secondary": source("Free Press Journal", None,
                            "https://www.freepressjournal.in/mumbai/relief-for-cyber-scam-victims-mha-launches-online-money-restoration-module-to-recover-frozen-funds"),
    "ncrp_form": source("National Cyber Crime Reporting Portal (cybercrime.gov.in)", None,
                        "https://cybercrime.gov.in/Webform/Crime_AuthoLogin.aspx"),
    "ncrp_ack": source("The Hindu (Chennai)", None,
                       "https://www.thehindu.com/news/cities/chennai/how-to-lodge-a-cybercrime-complaint/article69923101.ece"),
}

SC_DIRECTION_TEXT = "Supreme Court directed all States/UTs to adopt e-Zero FIR (13-point directions, 4 Aug 2026)"

EZERO_THRESHOLDS: Dict[str, Dict[str, Any]] = {
    "haryana": {"thresholdInr": 100000, "comparison": ">=", "source": SOURCES["haryana"]},
    "rajasthan": {"thresholdInr": 100000, "comparison": ">=", "source": SOURCES["rajasthan"]},
    "punjab": {"thresholdInr": 500000, "comparison": ">", "source": SOURCES["punjab"]},
}
EZERO_DEFAULT_NOTE = "Check with 1930; SC ordered all states to adopt e-Zero FIR (Aug 2026)"
EZERO_DEFAULT_SOURCE = SOURCES["sc_direction"]["url"]
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

NCRP_FORM_RULES: Dict[str, Any] = {
    "narrativeMinChars": NARRATIVE_MIN_LEN,
    "narrativeNoSpecialCharacters": True,
    "transactionIdDigits": 12,
    "idUploadRequired": True,
    "ackDigits": 14,
    "ackPrefix": ACK_PREFIX,
}


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


def classify_reference(value: Any) -> Tuple[str, str]:
    """Return (normalised reference, rail). Rail is ``upi_imps`` for a 12-digit UTR, ``neft_rtgs``
    for a 16-22 character alphanumeric reference (upper-cased), else ``unknown``."""
    ref = str(value or "").strip()
    if UTR_RE.match(ref):
        return ref, RAIL_UPI_IMPS
    upper = ref.upper()
    if NEFT_RTGS_RE.match(upper):
        return upper, RAIL_NEFT_RTGS
    return ref, RAIL_UNKNOWN


def validate_txn(txn: Any) -> Dict[str, Any]:
    """Validate one transaction. Returns the txn plus ``rail``, ``valid`` and ``issues``."""
    issues: List[str] = []
    if not isinstance(txn, dict):
        return {"valid": False, "issues": ["not_an_object"]}
    utr, rail = classify_reference(txn.get("utr", ""))
    if rail == RAIL_UNKNOWN:
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
        "rail": rail,
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
    """Validate a list of transactions; every entry gets ``rail``, ``valid`` and ``issues``."""
    if not isinstance(txns, list):
        return []
    return [validate_txn(t) for t in txns]


ISSUE_TEXT = {
    "utr_invalid": "reference must be a 12-digit UTR (UPI/IMPS) or a 16-22 character NEFT/RTGS reference",
    "amount_not_numeric": "amount must be a number",
    "amount_out_of_range": "amount must be between Rs 1 and Rs 10,00,00,000",
    "timestamp_unparseable": "timestamp must be ISO-8601 or dd/mm/yyyy hh:mm",
    "payee_missing": "payee is required",
    "not_an_object": "row is not an object",
}


def describe_issues(validated: List[Dict[str, Any]]) -> str:
    """'Row 2: utr_invalid (reference must be ...); Row 3: ...' for every invalid row (1-based)."""
    parts = []
    for i, t in enumerate(validated, 1):
        if t.get("valid"):
            continue
        parts.append("Row %d: %s" % (i, ", ".join("%s (%s)" % (code, ISSUE_TEXT.get(code, code)) for code in t.get("issues", []))))
    return "; ".join(parts)


# --- NCRP acknowledgement ------------------------------------------------------------

def validate_ack(value: Any) -> Tuple[Optional[str], Optional[str]]:
    """Return (ackNo, warning). ackNo is None when not 14 digits; a valid number that does not
    start with 329 is accepted with a warning."""
    ack = str(value or "").strip()
    if not ACK_RE.match(ack):
        return None, None
    return ack, (None if ack.startswith(ACK_PREFIX) else ACK_WARNING)


def ncrp_facts() -> Dict[str, Any]:
    """NCRP form rules with their sources, for the case artifacts (``artifacts.ncrp``)."""
    return {
        "portal": NCRP_PORTAL,
        "rules": dict(NCRP_FORM_RULES),
        "source": dict(SOURCES["ncrp_form"]),
        "ackSource": dict(SOURCES["ncrp_ack"]),
        "caveat": caveat_for(SOURCES["ncrp_ack"]),
        "ackWarning": ACK_WARNING,
    }


# --- e-Zero FIR -------------------------------------------------------------------

def lookup_ezero_threshold(state: Any) -> Dict[str, Any]:
    name = str(state or "").strip()
    entry = EZERO_THRESHOLDS.get(name.lower())
    sc = {"text": SC_DIRECTION_TEXT, "source": dict(SOURCES["sc_direction"]),
          "caveat": caveat_for(SOURCES["sc_direction"])}
    if entry:
        src = entry["source"]
        wording = "more than" if entry["comparison"] == ">" else "of"
        return {
            "state": name,
            "thresholdInr": entry["thresholdInr"],
            "comparison": entry["comparison"],
            "note": "e-Zero FIR is registered automatically for cyber financial fraud %s Rs %s%s reported on 1930/NCRP."
                    % (wording, format(entry["thresholdInr"], ","), "" if entry["comparison"] == ">" else " or more"),
            "sourceUrl": src["url"],
            "source": dict(src),
            "caveat": caveat_for(src),
            "scDirection": sc,
        }
    return {
        "state": name,
        "thresholdInr": None,
        "comparison": None,
        "note": EZERO_DEFAULT_NOTE,
        "sourceUrl": EZERO_DEFAULT_SOURCE,
        "source": dict(SOURCES["sc_direction"]),
        "caveat": caveat_for(SOURCES["sc_direction"]),
        "scDirection": sc,
    }


# --- MRM ------------------------------------------------------------------------

def _amount_by_payee(txns: List[Dict[str, Any]]) -> Dict[str, Decimal]:
    totals: Dict[str, Decimal] = {}
    for txn in txns:
        amount = _to_decimal(txn.get("amount")) or Decimal("0")
        payee = str(txn.get("payee", "") or "").strip().lower() or "unknown"
        totals[payee] = totals.get(payee, Decimal("0")) + amount
    return totals


def mrm_eligibility(confirmed_txns: Any, frozen_amount_by_account: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Money Restoration Module rule.

    Eligible when some money is frozen (or, if unknown, when there is at least one
    confirmed transaction, so the guardian is walked through the checklist).
    FIR is mandatory when the amount in any single account exceeds Rs 50,000; at or below
    that a police report plus an indemnity bond is enough.
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
        checklist.append("No FIR needed (Rs 50,000 or less in a single account); police report and indemnity bond are enough")
    rule = ("amount in a single account > Rs 50,000 -> FIR mandatory" if fir_required
            else "amount in a single account <= Rs 50,000 -> no FIR required, police report plus indemnity bond")
    return {
        "eligible": bool(eligible),
        "firRequired": bool(fir_required),
        "checklist": checklist,
        "portal": MRM_PORTAL,
        "rule": rule,
        "basis": basis,
        "maxSingleAccountInr": int(max_single) if max_single == max_single.to_integral_value() else float(max_single),
        "source": dict(SOURCES["mrm_primary"]),
        "sources": [dict(SOURCES["mrm_primary"]), dict(SOURCES["mrm_secondary"])],
        "caveat": caveat_for(SOURCES["mrm_primary"]),
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


_NUMBER_RUN_RE = re.compile(r"\d{12,}")
_AMOUNT_RE = re.compile(r"\bRs\.?\s*([0-9][0-9,]*(?:\.\d+)?)", re.IGNORECASE)


def _amount_forms(value: Any) -> set:
    amount = _to_decimal(value)
    if amount is None:
        return set()
    forms = {str(amount.normalize()) if amount != amount.to_integral_value() else str(int(amount))}
    forms.add(format(int(amount), ",") if amount == amount.to_integral_value() else str(amount))
    return forms


def narrative_consistent(text: str, confirmed_txns: List[Dict[str, Any]]) -> Tuple[bool, List[str]]:
    """Every 12+-digit number and every 'Rs <amount>' in ``text`` must come from the confirmed rows
    (amounts may also be the total). Returns (ok, reasons)."""
    reasons: List[str] = []
    txns = [t for t in (confirmed_txns or []) if isinstance(t, dict)]
    refs = {str(t.get("utr", "")).strip().upper() for t in txns if t.get("utr")}
    for run in _NUMBER_RUN_RE.findall(text or ""):
        if run not in refs and not any(run in ref for ref in refs):
            reasons.append("foreign_reference:%s" % run)
    for ref in refs:
        if ref not in (text or "").upper():
            reasons.append("missing_reference:%s" % ref)
    allowed: set = set()
    total = Decimal("0")
    for t in txns:
        allowed |= _amount_forms(t.get("amount"))
        total += _to_decimal(t.get("amount")) or Decimal("0")
    allowed |= _amount_forms(total)
    allowed_plain = {a.replace(",", "") for a in allowed}
    for raw in _AMOUNT_RE.findall(text or ""):
        plain = raw.replace(",", "").rstrip(".")
        if plain and plain not in allowed_plain:
            reasons.append("foreign_amount:%s" % raw)
    return not reasons, reasons
