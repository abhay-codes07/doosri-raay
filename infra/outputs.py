#!/usr/bin/env python
"""Read the deployed stack's outputs and print them as KEY=VALUE lines (or write frontend/.env.local).

Used by the Makefile instead of `$(shell sam list stack-outputs ...)` + text munging, which is fragile
on Windows (quoting, CRLF, table output). Everything goes through `sam list stack-outputs --output json`.

Usage
  python infra/outputs.py --stack-name doosriraay --region ap-south-1          KEY=VALUE per line
  python infra/outputs.py ... --shell                                           KEY='VALUE' (safe for `eval`)
  python infra/outputs.py ... --vite frontend/.env.local                        write the VITE_* file
  sam list stack-outputs --stack-name doosriraay --output json | python infra/outputs.py --input -

Exit code 1 (with a hint) when the stack cannot be read, e.g. no AWS credentials or not deployed yet.
"""
from __future__ import annotations

import argparse
import json
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

# Stack output -> frontend/.env.local variable (see frontend/.env.example).
VITE_KEYS = {
    "VITE_API_URL": "ApiUrl",
    "VITE_USER_POOL_ID": "UserPoolId",
    "VITE_USER_POOL_CLIENT_ID": "UserPoolClientId",
    "VITE_REGION": "Region",
}


def parse_outputs(text: str) -> dict[str, str]:
    """Accept `sam list stack-outputs --output json`, `aws cloudformation describe-stacks`, or {key: value}."""
    start = min((i for i in (text.find("["), text.find("{")) if i >= 0), default=-1)
    if start < 0:
        raise ValueError("no JSON found in the input")
    data = json.loads(text[start:])
    if isinstance(data, dict) and "Stacks" in data:  # aws cloudformation describe-stacks
        stacks = data.get("Stacks") or []
        data = (stacks[0].get("Outputs") or []) if stacks else []
    if isinstance(data, dict):
        return {str(k): str(v) for k, v in data.items()}
    out: dict[str, str] = {}
    for item in data:
        if isinstance(item, dict) and "OutputKey" in item:
            out[str(item["OutputKey"])] = str(item.get("OutputValue", ""))
    if not out:
        raise ValueError("the JSON has no OutputKey/OutputValue entries")
    return out


def fetch_outputs(sam: str, stack: str, region: str, profile: str | None) -> dict[str, str]:
    exe = shutil.which(sam) or sam
    cmd = [exe, "list", "stack-outputs", "--stack-name", stack, "--region", region, "--output", "json"]
    if profile:
        cmd += ["--profile", profile]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    except OSError as exc:
        sys.exit(f"cannot run {sam!r}: {exc}\nhint: make SAM=/path/to/sam.exe ... or add the SAM CLI to PATH")
    if proc.returncode != 0:
        sys.stderr.write(proc.stderr or proc.stdout)
        sys.exit(f"sam list stack-outputs failed for stack {stack!r} in {region}\n"
                 "hint: are AWS credentials configured (aws sts get-caller-identity) and is the stack deployed?")
    try:
        return parse_outputs(proc.stdout)
    except ValueError as exc:
        sys.stderr.write(proc.stdout)
        sys.exit(f"could not parse sam output: {exc}")


def write_vite_env(path: Path, outputs: dict[str, str]) -> None:
    missing = [k for k, v in VITE_KEYS.items() if v not in outputs]
    if missing:
        sys.exit(f"stack outputs lack {', '.join(VITE_KEYS[k] for k in missing)}; redeploy with the current template")
    managed = {k: outputs[v] for k, v in VITE_KEYS.items()}
    lines: list[str] = []
    seen: set[str] = set()
    if path.exists():  # keep VITE_VAPID_PUBLIC_KEY, VITE_DEMO_PARENT_EMAIL and anything else the dev added
        for line in path.read_text(encoding="utf-8").splitlines():
            key = line.split("=", 1)[0].strip() if "=" in line and not line.lstrip().startswith("#") else None
            if key in managed:
                lines.append(f"{key}={managed[key]}")
                seen.add(key)
            else:
                lines.append(line)
    else:
        lines.append("# Written by `make env` from the stack outputs; VITE_* keys below are overwritten on each run.")
    for key, value in managed.items():
        if key not in seen:
            lines.append(f"{key}={value}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines).rstrip("\n") + "\n", encoding="utf-8", newline="\n")
    print(f"wrote {path.as_posix()}:")
    for key, value in managed.items():
        print(f"  {key}={value}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--stack-name", default="doosriraay")
    ap.add_argument("--region", default="ap-south-1")
    ap.add_argument("--profile", default=None)
    ap.add_argument("--sam", default="sam", help="SAM CLI executable (default: sam on PATH)")
    ap.add_argument("--input", default=None, metavar="FILE", help="read outputs JSON from FILE ('-' = stdin) instead of calling sam")
    ap.add_argument("--shell", action="store_true", help="print KEY='VALUE' lines suitable for `eval`")
    ap.add_argument("--vite", default=None, metavar="PATH", help="write PATH (e.g. frontend/.env.local) with the VITE_* variables")
    args = ap.parse_args()

    if args.input:
        text = sys.stdin.read() if args.input == "-" else Path(args.input).read_text(encoding="utf-8")
        try:
            outputs = parse_outputs(text)
        except (ValueError, json.JSONDecodeError) as exc:
            sys.exit(f"could not parse outputs: {exc}")
    else:
        outputs = fetch_outputs(args.sam, args.stack_name, args.region, args.profile)

    if args.vite:
        write_vite_env(Path(args.vite), outputs)
        return 0
    for key, value in outputs.items():
        print(f"{key}={shlex.quote(value) if args.shell else value}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
