"""recovery_agent.rules: UTR, amounts, timestamps, thresholds, MRM, narrative."""
from __future__ import annotations

import pytest

from recovery_agent import rules, templates

GOOD = {"utr": "123456789012", "amount": 50000, "payee": "xyz@ybl", "timestamp": "2026-09-17T10:30:00+05:30", "app": "PhonePe"}


def test_validate_fields_good():
    out = rules.validate_fields([GOOD])
    assert out[0]["valid"] is True and out[0]["issues"] == [] and out[0]["amount"] == 50000
    assert out[0]["rail"] == "upi_imps"


@pytest.mark.parametrize("ref,expected", [
    ("SBIN526012345678", "SBIN526012345678"),          # 16
    ("hdfcn52026091812345678", "HDFCN52026091812345678"),  # 22, upper-cased
    (" utibr52026091812345 ", "UTIBR52026091812345"),  # 19, trimmed
    ("1234567890123456", "1234567890123456"),          # 16 digits is a NEFT/RTGS reference, not a UTR
])
def test_neft_rtgs_references(ref, expected):
    out = rules.validate_fields([{**GOOD, "utr": ref}])
    assert out[0]["valid"] is True and out[0]["rail"] == "neft_rtgs" and out[0]["utr"] == expected


@pytest.mark.parametrize("ref", ["SBIN5260123456", "A" * 23, "SBIN-526012345678", "sbin 526012345678"])
def test_neft_rtgs_rejects_wrong_length_or_characters(ref):
    out = rules.validate_fields([{**GOOD, "utr": ref}])
    assert out[0]["valid"] is False and out[0]["rail"] == "unknown" and "utr_invalid" in out[0]["issues"]


def test_describe_issues_lists_rows_one_based():
    validated = rules.validate_fields([GOOD, {**GOOD, "utr": "x", "payee": ""}, {**GOOD, "amount": 0}])
    text = rules.describe_issues(validated)
    assert text.startswith("Row 2: utr_invalid (") and "payee_missing" in text and "Row 3: amount_out_of_range" in text
    assert "Row 1" not in text


def test_validate_ack():
    assert rules.validate_ack(" 32901234567890 ") == ("32901234567890", None)
    assert rules.validate_ack("12901234567890") == ("12901234567890", rules.ACK_WARNING)
    assert rules.ACK_WARNING == "Ack numbers reported in the press start with 329; double-check"
    for bad in ("", None, "3290123456789", "329012345678901", "3290123456789a"):
        assert rules.validate_ack(bad) == (None, None), bad


@pytest.mark.parametrize("utr", ["", "12345678901", "1234567890123", "12345678901a", "ABC", None])
def test_utr_regex(utr):
    out = rules.validate_fields([{**GOOD, "utr": utr}])
    assert out[0]["valid"] is False and "utr_invalid" in out[0]["issues"] and out[0]["rail"] == "unknown"


@pytest.mark.parametrize("amount,issue", [
    (0, "amount_out_of_range"), (-5, "amount_out_of_range"), (100000001, "amount_out_of_range"),
    ("abc", "amount_not_numeric"), (None, "amount_not_numeric"), (True, "amount_not_numeric"),
])
def test_amount_rules(amount, issue):
    out = rules.validate_fields([{**GOOD, "amount": amount}])
    assert issue in out[0]["issues"]


@pytest.mark.parametrize("amount", [1, 100000000, "50,000", "Rs 1,200.50", 12.5])
def test_amount_accepts_formats(amount):
    assert rules.validate_fields([{**GOOD, "amount": amount}])[0]["valid"]


@pytest.mark.parametrize("ts", ["2026-09-17T10:30:00+05:30", "2026-09-17T10:30:00Z", "2026-09-17", "17/09/2026 10:30", "17/09/2026", "1/9/2026 9:05"])
def test_timestamp_formats(ts):
    assert rules.validate_fields([{**GOOD, "timestamp": ts}])[0]["valid"]


@pytest.mark.parametrize("ts", ["", "yesterday", "32/13/2026 10:30", None, "2026-99-99"])
def test_timestamp_unparseable(ts):
    assert "timestamp_unparseable" in rules.validate_fields([{**GOOD, "timestamp": ts}])[0]["issues"]


