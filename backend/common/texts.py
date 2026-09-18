"""All user-facing strings, Hindi (Devanagari) and English.

Rule (docs/API.md): the word "safe" never appears in anything the model or the
UI says about a message. ``assert_no_safe_word`` is checked by the tests.
"""
from __future__ import annotations

import re
from typing import Any, Dict, Optional, Tuple

APP_TITLE = "Doosri Raay"

# --- I4C / Puchho ----------------------------------------------------------

I4C_LINE_EN = "There is no concept of Digital Arrest under any Indian Laws."
I4C_LINE_HI_ROMAN = (
    "Bharat ke kisi bhi kanoon mein 'digital arrest' naam ki koi cheez nahi hai. "
    "Police, CBI ya court kabhi video call par giraftaar nahi karte aur paise nahi maangte. "
    "Phone kaat dein aur 1930 par call karein."
)
I4C_LINE_HI = (
    "भारत के किसी भी कानून में 'डिजिटल अरेस्ट' नाम की कोई चीज़ नहीं है। "
    "पुलिस, सीबीआई या कोर्ट कभी वीडियो कॉल पर गिरफ्तार नहीं करते और पैसे नहीं माँगते। "
    "फ़ोन काट दें और 1930 पर कॉल करें।"
)
I4C_SPEECH_EN = (
    "This is a message from your family. " + I4C_LINE_EN + " "
    "The police, the CBI and the courts never arrest anyone over a video call and never ask for money. "
    "Please hang up now and call 1930, the national cyber crime helpline."
)
I4C_SPEECH_HI = (
    "यह आपके परिवार की ओर से एक संदेश है। " + I4C_LINE_HI + " "
    "कृपया अभी फ़ोन रखें और साइबर हेल्पलाइन 1930 पर कॉल करें।"
)

PUCHHO_NO_EN = "This call is not genuine. Hang up. {guardian} has been told."
PUCHHO_NO_HI = "यह कॉल सच नहीं है। फ़ोन काट दें। {guardian} को बता दिया गया है।"
PUCHHO_NO_HI_ROMAN = "Yeh call sach nahi hai. Phone kaat dein. {guardian} ko bata diya gaya hai."

# --- Classifier copy --------------------------------------------------------

NONE_COPY_HI_ROMAN = "Koi khatra nahi mila — phir bhi parivaar se poochhein."
NONE_COPY_HI = "कोई खतरा नहीं मिला — फिर भी परिवार से पूछें।"
NONE_COPY_EN = "No known scam pattern found — still, ask your family before acting."

DEFAULT_SAY: Dict[str, Tuple[str, str]] = {
    "none": (NONE_COPY_HI_ROMAN, NONE_COPY_EN),
    "watching": (
        "Kuch baatein sandeh-janak hain. Koi paisa ya OTP na dein, pehle parivaar se poochhein.",
        "Some details look suspicious. Do not send money or an OTP; ask your family first.",
    ),
    "likely": (
        "Yeh ek jaana-pehchaana dhokha lagta hai. Phone kaat dein, paisa na bhejein, 1930 par call karein.",
        "This matches a known scam pattern. Hang up, do not send money, and call 1930.",
    ),
}
MODEL_INVALID_FLAG = "model_output_invalid"


# --- Task texts -------------------------------------------------------------

def _fmt(template: str, ctx: Dict[str, Any]) -> str:
    class _Safe(dict):
        def __missing__(self, key: str) -> str:
            return "…"

    return template.format_map(_Safe(**{k: ("" if v is None else v) for k, v in ctx.items()}))


