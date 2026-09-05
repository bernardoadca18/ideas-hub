from __future__ import annotations

from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest

from app.production_profiles import list_profiles
from app.prompts.workflows import get_workflow
from app.schemas.llm_outputs import LLMVisualQuery
from app.schemas.roteiro import RoteiroEstrutura
from app.services.script_generation_jobs import assemble_written_sections
from app.services.visual_requirements import (
    VisualRequirementsError,
    materialize_written_visual_queries,
    validate_preserved_visual_queries,
    visual_query_count_policy,
)


def _query(excerpt: str, *, source_note_id: UUID | None = None) -> LLMVisualQuery:
    return LLMVisualQuery(
        intent="illustration",
        query=f"gameplay relacionado a {excerpt}",
        narration_excerpt=excerpt,
        importance="preferred",
        source_note_id=source_note_id,
        desired_duration_seconds=30,
    )


def test_all_current_production_profiles_enable_structured_visual_queries() -> None:
    assert {
        profile.id: get_workflow(profile.workflow_roteiro).structured_visual_queries
        for profile in list_profiles()
    } == {
        "faceless_pop_culture_lists": True,
        "faceless_informational": True,
        "faceless_general": True,
        "faceless_pop_culture": True,
        "game_analysis": True,
    }


def test_long_section_requires_bounded_distributed_visual_requirements() -> None:
    assert visual_query_count_policy(125).minimum == 5
    assert visual_query_count_policy(600).maximum == 5

    content = "Abertura concreta. Primeiro argumento. Contraste central. Consequência real. Fechamento claro."
    run_id = uuid4()
    generated = [
        _query("Abertura concreta."),
        _query("Primeiro argumento."),
        _query("Contraste central."),
        _query("Consequência real."),
        _query("Fechamento claro."),
    ]
    first = materialize_written_visual_queries(
        generation_run_id=run_id,
        section_key="section-001",
        duration_seconds=125,
        content=content,
        generated=generated,
        evidence_dossier={},
    )
    second = materialize_written_visual_queries(
        generation_run_id=run_id,
        section_key="section-001",
        duration_seconds=125,
        content=content,
        generated=generated,
        evidence_dossier={},
    )

    assert [item.id for item in first] == [item.id for item in second]
    assert len({item.id for item in first}) == 5
    assert [item.order for item in first] == list(range(5))
    assert all(item.source_note_id is None for item in first)


def test_game_analysis_source_note_provenance_is_host_canonicalized() -> None:
    note_id = uuid4()
    session_id = uuid4()
    query = _query("Momento do combate.", source_note_id=note_id)
    result = materialize_written_visual_queries(
        generation_run_id=uuid4(),
        section_key="section-001",
        duration_seconds=20,
        content="Momento do combate.",
        generated=[query],
        evidence_dossier={
            "fragments": [
                {
                    "media_note_id": str(note_id),
                    "session_id": str(session_id),
                    "alignment": {"start_seconds": 12.5, "end_seconds": 19.0},
                }
            ]
        },
    )[0]

    assert result.source_note_id == note_id
    assert result.preferred_session_id == session_id
    assert result.preferred_start_seconds == 12.5
    assert result.preferred_end_seconds == 19.0


def test_unknown_source_note_and_non_literal_excerpt_are_rejected() -> None:
    with pytest.raises(VisualRequirementsError, match="literal, ordered"):
        materialize_written_visual_queries(
            generation_run_id=uuid4(),
            section_key="section-001",
            duration_seconds=20,
            content="Narração real.",
            generated=[_query("Paráfrase inventada.")],
            evidence_dossier={},
        )
    with pytest.raises(VisualRequirementsError, match="trusted media context"):
        materialize_written_visual_queries(
            generation_run_id=uuid4(),
            section_key="section-001",
            duration_seconds=20,
            content="Narração real.",
            generated=[_query("Narração real.", source_note_id=uuid4())],
            evidence_dossier={},
        )


def test_persist_reload_preserves_visual_query_identity() -> None:
    query_id = uuid4()
    payload = {
        "titulo": "Roteiro",
        "duracao_total_segundos": 60,
        "blocos": [
            {
                "tipo": "abertura",
                "duracao_segundos": 60,
                "conteudo": "Trecho persistido.",
                "visual_queries": [
                    {
                        "id": str(query_id),
                        "order": 0,
                        "intent": "illustration",
                        "query": "gameplay de abertura",
                        "narration_excerpt": "Trecho persistido.",
                        "importance": "required",
                    }
                ],
            }
        ],
    }
    first = RoteiroEstrutura.model_validate(payload)
    reloaded = RoteiroEstrutura.model_validate(first.model_dump(mode="json"))
    assert reloaded.blocos[0].visual_queries[0].id == query_id


def test_staged_section_assembly_keeps_materialized_visual_queries() -> None:
    query_id = uuid4()
    section = SimpleNamespace(
        section_order=0,
        section_key="section-001",
        section_plan={
            "title": "Abertura",
            "target_duration_seconds": 60,
            "purpose": "Abrir",
            "beats": [],
            "evidence_refs": [],
        },
        output={
            "content": "Trecho final.",
            "visual_queries": [
                {
                    "id": str(query_id),
                    "order": 0,
                    "intent": "illustration",
                    "query": "gameplay de abertura",
                    "narration_excerpt": "Trecho final.",
                    "importance": "required",
                }
            ],
            "claims_used": [],
            "beats_covered": [],
        },
    )
    block = assemble_written_sections([section], claim_ledger=[])[0]
    assert block.visual_queries[0].id == query_id
    assert block.visual_queries[0].narration_excerpt == "Trecho final."


def test_human_revision_must_preserve_existing_narration_bindings() -> None:
    query = type("Query", (), {"narration_excerpt": "Trecho original."})()
    validate_preserved_visual_queries(
        content="Antes. Trecho original. Depois.", queries=[query]
    )
    with pytest.raises(VisualRequirementsError, match="use script regeneration"):
        validate_preserved_visual_queries(content="Texto substituído.", queries=[query])
