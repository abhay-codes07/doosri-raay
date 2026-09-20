"""Rules as data: every fact in rules_data.json / patterns.json has a source and a quote, the
evaluator applies operator/value, and the classifier's few-shots and explanations come from the
catalogue."""
from __future__ import annotations

import json
import os

import pytest

from classify_worker import classifier
from recovery_agent import rules

BACKEND = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend")


def _entries(node, path=""):
    if isinstance(node, dict):
        if isinstance(node.get("source"), dict) and "quote" in node:
            yield path, node
        for k, v in node.items():
            yield from _entries(v, "%s.%s" % (path, k) if path else k)
    elif isinstance(node, list):
        for i, v in enumerate(node):
            yield from _entries(v, "%s[%d]" % (path, i))


def test_no_legal_fact_is_hard_coded_in_python():
    src = open(os.path.join(BACKEND, "recovery_agent", "rules.py"), encoding="utf-8").read()
    for literal in ("hindustantimes.com", "timesofindia", "deccanchronicle", "freepressjournal", "thehindu.com",
                    '"329"', "100000)", "500000)", '"50000"', "Reported by Hindustan"):
        assert literal not in src, literal


def test_every_rule_entry_has_source_quote_label_and_caveat():
    entries = rules.rule_entries()
    assert len(entries) >= 10
    for path, entry in entries:
        src = entry["source"]
        assert set(src) == {"outlet", "date", "url"} and src["url"].startswith("https://"), path
        assert isinstance(entry["quote"], str) and len(entry["quote"]) > 20, path
        assert entry["label"]["en"] and entry["label"]["hi"], path
        assert entry["caveat"], path
        if "value" in entry:
            assert entry["operator"] in rules._OPERATORS, path
    states = rules.RULES["ezeroFir"]["states"]
    assert set(states) == {"haryana", "rajasthan", "punjab"}
    assert rules.RULES["mrm"]["firMandatoryAbove"]["value"] == 50000
    assert rules.RULES["ncrp"]["ackNumber"]["prefix"] == "329"


@pytest.mark.parametrize("entry,actual,expected", [
    ({"operator": ">=", "value": 100000}, 100000, True),
    ({"operator": ">=", "value": 100000}, 99999.99, False),
    ({"operator": ">", "value": 500000}, 500000, False),
    ({"operator": ">", "value": 500000}, "5,00,001", True),
    ({"operator": "<=", "value": 50000}, 50000, True),
    ({"operator": "<=", "value": 50000}, 50001, False),
    ({"operator": "==", "value": 14}, 14, True),
    ({"operator": "==", "value": True}, True, True),
    ({"operator": "!=", "value": "x"}, "y", True),
    ({"operator": ">", "value": 1}, "not a number", False),
    ({"operator": ">", "value": 1}, float("nan"), False),
])
def test_evaluator(entry, actual, expected):
    assert rules.evaluate(entry, actual) is expected


def test_evaluator_rejects_entries_without_operator():
    with pytest.raises(ValueError):
        rules.evaluate({"value": 1}, 2)


def test_ezero_lookup_evaluates_amount_from_data():
    assert rules.lookup_ezero_threshold("Haryana", 100000)["applies"] is True
    assert rules.lookup_ezero_threshold("Haryana", 99999)["applies"] is False
    assert rules.lookup_ezero_threshold("Punjab", 500000)["applies"] is False
    assert rules.lookup_ezero_threshold("Punjab", 500001)["applies"] is True
    assert rules.lookup_ezero_threshold("Kerala", 900000)["applies"] is None
    entry = rules.lookup_ezero_threshold("Rajasthan")
    assert entry["quote"].startswith("Victims of cyber financial fraud involving Rs 1 lakh") and entry["label"]["hi"]
    assert entry["applies"] is None
    sc = entry["scDirection"]
    assert sc["quote"] and sc["source"]["url"] and sc["label"]["en"] == rules.SC_DIRECTION_TEXT


def test_mrm_and_ncrp_carry_citations():
    mrm = rules.mrm_eligibility([{"utr": "123456789012", "amount": 50001, "payee": "a", "timestamp": "2026-09-17"}])
    assert mrm["firRequired"] is True and mrm["quote"].startswith("If the held amount exceeds Rs50,000")
    assert set(mrm["citations"]) == {"noFirUpTo", "firMandatoryAbove", "ackRequired"}
    for c in mrm["citations"].values():
        assert c["quote"] and c["source"]["url"] and c["caveat"] and c["label"]["hi"]
    small = rules.mrm_eligibility([{"utr": "123456789012", "amount": 50000, "payee": "a", "timestamp": "2026-09-17"}])
    assert small["firRequired"] is False and small["quote"].startswith("refunds up to")
    ncrp = rules.ncrp_facts()
    assert set(ncrp["citations"]) == {"narrativeMinChars", "transactionIdDigits", "idUploadRequired", "ackNumber"}
    assert ncrp["citations"]["ackNumber"]["quote"].endswith("starting with “329”")


def test_nan_amount_is_not_numeric_not_a_crash():
    row = {"utr": "123456789012", "amount": float("nan"), "payee": "a", "timestamp": "2026-09-17"}
    out = rules.validate_fields([row, {**row, "amount": float("inf")}, {**row, "amount": "NaN"}])
    assert all("amount_not_numeric" in t["issues"] for t in out)
    assert rules.mrm_eligibility([row])["firRequired"] is False