def test_payee_required_and_non_objects():
    assert "payee_missing" in rules.validate_fields([{**GOOD, "payee": "  "}])[0]["issues"]
    assert rules.validate_fields(["nope"])[0] == {"valid": False, "issues": ["not_an_object"]}
    assert rules.validate_fields("nope") == []
    assert rules.validate_fields([]) == []


def test_ezero_thresholds():
    assert rules.lookup_ezero_threshold("Haryana")["thresholdInr"] == 100000
    assert rules.lookup_ezero_threshold("rajasthan")["thresholdInr"] == 100000
    assert rules.lookup_ezero_threshold("PUNJAB")["thresholdInr"] == 500000
    other = rules.lookup_ezero_threshold("Maharashtra")
    assert other["thresholdInr"] is None
    assert other["note"] == "Check with 1930; SC ordered all states to adopt e-Zero FIR (Aug 2026)"
    assert other["sourceUrl"].startswith("https://") and other["state"] == "Maharashtra"
    for s in ("Haryana", "Punjab"):
        assert rules.lookup_ezero_threshold(s)["sourceUrl"].startswith("https://")
    assert rules.lookup_ezero_threshold(None)["thresholdInr"] is None


def test_ezero_sources_and_caveats():
    hr = rules.lookup_ezero_threshold("Haryana")
    assert hr["source"] == {"outlet": "Hindustan Times", "date": "25 Jun 2026",
                            "url": "https://www.hindustantimes.com/cities/chandigarh-news/haryana-to-lodge-e-zero-fir-in-cyber-financial-fraud-cases-101782412687221.html"}
    assert hr["caveat"] == "Reported by Hindustan Times on 25 Jun 2026; confirm with 1930 before relying on it"
    assert hr["comparison"] == ">=" and "Rs 100,000 or more" in hr["note"]
    rj = rules.lookup_ezero_threshold("Rajasthan")
    assert rj["source"]["outlet"] == "Times of India" and rj["source"]["date"] == "23 Jul 2026"
    assert "timesofindia" in rj["source"]["url"] and rj["comparison"] == ">="
    pb = rules.lookup_ezero_threshold("Punjab")
    assert pb["source"]["outlet"] == "New Indian Express" and pb["source"]["date"] == "29 Jul 2026"
    assert pb["comparison"] == ">" and "more than Rs 500,000" in pb["note"]
    other = rules.lookup_ezero_threshold("Kerala")
    assert other["source"]["outlet"] == "New Indian Express" and other["source"]["date"] == "4 Aug 2026"
    assert other["source"]["url"].endswith("sc-issues-13-point-directions-to-fight-digital-arrest-scams")
    assert other["caveat"] == "Reported by New Indian Express on 4 Aug 2026; confirm with 1930 before relying on it"
    for entry in (hr, rj, pb, other):
        assert entry["scDirection"]["text"] == (
            "Supreme Court directed all States/UTs to adopt e-Zero FIR (13-point directions, 4 Aug 2026)")
        assert entry["scDirection"]["source"]["url"].startswith("https://www.newindianexpress.com/india/2026/Aug/04/")
        assert entry["sourceUrl"] == entry["source"]["url"]


def test_mrm_and_ncrp_sources():
    mrm = rules.mrm_eligibility([GOOD])
    assert mrm["source"]["outlet"] == "Deccan Chronicle" and "deccanchronicle.com" in mrm["source"]["url"]
    assert [s["outlet"] for s in mrm["sources"]] == ["Deccan Chronicle", "Free Press Journal"]
    assert "freepressjournal.in" in mrm["sources"][1]["url"]
    assert mrm["caveat"] == "Reported by Deccan Chronicle; confirm with 1930 before relying on it"
    assert mrm["portal"] == "https://mrm-ncrp.mha.gov.in"
    assert "indemnity bond" in rules.mrm_eligibility([{**GOOD, "amount": 50000}])["rule"]
    ncrp = rules.ncrp_facts()
    assert ncrp["rules"] == {"narrativeMinChars": 200, "narrativeNoSpecialCharacters": True, "transactionIdDigits": 12,
                             "idUploadRequired": True, "ackDigits": 14, "ackPrefix": "329"}
    assert ncrp["source"]["url"] == "https://cybercrime.gov.in/Webform/Crime_AuthoLogin.aspx"
    assert ncrp["ackSource"]["outlet"] == "The Hindu (Chennai)" and "thehindu.com" in ncrp["ackSource"]["url"]
    assert ncrp["caveat"].startswith("Reported by The Hindu (Chennai); confirm with 1930")
    for src in (mrm["source"], ncrp["source"], ncrp["ackSource"]):
        assert set(src) == {"outlet", "date", "url"}


