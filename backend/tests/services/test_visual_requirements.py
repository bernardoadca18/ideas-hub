from __future__ import annotations

from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest

from app.production_profiles import list_profiles
from app.prompts.workflows import get_workflow
from app.schemas.llm_outputs import LLMVisualBeatQuery, VisualBeatEnrichmentOutput
from app.schemas.roteiro import RoteiroEstrutura
from app.services.script_generation_jobs import assemble_written_sections
from app.services.visual_requirements import (
    VisualRequirementsError,
    materialize_written_visual_queries,
    segment_visual_beats,
    validate_preserved_visual_queries,
    validate_visual_readiness,
    visual_beat_batches,
    visual_query_count_policy,
)


def _content(sentence_count: int) -> str:
    return " ".join(
        f"Esta é a sentença número {index}, com conteúdo útil em português."
        for index in range(sentence_count)
    )


def _semantic(order: int, *, source_note_id: UUID | None = None) -> LLMVisualBeatQuery:
    return LLMVisualBeatQuery(
        beat_order=order,
        intent="illustration",
        query=f"gameplay relacionado ao beat {order}",
        importance="preferred",
        source_note_id=source_note_id,
    )


def _materialized(content: str, duration: int, *, section_key: str = "section-001"):
    beats = segment_visual_beats(
        section_key=section_key, content=content, duration_seconds=duration
    )
    return materialize_written_visual_queries(
        generation_run_id=uuid4(),
        section_key=section_key,
        duration_seconds=duration,
        content=content,
        generated=[_semantic(beat.order) for beat in beats],
        evidence_dossier={},
        beats=beats,
    )


def test_all_current_production_profiles_enable_structured_visual_queries() -> None:
    assert all(
        get_workflow(profile.workflow_roteiro).structured_visual_queries
        and profile.visual_requirements.requires_visual_queries_for_final
        for profile in list_profiles()
    )


@pytest.mark.parametrize(
    ("duration", "expected"), [(20, 1), (60, 2), (125, 5), (600, 20)]
)
def test_visual_density_scales_with_duration_without_five_query_cap(
    duration: int, expected: int
) -> None:
    policy = visual_query_count_policy(duration)
    assert policy.minimum == policy.maximum == expected
    beats = segment_visual_beats(
        section_key="section-001",
        content=_content(max(expected * 2, 2)),
        duration_seconds=duration,
    )
    assert len(beats) == expected


def test_three_realistic_long_form_sections_produce_24_contiguous_beats() -> None:
    durations = [204, 239, 270]
    sections = [
        segment_visual_beats(
            section_key=f"section-{index:03d}",
            content=_content(30),
            duration_seconds=duration,
        )
        for index, duration in enumerate(durations)
    ]
    assert [len(items) for items in sections] == [7, 8, 9]
    assert sum(map(len, sections)) == 24


def test_segmentation_is_deterministic_contiguous_and_lossless() -> None:
    content = (
        "Abertura com ação e acentuação.\n\n"
        "Segundo parágrafo: contexto necessário; contraste útil. "
        "Uma sentença excepcionalmente longa ainda preserva cada caractere, inclusive espaços. "
        "Conclusão clara!"
    )
    first = segment_visual_beats(
        section_key="unicode", content=content, duration_seconds=125
    )
    second = segment_visual_beats(
        section_key="unicode", content=content, duration_seconds=125
    )
    assert first == second
    assert first[0].start_char == 0
    assert first[-1].end_char == len(content)
    assert all(left.end_char == right.start_char for left, right in zip(first, first[1:]))
    assert "".join(beat.text for beat in first) == content
    assert len({beat.id for beat in first}) == len(first)


def test_llm_schema_cannot_own_excerpt_span_or_duration() -> None:
    properties = LLMVisualBeatQuery.model_json_schema()["properties"]
    assert set(properties) == {
        "beat_order",
        "intent",
        "query",
        "importance",
        "source_note_id",
        "notes",
    }


def test_materialization_uses_host_anchor_and_stable_ids() -> None:
    content = _content(10)
    beats = segment_visual_beats(
        section_key="section-001", content=content, duration_seconds=125
    )
    run_id = uuid4()
    values = [_semantic(beat.order) for beat in beats]
    first = materialize_written_visual_queries(
        generation_run_id=run_id,
        section_key="section-001",
        duration_seconds=125,
        content=content,
        generated=values,
        evidence_dossier={},
        beats=beats,
    )
    second = materialize_written_visual_queries(
        generation_run_id=run_id,
        section_key="section-001",
        duration_seconds=125,
        content=content,
        generated=values,
        evidence_dossier={},
        beats=beats,
    )
    assert [item.id for item in first] == [item.id for item in second]
    for query, beat in zip(first, beats, strict=True):
        assert query.visual_beat_id == beat.id
        assert query.narration_excerpt == content[beat.start_char : beat.end_char]
        assert query.coverage_start_char == beat.start_char
        assert query.coverage_end_char == beat.end_char
        assert query.desired_duration_seconds == beat.estimated_duration_seconds


