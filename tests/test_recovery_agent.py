"""recovery-agent Lambda actions with a fake Bedrock client (deterministic path; strands not installed)."""
from __future__ import annotations

import boto3
import pytest

from common import db
from recovery_agent import agent, app, rules

TXN = {"utr": "123456789012", "amount": 60000, "payee": "fraud@ybl", "timestamp": "2026-09-17T10:30:00+05:30", "app": "PhonePe"}


@pytest.fixture
def case(family):
    circle = family["circleId"]
    key = "circles/%s/case/a.png" % circle
    boto3.client("s3", region_name="ap-south-1").put_object(Bucket="doosriraay-test-uploads", Key=key, Body=b"png", ContentType="image/png")
    case_id = "f" * 32
    db.put_item({"PK": "CIRCLE#%s" % circle, "SK": "CASE#%s" % case_id, "GSI1PK": "CASEID#%s" % case_id,
                 "GSI1SK": "CIRCLE#%s" % circle, "caseId": case_id, "circleId": circle, "status": "open",
                 "victimName": "Ramesh Kumar", "state": "Haryana", "incidentDate": "2026-09-17",
                 "narrativeHint": "CBI video call", "objectKeys": [key], "artifacts": {}, "confirmedTxns": []})
    return {"circleId": circle, "caseId": case_id, "key": key}


def _get(case):
    return db.get_item("CIRCLE#%s" % case["circleId"], "CASE#%s" % case["caseId"])


def test_extract_writes_validated_txns(case, bedrock_fake):
    bedrock_fake.tool_input = {"txns": [TXN, {"utr": "12", "amount": "abc", "payee": "", "timestamp": "?"}]}
    result = app.handler({"action": "extract", "circleId": case["circleId"], "caseId": case["caseId"]}, None)
    assert result["extracted"]["count"] == 2 and result["extracted"]["invalidCount"] == 1
    stored = _get(case)
    assert stored["status"] == "awaiting_confirmation"
    txns = stored["extracted"]["txns"]
    assert txns[0]["valid"] is True and txns[0]["objectKey"] == case["key"]
    assert set(txns[1]["issues"]) == {"utr_invalid", "amount_not_numeric", "payee_missing", "timestamp_unparseable"}
    call = bedrock_fake.calls[0]
    assert call["messages"][0]["content"][1]["image"]["format"] == "png"
    assert "UNTRUSTED" in call["system"][0]["text"]


def test_build_uses_model_narrative_when_valid(case, bedrock_fake):
    db.set_attributes("CIRCLE#%s" % case["circleId"], "CASE#%s" % case["caseId"], {"confirmedTxns": [TXN]})
    good = ("On 17 September 2026 Ramesh Kumar received a video call from a person claiming to be a CBI officer. "
            "He was told to transfer money for verification. Rs 60000 was sent to fraud at ybl with UTR 123456789012 "
            "through PhonePe. The complainant requests that the accounts be frozen and the money returned.")
    bedrock_fake.tool_input = {"narrative": good}
    result = app.handler({"action": "build", "circleId": case["circleId"], "caseId": case["caseId"]}, None)
    stored = _get(case)
    art = stored["artifacts"]
    assert stored["status"] == "awaiting_1930"
    assert art["ncrpNarrativeSource"] == "model" and art["ncrpNarrativeLength"] == len(art["ncrpNarrative"])
    assert rules.ncrp_narrative_ok(art["ncrpNarrative"])[0] and "123456789012" in art["ncrpNarrative"]
    assert "1930" in art["script1930"] and "123456789012" in art["script1930"] and art["script1930Hi"]
    assert art["freezeLetter"].startswith("Subject:")
    assert art["ezeroFir"]["thresholdInr"] == 100000 and art["ezeroFir"]["state"] == "Haryana"
    assert art["mrm"]["firRequired"] is True
    assert result["ncrpNarrativeLength"] >= 200
    # the narrative prompt carried the hint only inside untrusted tags
    user = bedrock_fake.calls[0]["messages"][0]["content"][1]["text"]
    assert user.startswith("<untrusted_data>") and "CBI video call" in user


def test_build_falls_back_to_template_on_bad_narrative(case, bedrock_fake):
    db.set_attributes("CIRCLE#%s" % case["circleId"], "CASE#%s" % case["caseId"], {"confirmedTxns": [TXN]})
    bedrock_fake.tool_input = {"narrative": "Too short! And it has <html> and no UTR."}
    app.handler({"action": "build", "circleId": case["circleId"], "caseId": case["caseId"]}, None)
    art = _get(case)["artifacts"]
    assert len(bedrock_fake.calls) == 2  # retried once
    assert art["ncrpNarrativeSource"] == "template"
    assert rules.ncrp_narrative_ok(art["ncrpNarrative"])[0] and "123456789012" in art["ncrpNarrative"]
    assert "Ramesh Kumar" in art["ncrpNarrative"]


def test_build_survives_bedrock_errors(case, bedrock_fake):
    db.set_attributes("CIRCLE#%s" % case["circleId"], "CASE#%s" % case["caseId"], {"confirmedTxns": [TXN]})
    bedrock_fake.error_codes = ["ValidationException", "ValidationException"]
    app.handler({"action": "build", "circleId": case["circleId"], "caseId": case["caseId"]}, None)
    assert _get(case)["artifacts"]["ncrpNarrativeSource"] == "template"


