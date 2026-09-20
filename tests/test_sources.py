"""Documents you can prove: the bundled manifest, the S3 override, and the verifier's pure parts."""
from __future__ import annotations

import importlib.util
import json
import os
import sys

import boto3

from common import sources

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _verifier():
    path = os.path.join(ROOT, "scripts", "verify_sources.py")
    spec = importlib.util.spec_from_file_location("verify_sources", path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["verify_sources"] = mod
    spec.loader.exec_module(mod)
    return mod


def test_bundled_manifest_is_committed_and_verified():
    manifest = sources.load_bundled_manifest()
    assert manifest and manifest["generator"] == "scripts/verify_sources.py"
    urls = {s["url"] for s in manifest["sources"]}
    assert set(sources.official_urls()) <= urls
    summary = manifest["summary"]
    assert summary["citationsMissing"] == []
    assert summary["citationsVerified"] == summary["citations"] - summary["citationsUnchecked"]
    assert summary["sourcesFetched"] >= 12
    i4c = next(s for s in manifest["sources"] if s["url"] == sources.I4C_ADVISORY_URL)
    assert i4c["fetched"] and i4c["kind"] == "pdf" and len(i4c["sha256"]) == 64 and i4c["bytes"] > 1000
    assert all(q["quoteFound"] for q in i4c["quotes"])
    # an outlet that blocks scripts is recorded honestly, entry kept
    for s in manifest["sources"]:
        if not s["fetched"]:
            assert s["error"] and s["sha256"] is None
    docs_copy = json.load(open(os.path.join(ROOT, "docs", "sources-manifest.json"), encoding="utf-8"))
    assert docs_copy["generatedAt"] == manifest["generatedAt"]


def test_load_manifest_prefers_s3_then_bundled(monkeypatch):
    assert sources.load_manifest()["origin"] == "bundled"
    s3 = boto3.client("s3", region_name="ap-south-1")
    s3.put_object(Bucket="doosriraay-test-uploads", Key="sources/manifest.json",
                  Body=json.dumps({"generatedAt": "x", "sources": [], "summary": {"sources": 0}}).encode())
    got = sources.load_manifest()
    assert got["origin"] == "s3" and got["generatedAt"] == "x"
    s3.put_object(Bucket="doosriraay-test-uploads", Key="sources/manifest.json", Body=b"not json")
    assert sources.load_manifest()["origin"] == "bundled"
    monkeypatch.setattr(sources, "BUNDLED_MANIFEST", "/nonexistent.json")
    s3.delete_object(Bucket="doosriraay-test-uploads", Key="sources/manifest.json")
    assert sources.load_manifest()["origin"] == "none"


def test_get_sources_returns_manifest(api, family):
    status, body = api("GET", "/sources", family["guardian1"])
    assert status == 200 and body["origin"] == "bundled"
    assert body["summary"]["citationsVerified"] >= 20
    assert any(s["url"] == sources.I4C_ADVISORY_URL for s in body["sources"])
    assert [o["id"] for o in body["official"]][0] == "i4c_advisory_digital_arrest"


def test_verifier_normalisation_and_quote_collection():
    v = _verifier()
    assert v.normalise("Real law enforcement won’t  arrest\nyou") == v.normalise("real law enforcement won't arrest you")
    assert v.normalise("₹ 1 lakh") == v.normalise("₹1lakh")
    assert v.html_to_text(b"<p>Hi <b>there</b><script>x()</script>&amp; you</p>") == " Hi there & you "
    quotes = v.collect_quotes([v.RULES_DATA, v.PATTERNS])
    assert len(quotes) >= 25
    assert all(q["url"].startswith("https://") and q["quote"] for q in quotes)
    files = {q["file"] for q in quotes}
    assert files == {"backend/recovery_agent/rules_data.json", "backend/classify_worker/patterns.json"}


def test_verifier_fails_closed_on_bad_content(monkeypatch):
    v = _verifier()
    monkeypatch.setattr(v, "fetch", lambda url, timeout: (b"<html>not a pdf</html>", "text/html", 200, None))
    rec = v.verify_one({"url": "https://example.gov/x.pdf", "kind": "pdf"}, [], 5)
    assert rec["fetched"] is False and "PDF" in rec["error"] and rec["sha256"] is None
    monkeypatch.setattr(v, "fetch", lambda url, timeout: (None, None, 403, "HTTP 403"))
    rec = v.verify_one({"url": "https://example.org/", "kind": "html"},
                       [{"url": "https://example.org/", "quote": "q", "file": "f", "path": "p"}], 5)
    assert rec["fetched"] is False and rec["httpStatus"] == 403 and rec["quotes"][0]["quoteFound"] is None
    monkeypatch.setattr(v, "fetch", lambda url, timeout: (b"<p>The quick brown fox.</p>", "text/html; charset=utf-8", 200, None))
    rec = v.verify_one({"url": "https://example.org/", "kind": "html"},
                       [{"url": "https://example.org/", "quote": "quick  brown", "file": "f", "path": "p"},
                        {"url": "https://example.org/", "quote": "slow fox", "file": "f", "path": "p2"}], 5)
    assert rec["fetched"] and rec["quotes"][0]["quoteFound"] is True and rec["quotes"][1]["quoteFound"] is False
    assert rec["quoteFound"] is False