TASK_TEXTS: Dict[str, Tuple[str, str]] = {
    # kind: (English, Hindi)
    "guardian_call": (
        "Call {parent} now. {parent} has not opened the tile since {since} (rung {rung}, {reason}). "
        "Phone: {parentPhone}. Mark 'reached' once you have spoken.",
        "{parent} को अभी फ़ोन करें। {since} से टाइल नहीं खोली गई है (चरण {rung}, {reason})। "
        "फ़ोन: {parentPhone}। बात हो जाने पर 'reached' दबाएँ।",
    ),
    "neighbour": (
        "Ask the neighbour to knock. Call {neighbourName} ({neighbourPhone}), address {address}. "
        "Script: 'Namaste, I am {parent}'s family. We cannot reach them since {since}. "
        "Could you please knock on the door and call me back?' Mark 'reached' if {parent} is fine.",
        "पड़ोसी से दरवाज़ा खटखटाने को कहें। {neighbourName} ({neighbourPhone}) को फ़ोन करें, पता {address}। "
        "कहें: 'नमस्ते, मैं {parent} के परिवार से हूँ। {since} से संपर्क नहीं हो पा रहा। "
        "क्या आप दरवाज़ा खटखटा कर मुझे फ़ोन कर सकते हैं?' अगर {parent} ठीक हैं तो 'reached' दबाएँ।",
    ),
    "emergency": (
        "Call 112 now. Say: 'An elderly parent, {parent}, has been unreachable since {since}. "
        "Address: {address}. Phone: {parentPhone}. Please send someone to check.'",
        "अभी 112 पर कॉल करें। कहें: 'एक बुज़ुर्ग, {parent}, {since} से संपर्क में नहीं हैं। "
        "पता: {address}। फ़ोन: {parentPhone}। कृपया किसी को देखने भेजें।'",
    ),
    "sos": (
        "{parent} sent a silent SOS from {mapsLink} at {time}. Call now.",
        "{parent} ने {time} पर {mapsLink} से चुपचाप SOS भेजा है। अभी फ़ोन करें।",
    ),
    "sos_nolocation": (
        "{parent} sent a silent SOS at {time} (no location shared). Call now.",
        "{parent} ने {time} पर चुपचाप SOS भेजा है (स्थान नहीं मिला)। अभी फ़ोन करें।",
    ),
    "confirm_fields": (
        "Confirm the transaction details for the case of {victim}. {txnCount} transaction(s) were read "
        "from the screenshots; check every UTR, amount and payee beside the image and correct anything wrong.",
        "{victim} के केस के लेन-देन की जानकारी जाँचें। स्क्रीनशॉट से {txnCount} लेन-देन पढ़े गए हैं; "
        "हर UTR, राशि और भुगतान पाने वाले को तस्वीर के साथ मिलाएँ और ग़लती सुधारें।",
    ),
    "call_1930": (
        "Call 1930 now and read the script for {victim}'s case. The first hours matter most for freezing the money. "
        "Mark 'done' after the call, or 'later' if you cannot call right now.",
        "अभी 1930 पर कॉल करें और {victim} के केस की स्क्रिप्ट पढ़ें। पैसा रोकने के लिए पहले कुछ घंटे सबसे ज़रूरी हैं। "
        "कॉल के बाद 'done' दबाएँ, या अभी नहीं कर सकते तो 'later'।",
    ),
    "ncrp_filed": (
        "File the complaint on cybercrime.gov.in for {victim} using the prepared narrative, then enter the "
        "14-digit acknowledgement number (starts with 329).",
        "{victim} के लिए cybercrime.gov.in पर तैयार विवरण से शिकायत दर्ज करें, फिर 14 अंकों का "
        "पावती नंबर (329 से शुरू) भरें।",
    ),
    "mrm": (
        "Money for {victim}'s case may be frozen. Complete the MRM (Mule Account Refund) checklist: {checklist}.",
        "{victim} के केस का पैसा रोका जा सकता है। MRM (रिफ़ंड) चेकलिस्ट पूरी करें: {checklist}।",
    ),
    "puchho_family": (
        "{parent} is on a call and asks: is this real? Reply 'yes' only if you personally know about it, "
        "otherwise 'no'. Enter the family code word so {parent} knows it is you.",
        "{parent} किसी कॉल पर हैं और पूछ रहे हैं: क्या यह सच है? सिर्फ़ तभी 'yes' दबाएँ जब आपको खुद इसकी जानकारी हो, "
        "वरना 'no'। परिवार का कोड वर्ड लिखें ताकि {parent} जान सकें कि यह आप ही हैं।",
    ),
    "info": (
        "{parent} was told: {message} at {time}.",
        "{parent} को {time} पर बताया गया: {message}।",
    ),
    "reminder": (
        "Reminder for {victim}'s case: {message}",
        "{victim} के केस के लिए याद दिलाना: {message}",
    ),
}

