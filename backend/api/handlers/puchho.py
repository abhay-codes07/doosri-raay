"""POST /puchho (authority | family), GET /puchho/{taskId}."""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from botocore.exceptions import ClientError

from common import auth, aws, config, db, push, quota, tasks, texts
from common.http import ApiError, ok

log = logging.getLogger(__name__)

AUDIO_KEY = "audio/i4c_%s.mp3"
URL_TTL = 3600


def _audio_exists(key: str) -> bool:
    try:
        aws.s3_client().head_object(Bucket=config.upload_bucket(), Key=key)
        return True
    except ClientError:
        return False


def _synthesize(text: str) -> bytes:
    polly = aws.polly_client()
    try:
        resp = polly.synthesize_speech(
            Text=text, OutputFormat="mp3", VoiceId=config.polly_voice_id(), Engine="neural", LanguageCode="hi-IN"
        )
    except ClientError as exc:
        log.warning("neural Polly failed (%s); falling back to Aditi standard", exc)
        resp = polly.synthesize_speech(
            Text=text, OutputFormat="mp3", VoiceId=config.POLLY_FALLBACK_VOICE_ID, Engine="standard", LanguageCode="hi-IN"
        )
    return resp["AudioStream"].read()


def authority_audio_url(lang: str) -> str:
    key = AUDIO_KEY % lang
    if not _audio_exists(key):
        speech = texts.I4C_SPEECH_HI if lang == "hi" else texts.I4C_SPEECH_EN
        audio = _synthesize(speech)
        aws.s3_client().put_object(Bucket=config.upload_bucket(), Key=key, Body=audio, ContentType="audio/mpeg")
    return aws.s3_client().generate_presigned_url(
        "get_object", Params={"Bucket": config.upload_bucket(), "Key": key}, ExpiresIn=URL_TTL
    )


def _guardians(members: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [m for m in members if m.get("role") in auth.GUARDIAN_ROLES]


def _inform_guardians(circle_id: str, members: List[Dict[str, Any]], parent_name: str, message: str) -> None:
    ctx = {"parent": parent_name, "message": message, "time": db.utcnow().astimezone(db.IST).strftime("%H:%M")}
    en, hi = texts.task_text("info", ctx)
    for g in _guardians(members):
        task = tasks.create_task(circle_id, "info", g["sub"], en, hi, context={"reason": "puchho"},
                                 expires_in=86400, assignee_name=g.get("name"))
        push.send_push(auth.load_profile(g["sub"]), push.build_payload(task))


def post_puchho(req: Any) -> Dict[str, Any]:
    profile, circle_id = auth.require_circle(req.sub)
    kind = req.body.get("kind")
    if kind not in ("authority", "family"):
        raise ApiError(400, "invalid_kind", "kind must be authority or family")
    quota.consume_quota(req.sub)
    members = db.circle_members(circle_id)
    parent_name = profile.get("name") or "Papa"
    if kind == "authority":
        lang = "en" if profile.get("lang") == "en" else "hi"
        url = authority_audio_url(lang)
        _inform_guardians(circle_id, members, parent_name, texts.I4C_LINE_EN)
        return ok({"audioUrl": url, "textHi": texts.I4C_LINE_HI_ROMAN, "textEn": texts.I4C_LINE_EN})
    return _family(req, profile, circle_id, members, parent_name)


def _family(req: Any, profile: Dict[str, Any], circle_id: str, members: List[Dict[str, Any]], parent_name: str) -> Dict[str, Any]:
    son = db.member_by_role(members, "son")
    targets = [son] if son else _guardians(members)
    if not targets:
        raise ApiError(400, "no_family", "No family member to ask")
    en, hi = texts.task_text("puchho_family", {"parent": parent_name})
    task_ids: List[str] = []
    for member in targets:
        task = tasks.create_task(circle_id, "puchho_family", member["sub"], en, hi,
                                 context={"parentSub": req.sub, "reason": "puchho"},
                                 expires_in=900, assignee_name=member.get("name"))
        task_ids.append(task["taskId"])
        push.send_push(auth.load_profile(member["sub"]), push.build_payload(task))
    _inform_guardians(circle_id, members, parent_name, "asked the family whether a call is real")
    return ok({"taskId": task_ids[0], "taskIds": task_ids}, status=202)


def get_puchho(req: Any) -> Dict[str, Any]:
    _, circle_id = auth.require_circle(req.sub)
    task = auth.ensure_same_circle(tasks.get_task_by_id(req.param("taskId")), circle_id)
    if task.get("kind") != "puchho_family":
        raise ApiError(404, "not_found", "Not found")
    status = "done" if task.get("status") == "done" else "open"
    outcome: Optional[str] = task.get("outcome") if status == "done" else None
    return ok({"status": status, "outcome": outcome, "codeWordMatched": task.get("codeWordMatched")})