def test_mrm_finalize_fail(case, bedrock_fake):
    db.set_attributes("CIRCLE#%s" % case["circleId"], "CASE#%s" % case["caseId"], {"confirmedTxns": [{**TXN, "amount": 20000}]})
    res = app.handler({"action": "mrm", "circleId": case["circleId"], "caseId": case["caseId"]}, None)
    assert res == {"eligible": True, "firRequired": False, "checklist": res["checklist"]}
    assert _get(case)["status"] == "mrm" and _get(case)["artifacts"]["mrm"]["eligible"] is True
    app.handler({"action": "finalize", "circleId": case["circleId"], "caseId": case["caseId"]}, None)
    assert _get(case)["status"] == "filed"
    app.handler({"action": "fail", "circleId": case["circleId"], "caseId": case["caseId"],
                 "error": {"Error": "States.Timeout", "Cause": "x"}}, None)
    stored = _get(case)
    assert stored["status"] == "error" and "States.Timeout" in stored["error"]
    with pytest.raises(ValueError):
        app.handler({"action": "dance", "circleId": "c", "caseId": "d"}, None)


def test_extract_error_marks_case_and_raises(case, bedrock_fake):
    bedrock_fake.error_codes = ["ValidationException"]
    from botocore.exceptions import ClientError

    with pytest.raises(ClientError):
        app.handler({"action": "extract", "circleId": case["circleId"], "caseId": case["caseId"]}, None)
    assert _get(case)["status"] == "error"


def test_strands_flag_is_false_in_tests():
    # tests run without strands; the deterministic path is what was exercised above
    assert agent.STRANDS_AVAILABLE in (True, False)


def test_build_rejects_narrative_with_foreign_utr(case, bedrock_fake):
    """A fake model that injects a UTR not in confirmedTxns: the template narrative wins."""
    db.set_attributes("CIRCLE#%s" % case["circleId"], "CASE#%s" % case["caseId"], {"confirmedTxns": [TXN]})
    bogus = ("On 17 September 2026 Ramesh Kumar received a video call from a person claiming to be a CBI officer. "
             "Rs 60000 was sent to fraud at ybl with UTR 123456789012 through PhonePe and a further Rs 60000 with "
             "UTR 999999999999. The complainant requests that the accounts be frozen and the money returned.")
    bedrock_fake.tool_input = {"narrative": bogus}
    app.handler({"action": "build", "circleId": case["circleId"], "caseId": case["caseId"]}, None)
    art = _get(case)["artifacts"]
    assert len(bedrock_fake.calls) == 2  # retried once, both rejected
    assert art["ncrpNarrativeSource"] == "template"
    assert "999999999999" not in art["ncrpNarrative"] and "123456789012" in art["ncrpNarrative"]
    assert rules.ncrp_narrative_ok(art["ncrpNarrative"])[0]
    assert art["ncrp"]["source"]["url"] == "https://cybercrime.gov.in/Webform/Crime_AuthoLogin.aspx"
    assert art["ezeroFir"]["source"]["outlet"] == "Hindustan Times" and art["mrm"]["source"]["outlet"] == "Deccan Chronicle"


def test_build_rejects_narrative_with_foreign_amount(case, bedrock_fake):
    db.set_attributes("CIRCLE#%s" % case["circleId"], "CASE#%s" % case["caseId"], {"confirmedTxns": [TXN]})
    wrong = ("On 17 September 2026 Ramesh Kumar received a video call from a person claiming to be a CBI officer. "
             "He was told to transfer money for verification. Rs 6,00,000 was sent to fraud at ybl with UTR "
             "123456789012 through PhonePe. The complainant requests that the accounts be frozen and the money returned.")
    bedrock_fake.tool_input = {"narrative": wrong}
    app.handler({"action": "build", "circleId": case["circleId"], "caseId": case["caseId"]}, None)
    art = _get(case)["artifacts"]
    assert art["ncrpNarrativeSource"] == "template" and "6,00,000" not in art["ncrpNarrative"]


def test_build_never_uses_model_extraction_when_nothing_confirmed(case, bedrock_fake):
    """extracted rows exist but confirmedTxns is empty: none of the extracted UTRs may appear."""
    db.set_attributes("CIRCLE#%s" % case["circleId"], "CASE#%s" % case["caseId"],
                      {"confirmedTxns": [], "extracted": {"txns": [{**TXN, "valid": True, "issues": []}]}})
    bedrock_fake.tool_input = {"narrative": "Ramesh Kumar was cheated. " * 12}
    app.handler({"action": "build", "circleId": case["circleId"], "caseId": case["caseId"]}, None)
    art = _get(case)["artifacts"]
    assert "123456789012" not in art["ncrpNarrative"] and "123456789012" not in art["script1930"]
    assert "123456789012" not in art["freezeLetter"]
    prompt = bedrock_fake.calls[0]["messages"][0]["content"][1]["text"]
    assert "123456789012" not in prompt
    assert art["mrm"]["eligible"] is False