NEIGHBOUR_SCRIPT: Tuple[str, str] = (
    "Namaste, I am {parent}'s family. We cannot reach them since {since}. Could you please knock on the door "
    "and call me back?",
    "नमस्ते, मैं {parent} के परिवार से हूँ। {since} से संपर्क नहीं हो पा रहा। क्या आप दरवाज़ा खटखटा कर मुझे "
    "फ़ोन कर सकते हैं?",
)


def neighbour_script(ctx: Optional[Dict[str, Any]] = None) -> Tuple[str, str]:
    ctx = {"parent": "Papa", "since": "…", **(ctx or {})}
    return _fmt(NEIGHBOUR_SCRIPT[0], ctx), _fmt(NEIGHBOUR_SCRIPT[1], ctx)


REASON_LABELS: Dict[str, Tuple[str, str]] = {
    "missed_checkin": ("missed check-in", "चेक-इन नहीं हुआ"),
    "sos": ("silent SOS", "चुपचाप SOS"),
}


def task_text(kind: str, ctx: Optional[Dict[str, Any]] = None) -> Tuple[str, str]:
    """Return (english, hindi) for a task kind with the context substituted."""
    ctx = dict(ctx or {})
    ctx.setdefault("parent", "Papa")
    ctx.setdefault("victim", ctx.get("parent"))
    reason = ctx.get("reason")
    en_reason, hi_reason = REASON_LABELS.get(str(reason), (str(reason or ""), str(reason or "")))
    en_t, hi_t = TASK_TEXTS.get(kind, ("{parent}: {message}", "{parent}: {message}"))
    en = _fmt(en_t, {**ctx, "reason": en_reason})
    hi = _fmt(hi_t, {**ctx, "reason": hi_reason})
    return en, hi


# --- guards ----------------------------------------------------------------

_SAFE_RE = re.compile(r"\bsafe\b|\bunsafe\b|safety", re.IGNORECASE)


def contains_safe_word(text: str) -> bool:
    return bool(_SAFE_RE.search(text or ""))


def all_public_strings() -> Dict[str, str]:
    """Every string a user may read (for the no-'safe' test)."""
    out: Dict[str, str] = {
        "I4C_LINE_EN": I4C_LINE_EN,
        "I4C_LINE_HI_ROMAN": I4C_LINE_HI_ROMAN,
        "I4C_LINE_HI": I4C_LINE_HI,
        "I4C_SPEECH_EN": I4C_SPEECH_EN,
        "I4C_SPEECH_HI": I4C_SPEECH_HI,
        "PUCHHO_NO_EN": PUCHHO_NO_EN,
        "PUCHHO_NO_HI": PUCHHO_NO_HI,
        "PUCHHO_NO_HI_ROMAN": PUCHHO_NO_HI_ROMAN,
        "NONE_COPY_HI_ROMAN": NONE_COPY_HI_ROMAN,
        "NONE_COPY_HI": NONE_COPY_HI,
        "NONE_COPY_EN": NONE_COPY_EN,
    }
    for state, (hi, en) in DEFAULT_SAY.items():
        out["DEFAULT_SAY_%s_hi" % state] = hi
        out["DEFAULT_SAY_%s_en" % state] = en
    for kind, (en, hi) in TASK_TEXTS.items():
        out["TASK_%s_en" % kind] = en
        out["TASK_%s_hi" % kind] = hi
    return out
