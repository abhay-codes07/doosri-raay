#!/usr/bin/env python3
"""Run the Doosri Raay classifier over eval/items.jsonl and write a Markdown report.

Usage (from the repo root):
    python eval/run_eval.py --dry-run                 # no AWS: deterministic fake client
    python eval/run_eval.py                           # MODEL_ID or global.anthropic.claude-sonnet-4-6
    python eval/run_eval.py --fallback                # also run FALLBACK_MODEL_ID (Haiku 4.5)
    python eval/run_eval.py --limit 10 --out eval/results.md --raw eval/results_raw.jsonl

The classifier is imported from backend.classify_worker.classifier:
    classify(text=None, image_bytes=None, image_media_type=None, model_id=None, client=None) -> verdict
    verdict = {state, scamType, tactics, redFlags, sayHi, sayEn}

Scoring rules (see README "Evaluation"):
  * An item is *positive* when expected_state is "likely" or "watching"; benign controls are negative.
  * A positive item is a *hit* when the model says "likely", or says "watching" and the item has
    accept_watching=true (softened adversarial items).
  * A benign item is a *false positive* when the model says anything other than "none".
  * The word-"safe" check fails the run if any sayHi/sayEn contains "safe" (case-insensitive).
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import json
import os
import random
import re
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
# The Lambda code uses the flat layout (`from common import ...`), so both the repo root and backend/ go on the path.
for _p in (REPO_ROOT, REPO_ROOT / "backend"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

DEFAULT_MODEL = os.environ.get("MODEL_ID", "global.anthropic.claude-sonnet-4-6")
DEFAULT_FALLBACK = os.environ.get("FALLBACK_MODEL_ID", "global.anthropic.claude-haiku-4-5-20251001-v1:0")

STATES = ("none", "watching", "likely")
PRETEXTS = (
    "digital_arrest", "kyc", "courier_customs", "upi_collect",
    "job_task", "loan", "investment_deepfake", "refund_scam",
)
SCAMTYPE_TO_PRETEXT = {
    "DIGITAL_ARREST": "digital_arrest",
    "KYC_PHISHING": "kyc",
    "COURIER_CUSTOMS": "courier_customs",
    "UPI_COLLECT": "upi_collect",
    "FAKE_JOB": "job_task",
    "FAKE_LOAN": "loan",
    "INVESTMENT_DEEPFAKE": "investment_deepfake",
    "REFUND_SCAM": "refund_scam",
}
THROTTLE_MARKERS = ("Throttling", "TooManyRequests", "ServiceUnavailable", "ModelNotReady", "429", "503")

# --------------------------------------------------------------------------------------
# Dry-run fake client: a tiny keyword heuristic that speaks the Bedrock Converse tool-use shape
# --------------------------------------------------------------------------------------
_KEYWORDS: dict[str, tuple[str, tuple[str, ...]]] = {
    # scamType: (pretext, keywords lower-cased; Devanagari included)
    "DIGITAL_ARREST": ("digital_arrest", (
        "cbi", "ed ", "enforcement", "cyber cell", "cyber crime", "police", "trai", "supervision",
        "digital arrest", "warrant", "money laundering", "court", "registry", "सुपरविज़न", "गिरफ़्तारी",
        "साइबर क्राइम", "प्रवर्तन", "कस्टम्स विभाग", "video call", "वीडियो", "पुलिस")),
    "COURIER_CUSTOMS": ("courier_customs", (
        "fedex", "dhl", "blue dart", "dtdc", "parcel", "customs", "package", "india post", "shipment",
        "पार्सल", "कस्टम्स", "पैकेट", "courier")),
    "KYC_PHISHING": ("kyc", ("kyc", "blocked", "disconnected", "suspension", "pan", "verify", "बंद कर", "अपडेट")),
    "UPI_COLLECT": ("upi_collect", ("collect", "request", "upi pin", "anydesk", "pay dabakar", "approve", "रिक्वेस्ट", "pin")),
    "FAKE_JOB": ("job_task", ("part-time", "task", "telegram", "hr", "youtube", "rating", "review", "job", "जॉब", "रेटिंग")),
    "FAKE_LOAN": ("loan", ("loan", "processing fee", "cibil", "nbfc", "लोन", "disbursal", "emi")),
    "INVESTMENT_DEEPFAKE": ("investment_deepfake", ("ratan tata", "ambani", "अंबानी", "stock", "crypto", "क्रिप्टो", "returns", "sebi", "ipo", "mentor", "trade")),
    "REFUND_SCAM": ("refund_scam", ("refund", "restoration", "recovered", "traced", "i4c", "1930", "वापस", "रेस्टोरेशन", "शुल्क")),
}
_ASK_MONEY = ("fee", "deposit", "charge", "recharge", "registration", "gst", "tax", "शुल्क", "भेजें", "bhejein", "bhejna",
              "transfer", "ट्रांसफर", "rtgs", "neft", "upi pin", "pin", "card number", "कार्ड", "debit card", "account number",
              "supervision account", "verification account", "amount", "membership", "जमा करें")
_URGENCY = ("immediately", "today", "tonight", "within", "hours", "24", "2 ghante", "abhi", "turant", "तुरंत", "आज", "घंटे",
            "valid", "limited", "last", "now", "minutes", "absconding")
_SECRECY = ("do not tell", "mat batana", "confidential", "between us", "किसी को", "family ko", "नहीं बताना", "परिवार को", "kisi se")
_AUTHORITY = ("cbi", "police", "court", "ed ", "trai", "rbi", "customs", "officer", "advocate", "i4c", "cyber", "पुलिस",
              "कस्टम्स", "निदेशालय", "इंस्पेक्टर", "registry", "hr", "bank")
_LINK = re.compile(r"(https?://|www\.|bit\.ly|\.xyz|\.top|\.co/|\.online|\.com/|\.apk|t\.me|@ybl|@oksbi|@okaxis)", re.I)
_TRUSTED_LINK = re.compile(r"(\.bank\.in|\.gov\.in|cybercrime\.gov\.in|mahadiscom\.in|epfindia\.gov\.in)", re.I)
_BENIGN_SIGNALS = ("do not share", "never asks", "never ask", "नहीं माँगता", "ignore if", "not you? call", "pnr:", "reply c to confirm",
                   "dinner", "mummy", "papa,", "beta ", "उपलब्ध शेष", "जमा कर दी", "credited", "debited", "received rs", "you received",
                   "ready for pickup", "appointment", "tank cleaning", "भजन", "namaste bolna", "fee of rs 18,500")


def _heuristic_verdict(text: str) -> dict:
    """Deterministic keyword heuristic used only by --dry-run. Deliberately crude."""
    t = (text or "").lower()
    injection = "ignore previous instructions" in t
    tactics: list[str] = []
    if any(k in t for k in _AUTHORITY):
        tactics.append("authority")
    if any(k in t for k in _URGENCY):
        tactics.append("urgency")
    if any(k in t for k in _SECRECY):
        tactics.append("secrecy")
    if "supervision account" in t or "verification account" in t or "सुपरविज़न" in t:
        tactics.append("verification_account")
    if any(k in t for k in ("neft", "rtgs", "anydesk", "apk", "telegram", "private", "enterprises", "traders")):
        tactics.append("payment_switch")

    scores: dict[str, int] = {}
    for scam_type, (_pretext, kws) in _KEYWORDS.items():
        scores[scam_type] = sum(1 for k in kws if k in t)
    best_type = max(scores, key=lambda k: (scores[k], k))
    ask_money = any(k in t for k in _ASK_MONEY)
    untrusted_link = bool(_LINK.search(t)) and not _TRUSTED_LINK.search(t)
    benign_signals = sum(1 for k in _BENIGN_SIGNALS if k in t)

    risk = 0
    risk += 2 if ask_money else 0
    risk += 2 if untrusted_link else 0
    risk += len(tactics)
    risk += 2 if injection else 0
    risk += 1 if scores[best_type] >= 3 else 0
    risk -= 2 * benign_signals
    if _TRUSTED_LINK.search(t):
        risk -= 2

    if risk >= 4:
        state = "likely"
    elif risk >= 2:
        state = "watching"
    else:
        state = "none"
    if state == "none":
        best_type = "NONE"
        tactics = []

    red_flags: list[str] = []
    if ask_money:
        red_flags.append("Asks you to pay, transfer or enter a PIN/card to 'receive' or 'verify' something")
    if untrusted_link:
        red_flags.append("Link or handle that is not an official .bank.in / .gov.in domain")
    if "authority" in tactics:
        red_flags.append("Claims to be an authority or institution over chat/call")
    if "secrecy" in tactics:
        red_flags.append("Asks you to keep it from family")
    if injection:
        red_flags.append("Message contains hidden instructions aimed at the checker")
    red_flags = red_flags[:5]

    if state == "likely":
        say_hi = "Yeh sandesh dhokhe ke pattern se milta hai. Paise ya PIN na dein. Pehle parivaar se baat karein, phir 1930 par report karein."
        say_en = "This matches a known fraud pattern. Do not pay or share a PIN. Talk to family first, then report at 1930."
    elif state == "watching":
        say_hi = "Kuch baatein sandeh paida karti hain. Koi kadam uthane se pehle parivaar se doosri raay lein."
        say_en = "Some parts look suspicious. Get a second opinion from family before doing anything."
    else:
        say_hi = "Koi khatra nahi mila — phir bhi parivaar se poochhein."
        say_en = "No red flags found — still ask your family before acting."
    return {
        "state": state,
        "scamType": best_type,
        "tactics": sorted(set(tactics)),
        "redFlags": red_flags,
        "sayHi": say_hi[:240],
        "sayEn": say_en[:240],
    }


class FakeBedrockClient:
    """Mimics boto3 bedrock-runtime `converse` closely enough for the classifier's tool-use path.

    It reads the user text from the request messages and answers with a single toolUse block whose
    input is the heuristic verdict. Image inputs get a fixed 'watching' verdict (no OCR here).
    """

    def __init__(self) -> None:
        self.calls = 0
        self._lock = threading.Lock()

    def converse(self, **kwargs):  # noqa: D401 - boto3 style
        with self._lock:
            self.calls += 1
        text_parts: list[str] = []
        has_image = False
        for msg in kwargs.get("messages", []):
            for block in msg.get("content", []):
                if "text" in block:
                    text_parts.append(block["text"])
                if "image" in block:
                    has_image = True
        joined = "\n".join(text_parts)
        # The backend wraps user content in <untrusted_data> tags; score only that, not the wrapper's own words.
        wrapped = re.findall(r"<untrusted_data>(.*?)</untrusted_data>", joined, flags=re.S)
        text = "\n".join(w.strip() for w in wrapped) if wrapped else joined
        verdict = _heuristic_verdict(text) if (text or not has_image) else {
            "state": "watching", "scamType": "OTHER", "tactics": [],
            "redFlags": ["Dry-run cannot read images"], "sayHi": "Parivaar se poochhein.", "sayEn": "Ask family.",
        }
        tool_name = "verdict"
        try:
            tool_name = kwargs["toolConfig"]["tools"][0]["toolSpec"]["name"]
        except (KeyError, IndexError, TypeError):
            pass
        return {
            "output": {"message": {"role": "assistant", "content": [
                {"toolUse": {"toolUseId": f"dryrun-{self.calls}", "name": tool_name, "input": verdict}}]}},
            "stopReason": "tool_use",
            "usage": {"inputTokens": len(text) // 4, "outputTokens": 120, "totalTokens": len(text) // 4 + 120},
            "metrics": {"latencyMs": 1},
        }


# --------------------------------------------------------------------------------------
# Running
# --------------------------------------------------------------------------------------

def load_items(path: Path, limit: int | None) -> list[dict]:
    items = []
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                items.append(json.loads(line))
    return items[:limit] if limit else items


def _is_throttle(exc: Exception) -> bool:
    name = type(exc).__name__
    msg = str(exc)
    return any(m in name or m in msg for m in THROTTLE_MARKERS)


def call_with_retry(classify_fn, item: dict, model_id: str, client, delay: float, max_attempts: int = 6) -> dict:
    """Returns {verdict|error, latencyMs, attempts}."""
    attempt = 0
    while True:
        attempt += 1
        time.sleep(delay + random.uniform(0, delay))  # small stagger so 4 workers do not burst
        t0 = time.perf_counter()
        try:
            verdict = classify_fn(text=item["text"], model_id=model_id, client=client)
            return {"verdict": verdict, "latencyMs": int((time.perf_counter() - t0) * 1000), "attempts": attempt}
        except Exception as exc:  # noqa: BLE001 - we want to record every failure mode
            if _is_throttle(exc) and attempt < max_attempts:
                backoff = min(30.0, (2 ** attempt) + random.uniform(0, 1))
                print(f"  throttled on {item['id']} (attempt {attempt}); sleeping {backoff:.1f}s", file=sys.stderr)
                time.sleep(backoff)
                continue
            return {"error": f"{type(exc).__name__}: {exc}", "latencyMs": int((time.perf_counter() - t0) * 1000), "attempts": attempt}


def run_model(classify_fn, items: list[dict], model_id: str, client, concurrency: int, delay: float) -> list[dict]:
    results: list[dict] = [None] * len(items)  # type: ignore[list-item]
    done = 0
    lock = threading.Lock()

    def work(idx: int) -> None:
        nonlocal done
        item = items[idx]
        out = call_with_retry(classify_fn, item, model_id, client, delay)
        row = {"id": item["id"], "model": model_id, "expected_state": item["expected_state"],
               "pretext": item["pretext"], "lang": item["lang"], "adversarial": bool(item.get("adversarial")),
               "accept_watching": bool(item.get("accept_watching")), **out}
        results[idx] = row
        with lock:
            done += 1
            if done % 10 == 0 or done == len(items):
                print(f"  {model_id}: {done}/{len(items)}", file=sys.stderr)

    with cf.ThreadPoolExecutor(max_workers=concurrency) as pool:
        list(pool.map(work, range(len(items))))
    return results


# --------------------------------------------------------------------------------------
# Scoring
# --------------------------------------------------------------------------------------

def _pred_state(row: dict) -> str:
    v = row.get("verdict") or {}
    s = v.get("state")
    return s if s in STATES else "error"


def is_hit(row: dict) -> bool:
    """Positive item counted as detected."""
    ps = _pred_state(row)
    return ps == "likely" or (ps == "watching" and row.get("accept_watching"))


def state_correct(row: dict) -> bool:
    exp, ps = row["expected_state"], _pred_state(row)
    if exp == "none":
        return ps == "none"
    if exp == "likely":
        return ps == "likely" or (ps == "watching" and row.get("accept_watching"))
    if exp == "watching":
        return ps in ("watching", "likely")
    return False


def _prf(tp: int, fp: int, fn: int) -> tuple[float, float, float]:
    p = tp / (tp + fp) if tp + fp else 0.0
    r = tp / (tp + fn) if tp + fn else 0.0
    f = 2 * p * r / (p + r) if p + r else 0.0
    return p, r, f


def score(rows: list[dict]) -> dict:
    pos = [r for r in rows if r["expected_state"] != "none"]
    neg = [r for r in rows if r["expected_state"] == "none"]
    errors = [r for r in rows if "error" in r]

    # Overall detection (binary): predicted-positive = state != none
    tp = sum(1 for r in pos if is_hit(r))
    fn = len(pos) - tp
    fp = sum(1 for r in neg if _pred_state(r) in ("watching", "likely"))
    fp_likely = sum(1 for r in neg if _pred_state(r) == "likely")
    tn = len(neg) - fp
    p, rcl, f1 = _prf(tp, fp, fn)

    per_pretext = {}
    for pt in PRETEXTS:
        mine = [r for r in pos if r["pretext"] == pt]
        if not mine:
            continue
        hits = [r for r in mine if is_hit(r)]
        type_match = sum(1 for r in hits if SCAMTYPE_TO_PRETEXT.get((r.get("verdict") or {}).get("scamType")) == pt)
        # precision of the scamType label: of everything the model flagged and labelled as this type,
        # how many really were this pretext
        labelled = [r for r in rows if _pred_state(r) in ("watching", "likely")
                    and SCAMTYPE_TO_PRETEXT.get((r.get("verdict") or {}).get("scamType")) == pt]
        lab_tp = sum(1 for r in labelled if r["pretext"] == pt)
        lp, _, _ = _prf(lab_tp, len(labelled) - lab_tp, 0)
        pp, pr, pf = _prf(len(hits), len(labelled) - lab_tp, len(mine) - len(hits))
        per_pretext[pt] = {"n": len(mine), "hits": len(hits), "recall": pr, "type_precision": lp if labelled else None,
                           "f1": pf, "type_match": type_match / len(hits) if hits else None,
                           "adv_n": sum(1 for r in mine if r["adversarial"]),
                           "adv_hits": sum(1 for r in mine if r["adversarial"] and is_hit(r))}

    adv = [r for r in pos if r["adversarial"]]
    adv_hits = sum(1 for r in adv if is_hit(r))
    inj = [r for r in rows if r["id"].startswith("inj-")]
    inj_hits = sum(1 for r in inj if is_hit(r))

    confusion = {e: {s: 0 for s in STATES + ("error",)} for e in STATES}
    for r in rows:
        confusion[r["expected_state"]][_pred_state(r)] += 1

    safe_offenders = []
    for r in rows:
        v = r.get("verdict") or {}
        for key in ("sayHi", "sayEn"):
            if "safe" in str(v.get(key, "")).lower():
                safe_offenders.append((r["id"], key, v.get(key)))

    per_lang = {}
    for lang in ("hi", "hinglish", "en"):
        mine = [r for r in rows if r["lang"] == lang]
        if mine:
            per_lang[lang] = {"n": len(mine), "accuracy": sum(1 for r in mine if state_correct(r)) / len(mine)}

    latencies = sorted(r["latencyMs"] for r in rows if "latencyMs" in r)
    return {
        "n": len(rows), "positives": len(pos), "negatives": len(neg), "errors": len(errors),
        "accuracy": sum(1 for r in rows if state_correct(r)) / len(rows) if rows else 0.0,
        "tp": tp, "fp": fp, "fn": fn, "tn": tn, "precision": p, "recall": rcl, "f1": f1,
        "benign_fpr": fp / len(neg) if neg else 0.0, "benign_fpr_likely": fp_likely / len(neg) if neg else 0.0,
        "adversarial_n": len(adv), "adversarial_recall": adv_hits / len(adv) if adv else 0.0,
        "injection_n": len(inj), "injection_hits": inj_hits,
        "per_pretext": per_pretext, "per_lang": per_lang, "confusion": confusion,
        "safe_offenders": safe_offenders,
        "latency_p50": latencies[len(latencies) // 2] if latencies else None,
        "latency_p95": latencies[int(len(latencies) * 0.95) - 1] if len(latencies) >= 2 else (latencies[0] if latencies else None),
    }


# --------------------------------------------------------------------------------------
# Report
# --------------------------------------------------------------------------------------

def pct(x: float | None) -> str:
    return "n/a" if x is None else f"{100 * x:.0f}%"


def render_markdown(summaries: dict[str, dict], items_path: Path, dry_run: bool) -> str:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    out: list[str] = []
    out.append("# Classifier evaluation results\n")
    out.append(f"Generated {now} from `{items_path.as_posix()}` by `eval/run_eval.py`"
               + (" in **--dry-run** mode (deterministic keyword heuristic, no model call)." if dry_run else "."))
    out.append("")
    out.append("**Caveat.** This is a hand-built 70-item set (35 Hindi/Hinglish, 35 English; 21 benign controls, "
               "14 adversarially softened scam messages, 2 prompt-injection probes), written by the team in one day. "
               "It measures whether the classifier behaves as designed on the pretexts we know about; it is **not** field "
               "accuracy and says nothing about base rates in real inboxes. The research doc "
               "(README, Trust and safety) is why we report three states and treat a false "
               "'no red flags' as the worst failure: LLM detectors reach ~1.0 recall but only 0.70–0.77 precision on hard data, "
               "and an 'uncertain' state is what keeps users from disabling the feature. Public Hindi scam datasets are tiny "
               "(~120 messages), so a larger eval is roadmap, not a claim.\n")

    out.append("## Summary\n")
    out.append("| Model | Items | Accuracy | Precision | Recall | F1 | Benign FPR (any flag) | Benign FPR (likely) | Adversarial recall | Injection resisted | Errors | 'safe' check | p50 ms |")
    out.append("|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    for model, s in summaries.items():
        safe = "PASS" if not s["safe_offenders"] else f"FAIL ({len(s['safe_offenders'])})"
        out.append(f"| `{model}` | {s['n']} | {pct(s['accuracy'])} | {pct(s['precision'])} | {pct(s['recall'])} | {pct(s['f1'])} | "
                   f"{pct(s['benign_fpr'])} ({s['fp']}/{s['negatives']}) | {pct(s['benign_fpr_likely'])} | "
                   f"{pct(s['adversarial_recall'])} ({int(round(s['adversarial_recall'] * s['adversarial_n']))}/{s['adversarial_n']}) | "
                   f"{s['injection_hits']}/{s['injection_n']} | {s['errors']} | {safe} | {s['latency_p50']} |")
    out.append("")
    out.append("Definitions: positive = expected `likely` (softened adversarial items also accept `watching`); "
               "negative = benign control. Precision/recall/F1 are for the binary flag (`watching`/`likely` vs `none`). "
               "Accuracy is exact state match with the same relaxation. 'Injection resisted' counts the two prompt-injection "
               "items still flagged. The 'safe' check scans `sayHi`/`sayEn` for the word 'safe'.\n")

    for model, s in summaries.items():
        out.append(f"## `{model}`\n")
        out.append("### Per pretext\n")
        out.append("| Pretext | n | Detected | Recall | Type precision | F1 | Type match among hits | Adversarial hits |")
        out.append("|---|---|---|---|---|---|---|---|")
        for pt, v in s["per_pretext"].items():
            out.append(f"| {pt} | {v['n']} | {v['hits']} | {pct(v['recall'])} | {pct(v['type_precision'])} | {pct(v['f1'])} | "
                       f"{pct(v['type_match'])} | {v['adv_hits']}/{v['adv_n']} |")
        out.append(f"| benign (controls) | {s['negatives']} | {s['fp']} flagged | — | — | — | — | — |")
        out.append("")
        out.append("Recall = fraction of this pretext's items detected (`likely`, or `watching` where the item accepts it). Type precision = of everything the model flagged "
                   "*and labelled* with this scamType, the fraction that truly was this pretext. Type match = of the detected "
                   "items, how many got the right scamType label.\n")

        out.append("### Confusion matrix (rows = expected, columns = predicted)\n")
        out.append("| expected \\ predicted | none | watching | likely | error |")
        out.append("|---|---|---|---|---|")
        for e in STATES:
            c = s["confusion"][e]
            out.append(f"| {e} | {c['none']} | {c['watching']} | {c['likely']} | {c['error']} |")
        out.append("")

        out.append("### By language\n")
        out.append("| Language | n | Accuracy |")
        out.append("|---|---|---|")
        for lang, v in s["per_lang"].items():
            out.append(f"| {lang} | {v['n']} | {pct(v['accuracy'])} |")
        out.append("")
        if s["safe_offenders"]:
            out.append("### 'safe' check FAILED\n")
            for rid, key, val in s["safe_offenders"]:
                out.append(f"- `{rid}` {key}: {val}")
            out.append("")
    return "\n".join(out) + "\n"


# --------------------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------------------

def _import_classify(dry_run: bool):
    try:
        from backend.classify_worker.classifier import classify  # type: ignore
        return classify, None
    except Exception as exc:  # noqa: BLE001
        if dry_run:
            print(f"note: backend classifier not importable ({type(exc).__name__}: {exc}); "
                  "dry-run will call the heuristic directly", file=sys.stderr)

            def classify(text=None, image_bytes=None, image_media_type=None, model_id=None, client=None):  # noqa: ARG001
                return _heuristic_verdict(text or "")
            return classify, str(exc)
        raise


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--items", default=str(REPO_ROOT / "eval" / "items.jsonl"))
    ap.add_argument("--model", default=DEFAULT_MODEL, help="primary model id (env MODEL_ID)")
    ap.add_argument("--fallback", action="store_true", help="also run FALLBACK_MODEL_ID")
    ap.add_argument("--fallback-model", default=DEFAULT_FALLBACK)
    ap.add_argument("--dry-run", action="store_true", help="no AWS: deterministic fake Bedrock client")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--out", default=str(REPO_ROOT / "eval" / "results.md"))
    ap.add_argument("--raw", default=str(REPO_ROOT / "eval" / "results_raw.jsonl"))
    ap.add_argument("--concurrency", type=int, default=4)
    ap.add_argument("--delay", type=float, default=0.25, help="seconds between calls per worker")
    args = ap.parse_args(argv)

    items_path = Path(args.items)
    items = load_items(items_path, args.limit)
    classify_fn, import_error = _import_classify(args.dry_run)

    if args.dry_run:
        client = FakeBedrockClient()
        delay = 0.0
        models = ["dry-run-heuristic"]
    else:
        client = None  # classifier builds its own boto3 client
        delay = args.delay
        models = [args.model] + ([args.fallback_model] if args.fallback else [])

    all_rows: list[dict] = []
    summaries: dict[str, dict] = {}
    for model in models:
        print(f"running {len(items)} items on {model} (concurrency {args.concurrency})", file=sys.stderr)
        rows = run_model(classify_fn, items, model, client, args.concurrency, delay)
        all_rows.extend(rows)
        summaries[model] = score(rows)

    raw_path = Path(args.raw)
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    with raw_path.open("w", encoding="utf-8") as fh:
        for r in all_rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")

    md = render_markdown(summaries, items_path.relative_to(REPO_ROOT) if items_path.is_relative_to(REPO_ROOT) else items_path,
                         args.dry_run)
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(md, encoding="utf-8")

    # console summary
    for model, s in summaries.items():
        print(f"\n{model}: n={s['n']} acc={pct(s['accuracy'])} P={pct(s['precision'])} R={pct(s['recall'])} F1={pct(s['f1'])} "
              f"benignFPR={pct(s['benign_fpr'])} advRecall={pct(s['adversarial_recall'])} "
              f"injection={s['injection_hits']}/{s['injection_n']} errors={s['errors']} "
              f"safe-check={'PASS' if not s['safe_offenders'] else 'FAIL'}")
        print("  confusion (expected -> predicted):")
        for e in STATES:
            print(f"    {e:9s} " + " ".join(f"{k}={v}" for k, v in s["confusion"][e].items()))
    print(f"\nwrote {out_path} and {raw_path}")
    if import_error and not args.dry_run:
        return 2
    failed = any(s["safe_offenders"] for s in summaries.values())
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