def test_txn_string_fields_are_capped_at_200():
    long = "x" * 1000
    out = rules.validate_fields([{"utr": long, "amount": long, "payee": long, "timestamp": long, "app": long}])[0]
    for key in ("utr", "payee", "timestamp", "app", "amount"):
        assert len(str(out[key])) <= 200, key
    assert out["valid"] is False


def test_nan_amount_in_confirm_body_is_400(api, family):
    from common import db, tasks

    case_id = "n" * 32
    db.put_item({"PK": "CIRCLE#%s" % family["circleId"], "SK": "CASE#%s" % case_id, "caseId": case_id,
                 "circleId": family["circleId"], "status": "awaiting_confirmation"})
    task = tasks.create_task(family["circleId"], "confirm_fields", "g1", "x", "x", context={"caseId": case_id},
                             task_token="tok")
    from api.app import handler as api_handler
    from conftest import api_event

    event = api_event("POST", "/tasks/{taskId}/complete", "g1", None, {"taskId": task["taskId"]})
    event["body"] = '{"outcome":"confirmed","txns":[{"utr":"123456789012","amount":NaN,"payee":"a","timestamp":"2026-09-17"}]}'
    resp = api_handler(event, None)
    assert resp["statusCode"] == 400 and json.loads(resp["body"])["error"] == "invalid_txns"


# --- classifier catalogue ----------------------------------------------------------------------

def test_patterns_catalogue_is_complete_and_cited():
    patterns = classifier.PATTERN_LIST
    assert len(patterns) == 12
    assert len({p["id"] for p in patterns}) == 12
    for p in patterns:
        assert p["scamType"] in classifier.SCAM_TYPES and p["scamType"] != "NONE", p["id"]
        assert p["label"]["en"] and p["label"]["hi"] and len(p["redFlags"]) >= 2, p["id"]
        assert set(p["tactics"]) <= set(classifier.TACTICS) and p["tactics"], p["id"]
        adv = p["advisory"]
        assert adv["quote"] and adv["source"]["url"].startswith("https://") and adv["source"]["outlet"], p["id"]
        # the example is a valid verdict as the model would emit it
        v = classifier.validate_verdict(p["example"]["output"], "m")
        assert v["redFlags"] != ["model_output_invalid"], p["id"]
        assert v["scamType"] == p["scamType"] and v["state"] == "likely", p["id"]
    for key in ("generalAdvice", "reportAdvice"):
        assert classifier.PATTERNS[key]["quote"] and classifier.PATTERNS[key]["source"]["url"]


def test_few_shots_cover_all_states_and_come_from_the_catalogue():
    states = {ex["output"]["state"] for ex in classifier.FEW_SHOT}
    assert states == {"likely", "watching", "none"}
    assert len(classifier.FEW_SHOT) == 12 + len(classifier.PATTERNS["extraExamples"])
    for ex in classifier.FEW_SHOT:
        assert classifier.validate_verdict(ex["output"], "m")["redFlags"] != ["model_output_invalid"]
    prompt = classifier.SYSTEM_PROMPT
    assert "state=watching" in prompt and "Rohit" in prompt
    assert prompt.startswith("You are a scam-pattern classifier for Indian families.")


def test_lookup_patterns_and_explanations():
    da = classifier.lookup_patterns("DIGITAL_ARREST")
    assert [p["id"] for p in da] == ["digital_arrest", "trai_sim_block"]
    assert classifier.lookup_patterns("NONE") == [] and classifier.lookup_patterns(None) == []
    # OTHER has no direct catalogue match; two shared tactics pick the closest pretexts
    by_tactics = classifier.lookup_patterns("OTHER", ["authority", "urgency", "secrecy"])
    assert "family_emergency" in {p["id"] for p in by_tactics}
    assert classifier.lookup_patterns("OTHER", ["urgency"]) == []
    ex = classifier.explain("COURIER_CUSTOMS", ["authority", "urgency"], "likely")
    assert ex["patternId"] == "courier_customs" and ex["patternLabel"]["hi"]
    assert len(ex["explanations"]) == 3
    assert ex["explanations"][0]["quote"].startswith("sending or receiving contraband")
    assert ex["explanations"][0]["source"]["url"].endswith("DigitalArrest06.03.2025.pdf")
    assert ex["explanations"][1]["quote"] == "Speak to your relatives and friends before taking any action to transfer money."
    none = classifier.explain("NONE", [], "none")
    assert none["patternId"] is None and [e["patternId"] for e in none["explanations"]] == [None, None]


def test_classify_adds_explanations_and_uses_1024_tokens():
    from conftest import FakeBedrock

    fake = FakeBedrock({"state": "likely", "scamType": "KYC_PHISHING", "tactics": ["urgency"],
                        "redFlags": ["link"], "sayHi": "Link na kholein.", "sayEn": "Do not open."})
    v = classifier.classify(text="update kyc now", client=fake)
    assert fake.calls[0]["inferenceConfig"] == {"maxTokens": 1024, "temperature": 0.0}
    assert v["patternId"] == "kyc_phishing" and v["explanations"][0]["quote"].startswith("Never share personal")
    assert v["patternRedFlags"]
    fake = FakeBedrock("garbage")
    v = classifier.classify(text="x", client=fake)
    assert v["state"] == "watching" and v["patternId"] is None and len(v["explanations"]) == 2
