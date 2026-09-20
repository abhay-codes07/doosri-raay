"""Pure, deterministic recovery rules. No AWS, no LLM. Unit-tested.

Rules as data: every legal/operational fact (e-Zero FIR thresholds per state, the SC direction,
MRM rules, NCRP form rules, the acknowledgement-number note) lives in ``rules_data.json`` next to
this file, each entry with ``operator``/``value`` where a number is compared, a bilingual ``label``,
``source {outlet, date, url}``, the ``quote`` as reported and a ``caveat``. This module loads the
JSON at import and evaluates from it; nothing legal is hard-coded in Python.

- validate_fields: reference on one of three rails - UPI/IMPS 12 digits (``^\d{12}$``) or
  NEFT/RTGS 16-22 alphanumerics (``^[A-Z0-9]{16,22}$``, upper-cased first); amount numeric
  1..1e8, timestamp parseable (ISO-8601 or dd/mm/yyyy hh:mm), payee non-empty. Never auto-accepts.
- lookup_ezero_threshold / mrm_eligibility / ncrp_facts / validate_ack: evaluated from the JSON.
- ncrp_narrative_ok / sanitize_narrative / narrative_consistent: NCRP portal narrative constraints.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import re
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Optional, Tuple

UTR_RE = re.compile(r"^\d{12}$")
NEFT_RTGS_RE = re.compile(r"^[A-Z0-9]{16,22}$")
RAIL_UPI_IMPS = "upi_imps"
RAIL_NEFT_RTGS = "neft_rtgs"
RAIL_UNKNOWN = "unknown"
AMOUNT_MIN = Decimal("1")
AMOUNT_MAX = Decimal("100000000")  # 10,00,00,000
MAX_FIELD_LEN = 200  # every free-text txn field is capped (400 KB item limit, prompt size)
NARRATIVE_ALLOWED_RE = re.compile(r"^[A-Za-z0-9 ,.\n]+$")
_DISALLOWED_CHAR_RE = re.compile(r"[^A-Za-z0-9 ,.\n]")
DDMMYYYY_RE = re.compile(r"^(\d{1,2})/(\d{1,2})/(\d{4})(?:[ T](\d{1,2}):(\d{2})(?::(\d{2}))?)?$")

RULES_DATA_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "rules_data.json")


def load_rules(path: Optional[str] = None) -> Dict[str, Any]:
    with open(path or RULES_DATA_PATH, "r", encoding="utf-8") as fh:
        return json.load(fh)


RULES: Dict[str, Any] = load_rules()

# --- evaluator ----------------------------------------------------------------------

_OPERATORS = {
    ">=": lambda a, b: a >= b,
    ">": lambda a, b: a > b,
    "<=": lambda a, b: a <= b,
    "<": lambda a, b: a < b,
    "==": lambda a, b: a == b,
    "!=": lambda a, b: a != b,
}


def evaluate(entry: Dict[str, Any], actual: Any) -> bool:
    """Apply ``entry.operator`` to ``actual`` against ``entry.value`` (numbers compared as Decimal)."""
    op = _OPERATORS.get(str(entry.get("operator", "")))
    if op is None:
        raise ValueError("rule entry has no operator: %r" % (entry.get("label") or entry))
    expected = entry.get("value")
    if isinstance(expected, bool) or isinstance(actual, bool):
        return op(bool(actual), bool(expected))
    if isinstance(expected, (int, float)):
        value = _to_decimal(actual)
        if value is None:
            return False
        return op(value, Decimal(str(expected)))
    return op(actual, expected)


def rule_entries() -> List[Tuple[str, Dict[str, Any]]]:
    """Every cited entry (path, entry) in the data file, for tests and the sources manifest."""
    out: List[Tuple[str, Dict[str, Any]]] = []

    def walk(node: Any, path: str) -> None:
        if isinstance(node, dict):
            if isinstance(node.get("source"), dict) and "quote" in node:
                out.append((path, node))
            for key, value in node.items():
                walk(value, "%s.%s" % (path, key) if path else key)
        elif isinstance(node, list):
            for i, value in enumerate(node):
                walk(value, "%s[%d]" % (path, i))

    walk(RULES, "")
    return out


# --- sources (press reports; never law) ------------------------------------------

def source(outlet: str, date: Optional[str], url: str) -> Dict[str, Any]:
    return {"outlet": outlet, "date": date, "url": url}


def caveat_for(src: Dict[str, Any]) -> str:
    """'Reported by <outlet> on <date>; confirm with 1930 before relying on it'."""
    when = " on %s" % src["date"] if src.get("date") else ""
    return "Reported by %s%s; %s" % (src.get("outlet", "the press"), when, RULES.get("caveatSuffix", "confirm with 1930 before relying on it"))


def _cited(entry: Dict[str, Any]) -> Dict[str, Any]:
    """The citation block every artifact carries: label, source, quote, caveat."""
    src = dict(entry["source"])
    return {
        "label": dict(entry.get("label") or {}),
        "source": src,
        "quote": entry.get("quote"),
        "caveat": entry.get("caveat") or caveat_for(src),
    }


_EZERO = RULES["ezeroFir"]
_MRM = RULES["mrm"]
_NCRP = RULES["ncrp"]
_NARRATIVE = RULES.get("narrative", {})

SOURCES: Dict[str, Dict[str, Any]] = {
    **{state: dict(entry["source"]) for state, entry in _EZERO["states"].items()},
    "sc_direction": dict(_EZERO["scDirection"]["source"]),
    "mrm_primary": dict(_MRM["noFirUpTo"]["source"]),
    "mrm_secondary": dict(_MRM["firMandatoryAbove"]["source"]),
    "ncrp_form": dict(_NCRP["narrativeMinChars"]["source"]),
    "ncrp_ack": dict(_NCRP["ackNumber"]["source"]),
}

SC_DIRECTION_TEXT = _EZERO["scDirection"]["label"]["en"]
EZERO_THRESHOLDS: Dict[str, Dict[str, Any]] = {
    state: {"thresholdInr": entry["value"], "comparison": entry["operator"], "source": dict(entry["source"])}
    for state, entry in _EZERO["states"].items()
}
EZERO_DEFAULT_NOTE = _EZERO["defaultNote"]["en"]
EZERO_DEFAULT_SOURCE = _EZERO["scDirection"]["source"]["url"]
NEUTRAL_PAD_SENTENCE = _NARRATIVE.get(
    "padSentence",
    "The complainant requests that the transactions be traced and the beneficiary accounts be frozen "
    "at the earliest so that the amount can be recovered.",
)
NARRATIVE_MIN_LEN = int(_NCRP["narrativeMinChars"]["value"])
NARRATIVE_MAX_LEN = int(_NARRATIVE.get("maxChars", 1500))
MRM_SINGLE_ACCOUNT_LIMIT = Decimal(str(_MRM["firMandatoryAbove"]["value"]))
MRM_PORTAL = _MRM["portal"]
NCRP_PORTAL = _NCRP["portal"]
MRM_CHECKLIST_BASE = list(_MRM["checklist"])
ACK_DIGITS = int(_NCRP["ackNumber"]["value"])
ACK_RE = re.compile(r"^\d{%d}$" % ACK_DIGITS)
ACK_PREFIX = str(_NCRP["ackNumber"]["prefix"])
ACK_WARNING = _NCRP["ackNumber"]["warning"]

NCRP_FORM_RULES: Dict[str, Any] = {
    "narrativeMinChars": NARRATIVE_MIN_LEN,
    "narrativeNoSpecialCharacters": True,
    "transactionIdDigits": int(_NCRP["transactionIdDigits"]["value"]),
    "idUploadRequired": bool(_NCRP["idUploadRequired"]["value"]),
    "ackDigits": ACK_DIGITS,
    "ackPrefix": ACK_PREFIX,
}


# --- transactions -------------------------------------------------------------

def _to_decimal(value: Any) -> Optional[Decimal]:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float, Decimal)):
        try:
            result = Decimal(str(value))
        except InvalidOperation:
            return None
        return result if result.is_finite() else None  # NaN / inf are "not numeric", never a 500
    if isinstance(value, str):
        text = value.strip().replace(",", "").replace("₹", "").replace("Rs.", "").replace("Rs", "").replace("INR", "").strip()
        if not text:
            return None
        try:
            result = Decimal(text)
        except InvalidOperation:
            return None
        return result if result.is_finite() else None
    return None


def _capped(value: Any, limit: int = MAX_FIELD_LEN) -> str:
    return str(value or "")[:limit]


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
    utr, rail = classify_reference(_capped(txn.get("utr", "")))
    if rail == RAIL_UNKNOWN:
        issues.append("utr_invalid")
    amount = _to_decimal(txn.get("amount"))
    if amount is None:
        issues.append("amount_not_numeric")
    elif not AMOUNT_MIN <= amount <= AMOUNT_MAX:
        issues.append("amount_out_of_range")
    timestamp = _capped(txn.get("timestamp", ""))
    if parse_timestamp(timestamp) is None:
        issues.append("timestamp_unparseable")
    payee = _capped(txn.get("payee", "")).strip()
    if not payee:
        issues.append("payee_missing")
    raw_amount = txn.get("amount")
    out: Dict[str, Any] = {
        "utr": utr,
        "rail": rail,
        "amount": float(amount) if amount is not None else (_capped(raw_amount) if isinstance(raw_amount, str) else None),
        "payee": payee,
        "timestamp": timestamp,
        "app": _capped(txn.get("app", "")),
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
        "caveat": _NCRP["ackNumber"].get("caveat") or caveat_for(SOURCES["ncrp_ack"]),
        "ackWarning": ACK_WARNING,
        "citations": {key: _cited(_NCRP[key]) for key in ("narrativeMinChars", "transactionIdDigits",
                                                          "idUploadRequired", "ackNumber")},
    }


# --- e-Zero FIR -------------------------------------------------------------------

def lookup_ezero_threshold(state: Any, amount: Any = None) -> Dict[str, Any]:
    """e-Zero FIR rule for a state, evaluated from ``rules_data.json``. When ``amount`` is given,
    ``applies`` says whether the state's threshold is met (None when the state has no entry)."""
    name = str(state or "").strip()
    entry = _EZERO["states"].get(name.lower())
    sc_entry = _EZERO["scDirection"]
    sc = {"text": sc_entry["label"]["en"], **_cited(sc_entry)}
    if entry:
        src = entry["source"]
        wording = "more than" if entry["operator"] == ">" else "of"
        return {
            "state": name,
            "thresholdInr": entry["value"],
            "comparison": entry["operator"],
            "applies": evaluate(entry, amount) if amount is not None else None,
            "note": "e-Zero FIR is registered automatically for cyber financial fraud %s Rs %s%s reported on 1930/NCRP."
                    % (wording, format(entry["value"], ","), "" if entry["operator"] == ">" else " or more"),
            "label": dict(entry["label"]),
            "quote": entry["quote"],
            "sourceUrl": src["url"],
            "source": dict(src),
            "caveat": entry.get("caveat") or caveat_for(src),
            "scDirection": sc,
        }
    return {
        "state": name,
        "thresholdInr": None,
        "comparison": None,
        "applies": None,
        "note": EZERO_DEFAULT_NOTE,
        "label": dict(_EZERO["defaultNote"]),
        "quote": sc_entry["quote"],
        "sourceUrl": EZERO_DEFAULT_SOURCE,
        "source": dict(sc_entry["source"]),
        "caveat": sc_entry.get("caveat") or caveat_for(sc_entry["source"]),
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
    fir_entry = _MRM["firMandatoryAbove"]
    no_fir_entry = _MRM["noFirUpTo"]
    fir_required = evaluate(fir_entry, max_single)
    checklist = list(MRM_CHECKLIST_BASE)
    checklist.append(_MRM["checklistFir"] if fir_required else _MRM["checklistNoFir"])
    limit = format(int(fir_entry["value"]), ",")
    rule = ("amount in a single account > Rs %s -> FIR mandatory" % limit if fir_required
            else "amount in a single account <= Rs %s -> no FIR required, police report plus indemnity bond" % limit)
    applied = fir_entry if fir_required else no_fir_entry
    return {
        "eligible": bool(eligible),
        "firRequired": bool(fir_required),
        "checklist": checklist,
        "portal": MRM_PORTAL,
        "rule": rule,
        "label": dict(applied["label"]),
        "quote": applied["quote"],
        "basis": basis,
        "maxSingleAccountInr": int(max_single) if max_single == max_single.to_integral_value() else float(max_single),
        "source": dict(SOURCES["mrm_primary"]),
        "sources": [dict(SOURCES["mrm_primary"]), dict(SOURCES["mrm_secondary"])],
        "caveat": no_fir_entry.get("caveat") or caveat_for(SOURCES["mrm_primary"]),
        "citations": {key: _cited(_MRM[key]) for key in ("noFirUpTo", "firMandatoryAbove", "ackRequired")},
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
