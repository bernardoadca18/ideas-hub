from __future__ import annotations

from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.schemas.manual_script_import import ManualScriptImportRequest


def valid_payload() -> dict:
    return {
        "ideia_id": str(uuid4()),
        "source_filename": "roteiro.json",
        "script": {
            "schema": "neovids_manual_script_v1",
            "title": "GTA IV ainda parece vivo",
            "blocks": [
                {
                    "type": "abertura",
                    "text": "Existe uma coisa estranha quando você volta para GTA IV.",
                }
            ],
            "tags": ["GTA IV"],
            "references": [],
        },
    }


def test_minimum_valid_file() -> None:
    request = ManualScriptImportRequest.model_validate(valid_payload())
    assert request.script.schema_version == "neovids_manual_script_v1"
    assert request.script.blocks[0].duration_seconds is None


def test_multiple_blocks_and_explicit_duration() -> None:
    payload = valid_payload()
    payload["script"]["blocks"].append(
        {
            "type": "conclusao",
            "text": "É por isso que essa cidade ainda deixa marcas.",
            "duration_seconds": 42,
        }
    )
    request = ManualScriptImportRequest.model_validate(payload)
    assert len(request.script.blocks) == 2
    assert request.script.blocks[1].duration_seconds == 42


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("script", "schema"), "unknown"),
        (("script", "title"), "   "),
        (("script", "blocks"), []),
        (("script", "blocks", 0, "text"), "\n\t"),
        (("script", "blocks", 0, "duration_seconds"), 0),
        (("ideia_id",), "not-a-uuid"),
    ],
)
def test_invalid_structural_values_are_rejected(
    path: tuple[str | int, ...], value: object
) -> None:
    payload = valid_payload()
    target: object = payload
    for key in path[:-1]:
        target = target[key]  # type: ignore[index]
    target[path[-1]] = value  # type: ignore[index]
    with pytest.raises(ValidationError):
        ManualScriptImportRequest.model_validate(payload)


@pytest.mark.parametrize(
    ("container", "field", "value"),
    [
        ("script", "visual_queries", []),
        ("script", "duration_contract", {}),
        ("script", "production_profile", "game_analysis"),
        ("block", "visual_beat_id", str(uuid4())),
        ("block", "coverage_start_char", 0),
        ("block", "preferred_session_id", str(uuid4())),
    ],
)
def test_host_owned_or_unknown_fields_are_rejected(
    container: str, field: str, value: object
) -> None:
    payload = valid_payload()
    target = (
        payload["script"] if container == "script" else payload["script"]["blocks"][0]
    )
    target[field] = value
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        ManualScriptImportRequest.model_validate(payload)


@pytest.mark.parametrize(
    "filename", ["../roteiro.json", "/tmp/roteiro.json", "roteiro.txt", "a\\b.json"]
)
def test_source_filename_must_be_a_json_basename(filename: str) -> None:
    payload = valid_payload()
    payload["source_filename"] = filename
    with pytest.raises(ValidationError):
        ManualScriptImportRequest.model_validate(payload)


def test_media_scope_validates_uuids_and_duplicate_sessions() -> None:
    payload = valid_payload()
    session_id = str(uuid4())
    payload["script"]["media"] = {
        "project_id": str(uuid4()),
        "session_ids": [session_id, session_id],
    }
    with pytest.raises(ValidationError, match="session_ids must be unique"):
        ManualScriptImportRequest.model_validate(payload)


def test_narration_is_not_whitespace_normalized() -> None:
    payload = valid_payload()
    narration = "Linha um.\n\n  Linha dois preservada."
    payload["script"]["blocks"][0]["text"] = narration
    request = ManualScriptImportRequest.model_validate(payload)
    assert request.script.blocks[0].text == narration
