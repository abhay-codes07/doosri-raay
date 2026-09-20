#!/usr/bin/env python3
"""Documents you can prove: download every official source we cite, hash it, check every quote.

    python scripts/verify_sources.py [--s3] [--out docs/sources-manifest.json] [--timeout 60]

For each URL in ``backend/common/sources.py`` (OFFICIAL_SOURCES) plus every ``source.url`` used by
``backend/recovery_agent/rules_data.json`` and ``backend/classify_worker/patterns.json``:

  * fetch it with a browser-like User-Agent, failing closed on HTTP errors, on a content type that
    does not match the expected kind (``pdf`` / ``html``), and on a PDF that does not start with %PDF;
    TLS verification is never disabled (the Windows/macOS system store is used through ``truststore``
    when it is installed, which is what makes the NIC-signed *.gov.in certificates verify);
  * SHA-256 the bytes and record ``{url, sha256, bytes, contentType, fetchedAt, fetched, error}``;
  * extract text (pypdf for PDFs, tag-stripping for HTML) and check that every ``quote`` attached
    to that URL in the two JSON files appears in it (whitespace- and quote-mark-insensitive);
  * optionally (``--s3``, needs AWS credentials and UPLOAD_BUCKET) upload the bytes to
    ``sources/<sha256>.<ext>`` and the manifest to ``sources/manifest.json``.

Outlets that block scripts are recorded honestly with ``fetched: false`` and the HTTP status; the
entry is kept so the manifest still lists what we cite. Writes the manifest to ``--out`` AND to
``backend/common/sources_manifest.json`` (the copy bundled into the Lambda for ``GET /sources``).
Exit code is 0 when every quote that could be checked was found, 1 otherwise.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import html as html_mod
import io
import json
import os
import re
import ssl
import sys
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional, Tuple

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BACKEND = os.path.join(ROOT, "backend")
if BACKEND not in sys.path:
    sys.path.insert(0, BACKEND)

from common import sources as sources_mod  # noqa: E402

RULES_DATA = os.path.join(BACKEND, "recovery_agent", "rules_data.json")
PATTERNS = os.path.join(BACKEND, "classify_worker", "patterns.json")
DEFAULT_OUT = os.path.join(ROOT, "docs", "sources-manifest.json")
BUNDLED_OUT = sources_mod.BUNDLED_MANIFEST
USER_AGENT = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
              "Chrome/128.0 Safari/537.36")
EXT_FOR_KIND = {"pdf": "pdf", "html": "html"}


# --- text normalisation -------------------------------------------------------------------

_QUOTE_MAP = str.maketrans({"‘": "'", "’": "'", "“": '"', "”": '"', " ": " ",
                            "‑": "-", "–": "-", "—": "-"})


def normalise(text: str) -> str:
    """Lower-case, unify quote marks/dashes, drop ALL whitespace (PDF extraction inserts spaces
    inside words, news pages use non-breaking spaces around the rupee sign)."""
    text = html_mod.unescape(text or "").translate(_QUOTE_MAP).lower()
    return re.sub(r"\s+", "", text)


def html_to_text(raw: bytes) -> str:
    text = raw.decode("utf-8", "replace")
    text = re.sub(r"(?is)<(script|style|noscript).*?</\1>", " ", text)
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", html_mod.unescape(text))


def pdf_to_text(raw: bytes) -> Optional[str]:
    try:
        from pypdf import PdfReader  # type: ignore
    except ImportError:
        return None
    reader = PdfReader(io.BytesIO(raw))
    return "\n".join((page.extract_text() or "") for page in reader.pages)


# --- quotes from the data files ----------------------------------------------------------------

def _walk(node: Any, path: str, out: List[Tuple[str, str, str]]) -> None:
    """Collect (url, quote, path) for every dict that carries ``source.url`` and ``quote``."""
    if isinstance(node, dict):
        src = node.get("source")
        if isinstance(src, dict) and src.get("url") and node.get("quote"):
            out.append((src["url"], node["quote"], path))
        for key, value in node.items():
            _walk(value, "%s.%s" % (path, key) if path else str(key), out)
    elif isinstance(node, list):
        for i, value in enumerate(node):
            _walk(value, "%s[%d]" % (path, i), out)


def collect_quotes(paths: List[str]) -> List[Dict[str, str]]:
    quotes: List[Dict[str, str]] = []
    for file_path in paths:
        if not os.path.exists(file_path):
            continue
        with open(file_path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        found: List[Tuple[str, str, str]] = []
        _walk(data, "", found)
        rel = os.path.relpath(file_path, ROOT).replace(os.sep, "/")
        for url, quote, path in found:
            quotes.append({"file": rel, "path": path, "url": url, "quote": quote})
    return quotes


# --- fetching -------------------------------------------------------------------------------------

def _ssl_context() -> ssl.SSLContext:
    try:
        import truststore  # type: ignore

        return truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    except ImportError:
        return ssl.create_default_context()


def fetch(url: str, timeout: int) -> Tuple[Optional[bytes], Optional[str], Optional[int], Optional[str]]:
    """Return (bytes, contentType, httpStatus, error). Never disables TLS verification."""
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/pdf,*/*",
                                               "Accept-Language": "en-IN,en;q=0.9"})
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=_ssl_context()) as resp:
            return resp.read(), resp.headers.get("Content-Type"), resp.status, None
    except urllib.error.HTTPError as exc:
        return None, exc.headers.get("Content-Type") if exc.headers else None, exc.code, "HTTP %d" % exc.code
    except Exception as exc:  # noqa: BLE001 - recorded on the entry
        return None, None, None, "%s: %s" % (type(exc).__name__, exc)


def verify_one(entry: Dict[str, Any], quotes: List[Dict[str, str]], timeout: int) -> Dict[str, Any]:
    url = entry["url"]
    kind = entry.get("kind", "pdf" if url.lower().endswith(".pdf") else "html")
    raw, content_type, status, error = fetch(url, timeout)
    record: Dict[str, Any] = {
        "id": entry.get("id"),
        "title": entry.get("title"),
        "url": url,
        "kind": kind,
        "fetched": False,
        "httpStatus": status,
        "contentType": content_type,
        "sha256": None,
        "bytes": None,
        "fetchedAt": dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "error": error,
        "quotes": [],
    }
    text: Optional[str] = None
    if raw is not None and error is None:
        ct = (content_type or "").lower()
        if kind == "pdf":
            if not raw.startswith(b"%PDF"):
                record["error"] = "not a PDF (missing %PDF header)"
            elif "pdf" not in ct:
                record["error"] = "unexpected content type for a PDF: %s" % content_type
        elif "html" not in ct:
            record["error"] = "unexpected content type for a page: %s" % content_type
        if record["error"] is None:
            record["fetched"] = True
            record["sha256"] = hashlib.sha256(raw).hexdigest()
            record["bytes"] = len(raw)
            record["_raw"] = raw
            text = pdf_to_text(raw) if kind == "pdf" else html_to_text(raw)
            if text is None:
                record["error"] = "pypdf not installed; quotes not checked (pip install pypdf)"
    norm = normalise(text) if text else None
    for q in quotes:
        if q["url"] != url:
            continue
        found = (normalise(q["quote"]) in norm) if norm is not None else None
        record["quotes"].append({"file": q["file"], "path": q["path"], "quote": q["quote"], "quoteFound": found})
    record["quoteFound"] = (all(q["quoteFound"] for q in record["quotes"]) if record["quotes"] and norm is not None
                            else (None if record["quotes"] else None))
    return record


def upload_to_s3(records: List[Dict[str, Any]], manifest: Dict[str, Any]) -> None:
    import boto3  # local import: the script must run without boto3 when --s3 is not used

    bucket = os.environ.get("UPLOAD_BUCKET")
    if not bucket:
        raise SystemExit("--s3 needs UPLOAD_BUCKET in the environment")
    s3 = boto3.client("s3", region_name=os.environ.get("AWS_REGION", "ap-south-1"))
    for rec in records:
        raw = rec.get("_raw")
        if not raw:
            continue
        key = "sources/%s.%s" % (rec["sha256"], EXT_FOR_KIND.get(rec["kind"], "bin"))
        s3.put_object(Bucket=bucket, Key=key, Body=raw,
                      ContentType="application/pdf" if rec["kind"] == "pdf" else "text/html; charset=utf-8")
        rec["s3Key"] = key
        print("uploaded s3://%s/%s" % (bucket, key))
    body = json.dumps(_public(manifest), ensure_ascii=False, indent=2).encode("utf-8")
    s3.put_object(Bucket=bucket, Key=sources_mod.MANIFEST_S3_KEY, Body=body, ContentType="application/json")
    print("uploaded s3://%s/%s" % (bucket, sources_mod.MANIFEST_S3_KEY))


def _public(manifest: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(manifest)
    out["sources"] = [{k: v for k, v in rec.items() if k != "_raw"} for rec in manifest["sources"]]
    return out


def build_manifest(timeout: int) -> Dict[str, Any]:
    quotes = collect_quotes([RULES_DATA, PATTERNS])
    entries: List[Dict[str, Any]] = list(sources_mod.OFFICIAL_SOURCES)
    known = {e["url"] for e in entries}
    for q in quotes:
        if q["url"] not in known:
            known.add(q["url"])
            entries.append({"id": None, "url": q["url"], "kind": "pdf" if q["url"].lower().endswith(".pdf") else "html",
                            "title": None})
    records = [verify_one(e, quotes, timeout) for e in entries]
    fetched = [r for r in records if r["fetched"]]
    checked = [q for r in records for q in r["quotes"] if q["quoteFound"] is not None]
    found = [q for q in checked if q["quoteFound"]]
    unchecked = [q for r in records for q in r["quotes"] if q["quoteFound"] is None]
    summary = {
        "sources": len(records),
        "sourcesFetched": len(fetched),
        "sourcesNotFetched": [r["url"] for r in records if not r["fetched"]],
        "citations": len(quotes),
        "citationsVerified": len(found),
        "citationsMissing": [{"url": q["url"], "path": q["path"]} for q in checked if not q["quoteFound"]],
        "citationsUnchecked": len(unchecked),
    }
    return {
        "generatedAt": dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "generator": "scripts/verify_sources.py",
        "summary": summary,
        "sources": records,
    }


def print_summary(manifest: Dict[str, Any]) -> None:
    s = manifest["summary"]
    print("")
    print("=" * 78)
    print("Verified %d official sources and %d rule citations" % (s["sourcesFetched"], s["citationsVerified"]))
    print("=" * 78)
    for rec in manifest["sources"]:
        state = "OK  " if rec["fetched"] else "MISS"
        sha = (rec["sha256"] or "")[:12]
        extra = "%s %s bytes" % (sha, rec["bytes"]) if rec["fetched"] else (rec["error"] or "not fetched")
        print("%s %-4s %-58s %s" % (state, rec["kind"], rec["url"][:58], extra))
        for q in rec["quotes"]:
            mark = {True: "  quote ok   ", False: "  QUOTE MISS ", None: "  quote ?    "}[q["quoteFound"]]
            print("%s%s: \"%s\"" % (mark, q["path"], q["quote"][:70] + ("..." if len(q["quote"]) > 70 else "")))
    print("-" * 78)
    print("sources fetched %d/%d; citations verified %d/%d (%d could not be checked)" % (
        s["sourcesFetched"], s["sources"], s["citationsVerified"], s["citations"], s["citationsUnchecked"]))
    if s["sourcesNotFetched"]:
        print("not fetched (recorded with fetched=false): %s" % ", ".join(s["sourcesNotFetched"]))
    if s["citationsMissing"]:
        print("MISSING quotes: %s" % json.dumps(s["citationsMissing"]))


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default=DEFAULT_OUT)
    ap.add_argument("--s3", action="store_true", help="also upload sources/<sha256>.<ext> and sources/manifest.json")
    ap.add_argument("--timeout", type=int, default=60)
    args = ap.parse_args(argv)

    manifest = build_manifest(args.timeout)
    if args.s3:
        upload_to_s3(manifest["sources"], manifest)
    public = _public(manifest)
    for path in (args.out, BUNDLED_OUT):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(public, fh, ensure_ascii=False, indent=2)
            fh.write("\n")
        print("wrote %s" % os.path.relpath(path, ROOT))
    print_summary(public)
    return 0 if not public["summary"]["citationsMissing"] else 1


if __name__ == "__main__":
    sys.exit(main())