def test_mrm_single_account_over_50k_requires_fir():
    small = rules.mrm_eligibility([{**GOOD, "amount": 50000}])
    assert small["eligible"] is True and small["firRequired"] is False
    assert small["portal"] == "https://mrm-ncrp.mha.gov.in"
    assert any("PAN" in c for c in small["checklist"]) and any("ndemnity" in c for c in small["checklist"])
    assert not any("FIR copy" in c for c in small["checklist"])
    big = rules.mrm_eligibility([{**GOOD, "amount": 50001}])
    assert big["firRequired"] is True and any("FIR copy" in c for c in big["checklist"])
    # two transfers to the same account add up
    split = rules.mrm_eligibility([{**GOOD, "amount": 30000}, {**GOOD, "amount": 30000}])
    assert split["firRequired"] is True
    # two different accounts of 30k each do not
    spread = rules.mrm_eligibility([{**GOOD, "amount": 30000}, {**GOOD, "amount": 30000, "payee": "other@upi"}])
    assert spread["firRequired"] is False
    assert rules.mrm_eligibility([])["eligible"] is False


def test_mrm_with_frozen_amounts():
    res = rules.mrm_eligibility([GOOD], {"acc1": 0, "acc2": 0})
    assert res["eligible"] is False and res["basis"] == "frozen"
    res = rules.mrm_eligibility([GOOD], {"acc1": 60000})
    assert res["eligible"] is True and res["firRequired"] is True and res["maxSingleAccountInr"] == 60000
    res = rules.mrm_eligibility([GOOD], {"acc1": 20000, "acc2": 20000})
    assert res["eligible"] is True and res["firRequired"] is False


def test_narrative_ok_and_sanitizer():
    ok, reasons = rules.ncrp_narrative_ok("short")
    assert not ok and "too_short" in reasons
    ok, reasons = rules.ncrp_narrative_ok("a" * 200 + "!")
    assert not ok and reasons == ["disallowed_characters"]
    ok, reasons = rules.ncrp_narrative_ok("a" * 200)
    assert ok and reasons == []
    assert rules.ncrp_narrative_ok(None) == (False, ["not_a_string"])
    assert rules.ncrp_narrative_ok("x" * 1600)[1] == ["too_long"]

    cleaned = rules.sanitize_narrative("Sent ₹50,000 to xyz@ybl (UTR 123456789012)! <script>alert('x')</script>")
    assert rules.ncrp_narrative_ok(cleaned)[0]
    assert "Rs 50,000" in cleaned and "123456789012" in cleaned and "<" not in cleaned
    assert len(cleaned) >= 200 and cleaned.endswith(".")
    assert rules.NEUTRAL_PAD_SENTENCE in cleaned
    assert rules.ncrp_narrative_ok(rules.sanitize_narrative(""))[0]
    assert rules.ncrp_narrative_ok(rules.sanitize_narrative("नमस्ते " * 50))[0]


def test_templates_are_deterministic_and_valid():
    case = {"victimName": "Ramesh Kumar", "state": "Punjab", "incidentDate": "2026-09-17",
            "narrativeHint": "CBI video call, told to transfer for 'verification'", "ackNo": "32901234567890"}
    txns = rules.validate_fields([GOOD, {**GOOD, "utr": "999999999999", "amount": 12000, "payee": "abc@okaxis"}])
    narrative = templates.ncrp_template_narrative(case, txns)
    assert rules.ncrp_narrative_ok(narrative)[0]
    assert "123456789012" in narrative and "999999999999" in narrative and "Ramesh Kumar" in narrative
    assert narrative == templates.ncrp_template_narrative(case, txns)
    script = templates.script_1930(case, txns)
    assert "1930" in script["en"] and "123456789012" in script["en"] and "62,000" in script["en"]
    assert "1930" in script["hi"] and "123456789012" in script["hi"]
    letter = templates.freeze_letter(case, txns)
    assert "32901234567890" in letter and "freeze" in letter.lower() and "Ramesh Kumar" in letter
    checklist = templates.mrm_checklist(case, rules.mrm_eligibility(txns))
    assert checklist["firRequired"] is False and checklist["checklist"]
