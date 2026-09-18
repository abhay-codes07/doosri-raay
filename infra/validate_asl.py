#!/usr/bin/env python
"""Static checks for the Step Functions definitions in infra/statemachines/.

Checks, per state machine:
  * the JSON parses and has exactly one top-level StartAt that names an existing state;
  * every state referenced by Next / Default / Catch[].Next / Choices[].Next exists;
  * at least one terminal state (Succeed / Fail / End: true) exists and every non-terminal
    state has a way out (Next, or Choices+Default for Choice states);
  * every ${Placeholder} used in the definition is declared in the matching
    AWS::Serverless::StateMachine.DefinitionSubstitutions of infra/template.yaml, and vice versa;
  * every state is reachable from StartAt.

Also asserts infra/template.yaml is plain-YAML parsable (long-form intrinsics only).

Usage: python infra/validate_asl.py            (exit code 0 = all good)
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

try:
    import yaml  # type: ignore
except ImportError:  # pragma: no cover
    print("pyyaml is required: pip install pyyaml", file=sys.stderr)
    sys.exit(2)

INFRA = Path(__file__).resolve().parent
TEMPLATE = INFRA / "template.yaml"
SM_DIR = INFRA / "statemachines"
PLACEHOLDER = re.compile(r"\$\{([A-Za-z0-9_]+)\}")
TERMINAL_TYPES = {"Succeed", "Fail"}


def load_template() -> dict:
    with TEMPLATE.open(encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def template_substitutions(template: dict) -> dict[str, tuple[str, set[str]]]:
    """Map DefinitionUri (as written, e.g. statemachines/watch.asl.json) -> (logical id, subs)."""
    out: dict[str, tuple[str, set[str]]] = {}
    for logical_id, res in (template.get("Resources") or {}).items():
        if res.get("Type") != "AWS::Serverless::StateMachine":
            continue
        props = res.get("Properties") or {}
        uri = props.get("DefinitionUri")
        if not isinstance(uri, str):
            continue
        subs = set((props.get("DefinitionSubstitutions") or {}).keys())
        out[uri.replace("\\", "/")] = (logical_id, subs)
    return out


def walk_states(states: dict, prefix: str = "") -> dict[str, dict]:
    """Flatten nested Parallel/Map branches so their states are validated too."""
    flat: dict[str, dict] = {}
    for name, st in states.items():
        flat[prefix + name] = st
        for branch in st.get("Branches") or []:
            flat.update(walk_states(branch.get("States") or {}, prefix + name + "/"))
        for key in ("Iterator", "ItemProcessor"):
            if key in st:
                flat.update(walk_states(st[key].get("States") or {}, prefix + name + "/"))
    return flat


def referenced_names(state: dict) -> list[tuple[str, str]]:
    refs: list[tuple[str, str]] = []
    if "Next" in state:
        refs.append(("Next", state["Next"]))
    if "Default" in state:
        refs.append(("Default", state["Default"]))
    for i, choice in enumerate(state.get("Choices") or []):
        if "Next" in choice:
            refs.append((f"Choices[{i}].Next", choice["Next"]))
    for i, catch in enumerate(state.get("Catch") or []):
        if "Next" in catch:
            refs.append((f"Catch[{i}].Next", catch["Next"]))
    return refs


def validate_machine(path: Path, expected_subs: set[str] | None, errors: list[str]) -> None:
    label = path.as_posix().split("/infra/")[-1]
    try:
        definition = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        errors.append(f"{label}: invalid JSON: {exc}")
        return

    # Exactly one StartAt at the top level (nested branches have their own).
    if list(definition.keys()).count("StartAt") != 1 or "StartAt" not in definition:
        errors.append(f"{label}: top-level StartAt missing")
        return
    states = definition.get("States") or {}
    if not isinstance(states, dict) or not states:
        errors.append(f"{label}: States must be a non-empty object")
        return
    start = definition["StartAt"]
    if start not in states:
        errors.append(f"{label}: StartAt '{start}' is not a state")

    # Reference integrity (top-level graph; nested graphs checked with their own namespace).
    def check_graph(graph: dict, scope: str) -> None:
        names = set(graph.keys())
        terminal = False
        for name, st in graph.items():
            stype = st.get("Type")
            if stype in TERMINAL_TYPES or st.get("End") is True:
                terminal = True
            for where, target in referenced_names(st):
                if target not in names:
                    errors.append(f"{label}: {scope}{name}.{where} -> unknown state '{target}'")
            if stype == "Choice":
                if not st.get("Choices"):
                    errors.append(f"{label}: {scope}{name} is a Choice with no Choices")
                if "Default" not in st:
                    errors.append(f"{label}: {scope}{name} is a Choice with no Default")
            elif stype not in TERMINAL_TYPES:
                if "Next" not in st and st.get("End") is not True:
                    errors.append(f"{label}: {scope}{name} has neither Next nor End")
            if stype == "Task" and "TimeoutSecondsPath" in st and "TimeoutSeconds" in st:
                errors.append(f"{label}: {scope}{name} sets both TimeoutSeconds and TimeoutSecondsPath")
            if stype == "Task" and "waitForTaskToken" in str(st.get("Resource", "")):
                params = json.dumps(st.get("Parameters") or {})
                if "$$.Task.Token" not in params:
                    errors.append(f"{label}: {scope}{name} uses waitForTaskToken but never passes $$.Task.Token")
        if not terminal:
            errors.append(f"{label}: {scope or 'top level'} has no terminal state (Succeed/Fail/End)")

        # Reachability from StartAt within this graph.
        start_name = definition["StartAt"] if scope == "" else None
        if start_name in names:
            seen: set[str] = set()
            stack = [start_name]
            while stack:
                cur = stack.pop()
                if cur in seen or cur not in graph:
                    continue
                seen.add(cur)
                stack.extend(t for _, t in referenced_names(graph[cur]))
            for unreachable in sorted(names - seen):
                errors.append(f"{label}: state '{unreachable}' is unreachable from StartAt")

    check_graph(states, "")
    for name, st in walk_states(states).items():
        for branch in st.get("Branches") or []:
            check_graph(branch.get("States") or {}, name + "/")
        for key in ("Iterator", "ItemProcessor"):
            if key in st:
                check_graph(st[key].get("States") or {}, name + "/")

    # ${Placeholder} <-> DefinitionSubstitutions.
    used = set(PLACEHOLDER.findall(path.read_text(encoding="utf-8")))
    if expected_subs is None:
        errors.append(f"{label}: no AWS::Serverless::StateMachine in template.yaml points at this file")
    else:
        for missing in sorted(used - expected_subs):
            errors.append(f"{label}: uses ${{{missing}}} but template.yaml has no DefinitionSubstitution for it")
        for unused in sorted(expected_subs - used):
            errors.append(f"{label}: template.yaml declares substitution '{unused}' that the definition never uses")

    print(f"ok  {label}: {len(walk_states(states))} states, substitutions {sorted(used)}")


def main() -> int:
    errors: list[str] = []
    try:
        template = load_template()
    except yaml.YAMLError as exc:
        print(f"FAIL infra/template.yaml is not plain YAML (use long-form Fn::Sub/Ref/Fn::GetAtt): {exc}")
        return 1
    if template.get("Transform") != "AWS::Serverless-2016-10-31":
        errors.append("template.yaml: Transform must be AWS::Serverless-2016-10-31")
    subs_by_uri = template_substitutions(template)
    print(f"ok  infra/template.yaml: plain YAML, {len(template.get('Resources') or {})} resources, "
          f"{len(subs_by_uri)} state machines")

    files = sorted(SM_DIR.glob("*.asl.json"))
    if not files:
        errors.append(f"no *.asl.json files under {SM_DIR}")
    for path in files:
        uri = f"statemachines/{path.name}"
        expected = subs_by_uri.get(uri, (None, None))[1]
        validate_machine(path, expected, errors)
    for uri in subs_by_uri:
        if not (INFRA / uri).exists():
            errors.append(f"template.yaml: DefinitionUri '{uri}' does not exist")

    if errors:
        print()
        for err in errors:
            print(f"FAIL {err}")
        print(f"\n{len(errors)} problem(s) found")
        return 1
    print("\nall state machine checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