def test_batches_bound_calls_but_not_editorial_query_count() -> None:
    beats = segment_visual_beats(
        section_key="long", content=_content(40), duration_seconds=600
    )
    batches = visual_beat_batches(beats)
    assert len(beats) == 20
    assert [len(batch) for batch in batches] == [5, 5, 5, 5]
    assert [beat.order for batch in batches for beat in batch] == list(range(20))


def test_game_analysis_source_note_provenance_is_host_canonicalized() -> None:
    note_id = uuid4()
    session_id = uuid4()
    content = "Momento do combate."
    beats = segment_visual_beats(
        section_key="game", content=content, duration_seconds=20
    )
    result = materialize_written_visual_queries(
        generation_run_id=uuid4(),
        section_key="game",
        duration_seconds=20,
        content=content,
        generated=[_semantic(0, source_note_id=note_id)],
        evidence_dossier={
            "fragments": [
                {
                    "media_note_id": str(note_id),
                    "session_id": str(session_id),
                    "alignment": {"start_seconds": 12.5, "end_seconds": 19.0},
                }
            ]
        },
        beats=beats,
    )[0]
    assert result.source_note_id == note_id
    assert result.preferred_session_id == session_id
    assert result.preferred_start_seconds == 12.5
    assert result.preferred_end_seconds == 19.0


def test_unknown_source_note_and_missing_beat_are_rejected() -> None:
    content = _content(4)
    beats = segment_visual_beats(
        section_key="section", content=content, duration_seconds=60
    )
    with pytest.raises(VisualRequirementsError, match="returned 1 items for 2"):
        materialize_written_visual_queries(
            generation_run_id=uuid4(),
            section_key="section",
            duration_seconds=60,
            content=content,
            generated=[_semantic(0)],
            evidence_dossier={},
            beats=beats,
        )
    with pytest.raises(VisualRequirementsError, match="trusted media context"):
        materialize_written_visual_queries(
            generation_run_id=uuid4(),
            section_key="section",
            duration_seconds=60,
            content=content,
            generated=[_semantic(beat.order, source_note_id=uuid4()) for beat in beats],
            evidence_dossier={},
            beats=beats,
        )


def test_visual_readiness_requires_full_host_owned_coverage() -> None:
    content = _content(8)
    queries = _materialized(content, 60)
    structure = RoteiroEstrutura.model_validate(
        {
            "titulo": "Roteiro",
            "duracao_total_segundos": 60,
            "blocos": [
                {
                    "tipo": "narracao",
                    "duracao_segundos": 60,
                    "conteudo": content,
                    "visual_queries": [item.to_dict() for item in queries],
                }
            ],
        }
    )
    ready = validate_visual_readiness(structure)
    assert ready.status == "ready"
    assert ready.textual_coverage_ratio == 1.0
    assert ready.visual_beat_count == 2
    broken = structure.model_copy(deep=True)
    broken.blocos[0].visual_queries.pop()
    report = validate_visual_readiness(broken)
    assert report.status == "not_ready"
    assert report.textual_coverage_ratio < 1
    assert report.missing_ranges


def test_persist_reload_preserves_host_beat_identity_and_offsets() -> None:
    content = _content(8)
    query = _materialized(content, 20)[0]
    payload = {
        "titulo": "Roteiro",
        "duracao_total_segundos": 20,
        "blocos": [
            {
                "tipo": "abertura",
                "duracao_segundos": 20,
                "conteudo": content,
                "visual_queries": [query.to_dict()],
            }
        ],
    }
    first = RoteiroEstrutura.model_validate(payload)
    reloaded = RoteiroEstrutura.model_validate(first.model_dump(mode="json"))
    persisted = reloaded.blocos[0].visual_queries[0]
    assert persisted.id == query.id
    assert persisted.visual_beat_id == query.visual_beat_id
    assert (persisted.coverage_start_char, persisted.coverage_end_char) == (0, len(content))


def test_staged_section_assembly_keeps_materialized_visual_queries() -> None:
    content = _content(4)
    query = _materialized(content, 20)[0]
    section = SimpleNamespace(
        section_order=0,
        section_key="section-001",
        section_plan={"title": "Abertura", "target_duration_seconds": 20, "beats": []},
        output={
            "content": content,
            "visual_queries": [query.to_dict()],
            "claims_used": [],
            "beats_covered": [],
        },
    )
    block = assemble_written_sections([section], claim_ledger=[])[0]
    assert block.visual_queries[0].visual_beat_id == query.visual_beat_id


def test_human_revision_must_preserve_complete_host_owned_bindings() -> None:
    content = _content(4)
    queries = _materialized(content, 60)
    validate_preserved_visual_queries(content=content, queries=queries)
    with pytest.raises(VisualRequirementsError, match="changed host-owned visual coverage"):
        validate_preserved_visual_queries(
            content=content.replace("sentença", "frase"), queries=queries
        )


def test_batch_response_rejects_unrequested_temporal_fields() -> None:
    with pytest.raises(Exception):
        VisualBeatEnrichmentOutput.model_validate(
            {
                "visual_queries": [
                    {
                        "beat_order": 0,
                        "intent": "illustration",
                        "query": "gameplay",
                        "importance": "preferred",
                        "narration_excerpt": "LLM tentou escolher span",
                    }
                ]
            }
        )
