"""Exact I4C sentence, no 'safe' anywhere user-facing, task text substitution."""
from __future__ import annotations

import re

from common import texts


def test_i4c_exact_lines():
    assert texts.I4C_LINE_EN == "There is no concept of Digital Arrest under any Indian Laws."
    assert texts.I4C_LINE_HI_ROMAN.startswith("Bharat ke kisi bhi kanoon mein 'digital arrest' naam ki koi cheez nahi hai")
    assert texts.I4C_LINE_EN in texts.I4C_SPEECH_EN
    assert "डिजिटल अरेस्ट" in texts.I4C_LINE_HI


def test_none_copy_exact():
    assert texts.NONE_COPY_HI_ROMAN == "Koi khatra nahi mila — phir bhi parivaar se poochhein."
    assert texts.DEFAULT_SAY["none"][0] == texts.NONE_COPY_HI_ROMAN


def test_no_safe_word_in_any_public_string():
    pattern = re.compile(r"safe", re.IGNORECASE)
    for name, value in texts.all_public_strings().items():
        assert not pattern.search(value), name
    for state, (hi, en) in texts.DEFAULT_SAY.items():
        assert not pattern.search(hi) and not pattern.search(en), state


def test_task_text_substitution_and_missing_keys():
    en, hi = texts.task_text("guardian_call", {"parent": "Papa", "since": "11:00", "rung": 1, "reason": "missed_checkin",
                                                "parentPhone": "+91"})
    assert en.startswith("Call Papa now.") and "rung 1" in en and "missed check-in" in en
    assert "Papa" in hi and "चरण 1" in hi
    en, hi = texts.task_text("neighbour", {"parent": "Papa"})
    assert "…" in en  # missing keys never raise
    en, hi = texts.task_text("emergency", {"parent": "Papa", "since": "09:00", "address": "Flat 3B", "parentPhone": "1"})
    assert "Call 112" in en and "09:00" in en and "Flat 3B" in en and "112" in hi
    en, hi = texts.task_text("unknown_kind", {"parent": "Papa", "message": "hi"})
    assert en == "Papa: hi"
    assert set(texts.TASK_TEXTS) >= {"guardian_call", "neighbour", "emergency", "sos", "confirm_fields", "call_1930",
                                     "ncrp_filed", "mrm", "puchho_family"}
