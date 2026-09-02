from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from app.core.config import Settings
from app.production_profiles import get_profile
from app.schemas.generation import (
    EditorialCriticIssue,
    EditorialCriticOutput,
    EditorialPlanOutput,
    ExternalClaimExtractionOutput,
    GlobalEditorialPlanOutput,
    PlannedSectionBatchOutput,
    SectionEditorialAuditOutput,
    WrittenSectionOutput,
)
from app.schemas.media_indexer import (
    GameAnalysisMediaContext,
    MediaIndexerAlignment,
    MediaIndexerNote,
    MediaIndexerTimelineNote,
    MediaIndexerTimelineSession,
)
from app.services.external_research import ResearchSource
from app.services.llm_gateway import (
    LLMCallResult,
    LLMFailureCategory,
    LLMGatewayError,
    LLMTaskRole,
)
from app.services.script_generation_jobs import (
    GenerationFailureCategory,
    GenerationJobError,
    ScriptGenerationJobService,
    _audit_has_factual_blockers,
    _claim_extraction_max_tokens,
    _editorial_review_payload,
    _enforce_claim_language_assessments,
    _explicit_primary_source_required,
    _global_critic_output_contract,
    _global_plan_output_contract,
    _normalize_research_url,
    _planning_max_tokens,
    _primary_source_research_query,
    _reaudit_claim_refs,
    _reaudited_blocks,
    _repair_max_tokens,
    _research_budget,
    _role_model_snapshot,
    _section_audit_max_tokens,
    _section_audit_output_contract,
    _section_batch_output_contract,
    _section_batches,
    _select_research_sources,
    _temperature_for_role,
    _writing_max_tokens,
)


def _config() -> Settings:
    return Settings(
        llm_fast_model="fast-route",
        llm_standard_model="standard-route",
        llm_strong_model="strong-route",
    )


def _result(
    content: str,
    *,
    role: LLMTaskRole = LLMTaskRole.PLANNING,
    finish_reason: str = "stop",
    max_tokens: int = 3000,
    completion_tokens: int = 300,
) -> LLMCallResult:
    return LLMCallResult(
        content=content,
        task_role=role.value,
        model_alias="standard-route"
        if role is not LLMTaskRole.REPAIR
        else "fast-route",
        actual_model="provider/model",
        provider="test",
        prompt_identity="prompt",
        temperature=0.0 if role is LLMTaskRole.REPAIR else 0.5,
        max_tokens=max_tokens,
        prompt_tokens=100,
        completion_tokens=completion_tokens,
        total_tokens=100 + completion_tokens,
        latency_seconds=0.01,
        attempt_count=1,
        finish_reason=finish_reason,
    )


def _budgets(count: int, *, chapter_count: int = 1) -> list[dict[str, int | str]]:
    return [
        {
            "key": f"section-{index + 1:03d}",
            "order": index,
            "chapter_order": min(chapter_count - 1, index * chapter_count // count),
            "target_duration_seconds": 240,
            "target_words": 596,
            "min_words": 507,
            "max_words": 685,
        }
        for index in range(count)
    ]


def _global_json(*, chapter_count: int = 1) -> str:
    return json.dumps(
        {
            "thesis": "Uma tese editorial verificável.",
            "audience_promise": "Entender o argumento sem fatos inventados.",
            "chapters": [
                {
                    "key": f"chapter-{index + 1:03d}",
                    "title": f"Capítulo {index + 1}",
                    "purpose": "Organizar a progressão editorial.",
                }
                for index in range(chapter_count)
            ],
            "open_loops": [],
        }
    )


def _section_dict(key: str) -> dict[str, object]:
    return {
        "key": key,
        "title": f"Plano {key}",
        "purpose": "Desenvolver o argumento com clareza.",
        "narrative_role": "desenvolvimento",
        "beats": ["Apresentar o ponto central"],
        "evidence_refs": [],
        "claim_refs": [],
        "must_cover": ["A tese editorial"],
        "must_not_repeat": [],
        "transition_target": "Conectar com a próxima seção",
    }


def _batch_json(keys: list[str]) -> str:
    return json.dumps({"sections": [_section_dict(key) for key in keys]})


def _written_json(word_count: int, *, marker: str = "palavra") -> str:
    return json.dumps({"content": " ".join([marker] * word_count)})


def _section_audit(
    *,
    revision_required: bool = False,
    issues: list[EditorialCriticIssue] | None = None,
    claims: list[str] | None = None,
    beats: list[str] | None = None,
    claim_language_assessments: list[dict[str, object]] | None = None,
) -> SectionEditorialAuditOutput:
    return SectionEditorialAuditOutput(
        revision_required=revision_required,
        issues=issues or [],
        actual_claim_refs=claims or [],
        actual_beats_covered=["Apresentar o ponto central"] if beats is None else beats,
        actual_summary="A seção cobriu o ponto central.",
        opened_loops=[],
        closed_loops=[],
        claim_language_assessments=claim_language_assessments or [],
    )


def _writing_fixture() -> tuple[
    ScriptGenerationJobService, AsyncMock, SimpleNamespace, SimpleNamespace
]:
    session = AsyncMock()
    section = SimpleNamespace(
        section_key="section-001",
        section_order=0,
        status="pending",
        attempt_count=0,
        section_plan={
            "key": "section-001",
            "order": 0,
            "chapter_order": 0,
            "target_duration_seconds": 240,
            "target_words": 580,
            "min_words": 493,
            "max_words": 667,
            "title": "Seção controlada",
            "purpose": "Desenvolver o argumento.",
            "narrative_role": "desenvolvimento",
            "beats": ["Apresentar o ponto central"],
            "evidence_refs": [],
            "must_cover": ["O ponto central"],
            "must_not_repeat": [],
            "transition_target": None,
        },
        output=None,
        local_validation=None,
        prompt_provenance={"planning": {"persisted": True}},
        output_identity=None,
        error_category=None,
        error_message=None,
    )
    run = SimpleNamespace(
        id=uuid4(),
        ideia_id=uuid4(),
        production_profile="faceless_general",
        sections=[section],
        plan={
            "editorial": {
                "thesis": "Tese global.",
                "audience_promise": "Entender o ponto central.",
                "open_loops": [],
                "claim_ledger": [],
            }
        },
        evidence_dossier={"fragments": []},
        continuity_state={
            "introduced_claims": [],
            "completed_sections": [],
        },
        model_policy={"strategy": "standard"},
        call_usage={"calls": 0, "total_tokens": 0},
        strategy_identity="writing-test",
        heartbeat_at=None,
    )
    service = ScriptGenerationJobService(session, gateway=AsyncMock(), config=_config())
    service._editorial_context = AsyncMock(  # type: ignore[method-assign]
        return_value=(
            SimpleNamespace(author_briefing=None),
            None,
            get_profile("faceless_general"),
        )
    )
    service._audit_section = AsyncMock(  # type: ignore[method-assign]
        return_value=(
            _section_audit(),
            {"audit": "test"},
        )
    )
    return service, session, run, section


@pytest.mark.asyncio
async def test_reaudit_process_never_calls_writer() -> None:
    session = AsyncMock()
    run = SimpleNamespace(
        id=uuid4(),
        status="running",
        phase="validating",
        generation_intent="reaudit",
        sections=[],
        roteiro_id=None,
        completed_at=None,
    )
    service = ScriptGenerationJobService(session, gateway=AsyncMock())
    service.get = AsyncMock(return_value=run)  # type: ignore[method-assign]
    service._process_reaudit = AsyncMock()  # type: ignore[method-assign]
    service._write_section = AsyncMock()  # type: ignore[method-assign]

    result = await service.process(run.id)

    assert result.status == "completed"
    service._process_reaudit.assert_awaited_once_with(run)
    service._write_section.assert_not_awaited()


@pytest.mark.asyncio
async def test_enqueue_reaudit_refreshes_run_before_response_serialization() -> None:
    source = SimpleNamespace(
        id=uuid4(),
        ideia_id=uuid4(),
        ideia=SimpleNamespace(perfil_producao="faceless_general"),
        estrutura={
            "titulo": "Texto editado",
            "duracao_total_segundos": 60,
            "blocos": [
                {
                    "tipo": "desenvolvimento",
                    "duracao_segundos": 60,
                    "conteudo": "Texto humano que precisa de uma auditoria atual.",
                }
            ],
            "inherited_evidence_provenance": {
                "claim_ledger": [],
                "sources": [],
            },
        },
    )
    repository = AsyncMock()
    repository.get_by_id.return_value = source
    repository.get_latest_version_by_ideia.return_value = source
    run = SimpleNamespace(id=uuid4(), plan={}, total_sections=0)
    session = MagicMock()
    session.flush = AsyncMock()
    session.refresh = AsyncMock()
    service = ScriptGenerationJobService(session, gateway=AsyncMock(), config=_config())
    service.enqueue = AsyncMock(return_value=run)  # type: ignore[method-assign]

    with patch(
        "app.services.script_generation_jobs.RoteiroRepository",
        return_value=repository,
    ):
        result = await service.enqueue_reaudit(
            source.id,
            idempotency_key="reaudit-response-refresh",
        )

    assert result is run
    assert run.total_sections == 1
    session.flush.assert_awaited_once()
    session.refresh.assert_awaited_once_with(run)


@pytest.mark.asyncio
async def test_game_media_context_uses_real_ids_and_preserves_unmatched() -> None:
    project_id = uuid4()
    session_id = uuid4()
    matched_note_id = uuid4()
    unmatched_note_id = uuid4()
    context = GameAnalysisMediaContext(
        project_id=project_id,
        sessions=[
            MediaIndexerTimelineSession(
                session_id=session_id,
                session_label="Gameplay",
                notes=[
                    MediaIndexerTimelineNote(
                        note=MediaIndexerNote(
                            id=matched_note_id,
                            order=1,
                            raw="O carro aparece na chuva.",
                            alignment_status="matched",
                        ),
                        alignment=MediaIndexerAlignment(
                            candidate_alignment_id=uuid4(),
                            retrieval_rank=1,
                            start_seconds=12.5,
                            end_seconds=18.0,
                            confidence=0.9,
                        ),
                    ),
                    MediaIndexerTimelineNote(
                        note=MediaIndexerNote(
                            id=unmatched_note_id,
                            order=2,
                            raw="A nota humana não foi localizada.",
                            alignment_status="unmatched",
                        )
                    ),
                ],
            )
        ],
        total_notes=2,
        matched_notes=1,
        unmatched_notes=1,
        total_chars=100,
        available=True,
    )
    provider = AsyncMock()
    provider.get_context.return_value = context
    service = ScriptGenerationJobService(
        AsyncMock(), gateway=AsyncMock(), media_context_provider=provider
    )
    run = SimpleNamespace(id=uuid4(), heartbeat_at=None, evidence_dossier={})

    dossier = await service._retrieve_game_media_context(
        run,
        {
            "media_project_id": str(project_id),
            "media_session_ids": [str(session_id)],
            "sources": [],
            "fragments": [],
        },
    )

    by_id = {item["source_fragment_id"]: item for item in dossier["fragments"]}
    matched = by_id[f"media-timeline:{session_id}:{matched_note_id}"]
    unmatched = by_id[f"media-timeline:{session_id}:{unmatched_note_id}"]
    assert matched["alignment"]["start_seconds"] == 12.5
    assert matched["alignment"]["end_seconds"] == 18.0
    assert unmatched["alignment_status"] == "unmatched"
    assert "alignment" not in unmatched
    assert dossier["media_context"]["authority"] == "supplementary_audiovisual_evidence"


@pytest.mark.asyncio
async def test_optional_media_indexer_failure_is_persisted_as_warning() -> None:
    project_id = uuid4()
    provider = AsyncMock()
    provider.get_context.return_value = GameAnalysisMediaContext(
        project_id=project_id,
        warnings=["Media Indexer unavailable"],
        available=False,
        error="temporary outage",
    )
    service = ScriptGenerationJobService(
        AsyncMock(), gateway=AsyncMock(), media_context_provider=provider
    )
    run = SimpleNamespace(id=uuid4(), heartbeat_at=None, evidence_dossier={})

    dossier = await service._retrieve_game_media_context(
        run,
        {
            "media_project_id": str(project_id),
            "media_session_ids": [],
            "sources": [],
            "fragments": [],
        },
    )

    assert dossier["media_context_retrieved"] is True
    assert dossier["media_context"]["available"] is False
    assert dossier["media_context"]["warnings"] == ["Media Indexer unavailable"]


def _planning_fixture(
    monkeypatch: pytest.MonkeyPatch,
    *,
    section_count: int = 3,
    chapter_count: int = 1,
) -> tuple[
    ScriptGenerationJobService, AsyncMock, SimpleNamespace, list[SimpleNamespace]
]:
    rows: list[SimpleNamespace] = []
    session = AsyncMock()
    scalar_result = MagicMock()
    scalar_result.scalars.return_value.all.side_effect = lambda: rows
    session.execute = AsyncMock(return_value=scalar_result)
    session.add = MagicMock(side_effect=rows.append)
    service = ScriptGenerationJobService(session, gateway=AsyncMock(), config=_config())
    run = SimpleNamespace(
        id=uuid4(),
        ideia_id=uuid4(),
        phase="queued",
        status="running",
        plan={
            "sections": _budgets(section_count, chapter_count=chapter_count),
            "chapter_count": chapter_count,
        },
        sections=rows,
        evidence_dossier={
            "sources": [{"id": "idea-description"}],
            "fragments": [],
            "claims": [],
        },
        call_usage={
            "calls": 0,
            "total_tokens": 0,
            "fallbacks": [],
            "escalations": [],
        },
        model_policy={"strategy": "standard"},
        production_profile="faceless_general",
        continuity_state={"open_loops": [], "completed_sections": []},
        strategy_identity="fragmented-planning-test",
        heartbeat_at=None,
    )
    monkeypatch.setattr(
        "app.services.script_generation_jobs.IdeiaRepository.get_by_id",
        AsyncMock(
            return_value=SimpleNamespace(
                titulo="Fixture editorial",
                descricao_breve="Conteúdo sintético sem fatos externos.",
                author_briefing=None,
                nicho_id=None,
            )
        ),
    )
    return service, session, run, rows


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("strategy", "role", "escalation", "expected"),
    [
        ("standard", LLMTaskRole.WRITING, None, "standard-route"),
        ("flash_only", LLMTaskRole.CRITIC, None, "fast-route"),
        ("flash_only", LLMTaskRole.WRITING, "repeated_failure", "fast-route"),
        ("hybrid", LLMTaskRole.PLANNING, None, "strong-route"),
        ("hybrid", LLMTaskRole.WRITING, None, "standard-route"),
        ("strong", LLMTaskRole.WRITING, None, "strong-route"),
        ("standard", LLMTaskRole.WRITING, "repeated_failure", "strong-route"),
    ],
)
async def test_task_policy_routes_by_function_without_provider_names(
    strategy: str,
    role: LLMTaskRole,
    escalation: str | None,
    expected: str,
) -> None:
    session = AsyncMock()
    gateway = MagicMock()
    gateway.complete = AsyncMock()
    gateway.model_for.return_value = "standard-route"
    gateway.complete.side_effect = lambda **kwargs: _result(
        "{}", role=role, max_tokens=kwargs["max_tokens"]
    )
    run = SimpleNamespace(
        call_usage={"calls": 0, "total_tokens": 0, "escalations": []},
        model_policy={"strategy": strategy},
        strategy_identity="strategy-id",
    )
    service = ScriptGenerationJobService(session, gateway=gateway, config=_config())
    await service._complete(
        run,
        role=role,
        prompt="prompt",
        schema={"type": "object"},
        max_tokens=100,
        escalation_reason=escalation,
    )
    assert gateway.complete.await_args.kwargs["model_alias"] == expected
    assert gateway.complete.await_args.kwargs["temperature"] == _temperature_for_role(
        role
    )
    assert run.call_usage["calls"] == 1
    assert run.call_usage["by_role"] == {role.value: 1}
    assert run.call_usage["finish_reasons"][0]["role"] == role.value
    assert (len(run.call_usage["escalations"]) == 1) is bool(escalation)


def test_semantic_model_strategy_matrix_is_complete() -> None:
    expected = {
        "flash_only": {
            "fast": "fast-route",
            "planning": "fast-route",
            "writing": "fast-route",
            "critic": "fast-route",
            "repair": "fast-route",
        },
        "standard": {
            "fast": "fast-route",
            "planning": "standard-route",
            "writing": "standard-route",
            "critic": "standard-route",
            "repair": "fast-route",
        },
        "hybrid": {
            "fast": "fast-route",
            "planning": "strong-route",
            "writing": "standard-route",
            "critic": "strong-route",
            "repair": "fast-route",
        },
        "strong": {
            "fast": "strong-route",
            "planning": "strong-route",
            "writing": "strong-route",
            "critic": "strong-route",
            "repair": "strong-route",
        },
    }
    assert {
        strategy: _role_model_snapshot(_config(), strategy) for strategy in expected
    } == expected


def test_research_budget_is_proportional_and_bounded() -> None:
    config = _config()
    short = _research_budget(
        target_duration_seconds=60, target_words=145, config=config
    )
    medium = _research_budget(
        target_duration_seconds=360, target_words=870, config=config
    )
    long = _research_budget(
        target_duration_seconds=720, target_words=1740, config=config
    )
    assert (short.initial_queries, short.total_queries, short.results_per_query) == (
        1,
        2,
        3,
    )
    assert short.selected_sources == 2
    assert medium.selected_sources == 7
    assert long.selected_sources == 10
    assert short.selected_sources < medium.selected_sources < long.selected_sources
    assert long.total_queries <= config.generation_research_max_queries


@pytest.mark.parametrize(
    ("claim_count", "expected"),
    [(0, 8000), (12, 8000), (13, 8000), (42, 8000), (200, 8000)],
)
def test_section_audit_output_budget_is_bounded_and_proportional(
    claim_count: int, expected: int
) -> None:
    assert _section_audit_max_tokens(claim_count) == expected


def test_reaudit_claim_selection_uses_parent_section_provenance_without_reusing_audit() -> (
    None
):
    available = ["claim-parent", "claim-unused"]
    assert _reaudit_claim_refs(
        current_claims=[],
        inherited_claims=[{"id": "claim-parent"}, {"id": "claim-unknown"}],
        available_claim_ids=available,
    ) == ["claim-parent"]
    assert _reaudit_claim_refs(
        current_claims=[{"id": "claim-unused"}],
        inherited_claims=[{"id": "claim-parent"}],
        available_claim_ids=available,
    ) == ["claim-unused"]
    assert (
        _reaudit_claim_refs(
            current_claims=[], inherited_claims=[], available_claim_ids=available
        )
        == available
    )


def test_reaudited_blocks_preserve_prose_and_persist_only_actual_claims() -> None:
    block = SimpleNamespace(
        model_dump=lambda **_: {
            "tipo": "seção",
            "duracao_segundos": 60,
            "conteudo": "Texto humano preservado.",
            "claims": [],
            "beats": [],
        }
    )
    section = SimpleNamespace(
        section_order=0,
        section_plan={"evidence_refs": ["source-1"]},
        output={
            "claims_used": ["claim-used"],
            "beats_covered": ["Beat observado"],
        },
    )

    result = _reaudited_blocks(
        [block],
        [section],
        claim_ledger=[
            {"id": "claim-used", "summary": "Usado"},
            {"id": "claim-unused", "summary": "Não usado"},
        ],
    )

    assert result[0]["conteudo"] == "Texto humano preservado."
    assert [item["id"] for item in result[0]["claims"]] == ["claim-used"]
    assert result[0]["beats"] == [
        {
            "purpose": "actual",
            "key_point": "Beat observado",
            "evidence_refs": ["source-1"],
        }
    ]


def test_source_preselection_normalizes_tracking_and_preserves_relevant_diversity() -> (
    None
):
    assert (
        _normalize_research_url(
            "https://www.rockstargames.com/news/?utm_source=test&lang=pt#fragment"
        )
        == "https://rockstargames.com/news?lang=pt"
    )
    sources = [
        {
            "title": "Rockstar Games anuncia GTA VI",
            "snippet": "Página oficial com o anúncio de GTA VI.",
            "url": "https://rockstargames.com/VI",
            "domain": "rockstargames.com",
            "source_trust": "primary_official",
        },
        {
            "title": "GTA VI report",
            "snippet": "A secondary report about GTA VI development.",
            "url": "https://news.example/gta-vi",
            "domain": "news.example",
            "source_trust": "unverified",
        },
        {
            "title": "Frases para começar bem o dia",
            "snippet": "Mensagens motivacionais e cartões de bom dia.",
            "url": "https://irrelevant.example/bom-dia",
            "domain": "irrelevant.example",
            "source_trust": "unverified",
        },
    ]
    selected = _select_research_sources(sources, topic="GTA VI anúncio", limit=3)
    assert [item["domain"] for item in selected] == [
        "rockstargames.com",
        "news.example",
    ]


def test_short_source_preselection_uses_trusted_sources_before_unverified() -> None:
    sources = [
        {
            "title": "Rockstar Games GTA VI",
            "snippet": "Página oficial sobre GTA VI.",
            "url": "https://rockstargames.com/VI",
            "domain": "rockstargames.com",
            "source_trust": "primary_official",
        },
        {
            "title": "GTA VI report",
            "snippet": "Unverified report about GTA VI.",
            "url": "https://unknown.example/gta-vi",
            "domain": "unknown.example",
            "source_trust": "unverified",
        },
    ]

    selected = _select_research_sources(
        sources,
        topic="GTA VI",
        limit=2,
        trusted_only_when_available=True,
    )

    assert [item["source_trust"] for item in selected] == ["primary_official"]


def test_short_source_preselection_keeps_unverified_without_trusted_source() -> None:
    sources = [
        {
            "title": "GTA VI report",
            "snippet": "Unverified report about GTA VI.",
            "url": "https://unknown.example/gta-vi",
            "domain": "unknown.example",
            "source_trust": "unverified",
        }
    ]

    selected = _select_research_sources(
        sources,
        topic="GTA VI",
        limit=2,
        trusted_only_when_available=True,
    )

    assert [item["source_trust"] for item in selected] == ["unverified"]


def test_primary_source_query_uses_topic_scoped_policy_rule() -> None:
    policy = get_profile(None).source_policy

    assert _primary_source_research_query("Análise de GTA VI", policy).endswith(
        "site:rockstargames.com"
    )
    assert _primary_source_research_query("História de Marte", policy).endswith(
        "fonte primária oficial anúncio"
    )


def test_explicit_primary_source_requirement_is_narrow_and_accent_insensitive() -> None:
    assert _explicit_primary_source_required(
        "Priorize exclusivamente evidência oficial e perfis oficiais."
    )
    assert _explicit_primary_source_required("Use official sources only.")
    assert _explicit_primary_source_required(
        "Use apenas informações oficialmente confirmadas pela Rockstar."
    )
    assert not _explicit_primary_source_required(
        "Faça uma análise de GTA VI e prefira fontes oficiais quando disponíveis."
    )
    assert not _explicit_primary_source_required(
        "O que sabemos sobre GTA VI, incluindo reportagens e rumores qualificados."
    )


@pytest.mark.parametrize(
    ("status", "attributed", "qualified", "scope_preserved"),
    [
        ("reported", False, False, True),
        ("rumor", True, False, True),
        ("leak", True, False, True),
        ("speculation", True, False, True),
        ("inference", True, False, True),
        ("official_observation", True, True, False),
    ],
)
def test_non_direct_claim_language_loss_becomes_revision_required(
    status: str,
    attributed: bool,
    qualified: bool,
    scope_preserved: bool,
) -> None:
    claim_ref = f"claim-{status}"
    audit = SectionEditorialAuditOutput.model_validate(
        {
            "revision_required": False,
            "issues": [],
            "actual_claim_refs": [claim_ref],
            "actual_beats_covered": [],
            "actual_summary": "A seção usou o claim.",
            "opened_loops": [],
            "closed_loops": [],
            "claim_language_assessments": [
                {
                    "claim_ref": claim_ref,
                    "language_proportional": True,
                    "attribution_present": attributed,
                    "qualification_present": qualified,
                    "scope_preserved": scope_preserved,
                }
            ],
        }
    )
    checked = _enforce_claim_language_assessments(
        audit,
        [{"id": claim_ref, "claim_status": status}],
    )
    assert checked.revision_required is True
    assert checked.issues[0].category == "uncertainty_lost"
    assert checked.issues[0].claim_ref == claim_ref


def test_reported_attribution_is_accepted_and_confirmed_needs_no_assessment() -> None:
    reported = SectionEditorialAuditOutput.model_validate(
        {
            "revision_required": False,
            "issues": [],
            "actual_claim_refs": ["claim-reported"],
            "actual_beats_covered": [],
            "actual_summary": "Segundo a fonte, a empresa estaria desenvolvendo X.",
            "opened_loops": [],
            "closed_loops": [],
            "claim_language_assessments": [
                {
                    "claim_ref": "claim-reported",
                    "language_proportional": True,
                    "attribution_present": True,
                    "qualification_present": True,
                    "scope_preserved": True,
                }
            ],
        }
    )
    assert not _enforce_claim_language_assessments(
        reported,
        [{"id": "claim-reported", "claim_status": "reported"}],
    ).revision_required
    confirmed = reported.model_copy(
        update={
            "actual_claim_refs": ["claim-confirmed"],
            "claim_language_assessments": [],
        }
    )
    assert not _enforce_claim_language_assessments(
        confirmed,
        [{"id": "claim-confirmed", "claim_status": "confirmed"}],
    ).revision_required


def test_attributed_official_observation_is_accepted_without_false_qualification() -> (
    None
):
    audit = SectionEditorialAuditOutput.model_validate(
        {
            "revision_required": False,
            "issues": [],
            "actual_claim_refs": ["claim-official"],
            "actual_beats_covered": [],
            "actual_summary": "O material oficial mostra X.",
            "opened_loops": [],
            "closed_loops": [],
            "claim_language_assessments": [
                {
                    "claim_ref": "claim-official",
                    "language_proportional": True,
                    "attribution_present": True,
                    "qualification_present": False,
                    "scope_preserved": True,
                }
            ],
        }
    )

    checked = _enforce_claim_language_assessments(
        audit,
        [{"id": "claim-official", "claim_status": "official_observation"}],
    )

    assert checked.revision_required is False
    assert checked.issues == []


def test_negative_factual_assertion_without_claim_is_a_blocking_audit_issue() -> None:
    unsupported = SectionEditorialAuditOutput.model_validate(
        {
            "revision_required": True,
            "issues": [
                {
                    "section_key": "section-001",
                    "category": "unsupported_claim",
                    "severity": "blocking",
                    "actionable_feedback": (
                        "Remova a afirmação de que a Rockstar ainda não mostrou "
                        "Vice City ou forneça um claim aprovado que sustente essa ausência."
                    ),
                    "claim_ref": None,
                    "excerpt": "A Rockstar ainda não mostrou Vice City.",
                }
            ],
            "actual_claim_refs": [],
            "actual_beats_covered": [],
            "actual_summary": "A seção fez uma afirmação negativa sem suporte.",
            "opened_loops": [],
            "closed_loops": [],
            "claim_language_assessments": [],
        }
    )

    assert _audit_has_factual_blockers(unsupported) is True

    supported = unsupported.model_copy(
        update={
            "revision_required": False,
            "issues": [],
            "actual_claim_refs": ["claim-negative-dated"],
            "actual_summary": (
                "Até a data coberta pela fonte, a Rockstar não havia anunciado Y."
            ),
        }
    )
    checked = _enforce_claim_language_assessments(
        supported,
        [
            {
                "id": "claim-negative-dated",
                "claim_status": "confirmed",
                "support_scope": "Ausência de anúncio somente até a data X.",
            }
        ],
    )

    assert _audit_has_factual_blockers(checked) is False
    assert checked.revision_required is False


@pytest.mark.asyncio
async def test_valid_global_fragment_does_not_call_repair() -> None:
    service = ScriptGenerationJobService(
        AsyncMock(), gateway=AsyncMock(), config=_config()
    )
    service._complete = AsyncMock()  # type: ignore[method-assign]
    result = _result(_global_json())
    parsed, provenance = await service._parse_or_repair(
        SimpleNamespace(), result, GlobalEditorialPlanOutput
    )
    assert parsed.thesis.startswith("Uma tese")
    assert provenance == result.provenance()
    service._complete.assert_not_awaited()


@pytest.mark.asyncio
async def test_json_only_markdown_fence_is_locally_unwrapped_without_repair() -> None:
    service = ScriptGenerationJobService(
        AsyncMock(), gateway=AsyncMock(), config=_config()
    )
    service._complete = AsyncMock()  # type: ignore[method-assign]
    result = _result(f"```json\n{_global_json()}\n```")

    parsed, provenance = await service._parse_or_repair(
        SimpleNamespace(), result, GlobalEditorialPlanOutput
    )

    assert parsed.thesis.startswith("Uma tese")
    assert provenance == result.provenance()
    service._complete.assert_not_awaited()


@pytest.mark.asyncio
async def test_external_claim_confidence_labels_are_normalized_without_llm_repair() -> (
    None
):
    service = ScriptGenerationJobService(
        AsyncMock(), gateway=AsyncMock(), config=_config()
    )
    service._complete = AsyncMock()  # type: ignore[method-assign]
    result = _result(
        json.dumps(
            {
                "claims": [
                    {
                        "summary": "A fonte descreve o personagem.",
                        "source_fragment_id": "source-1",
                        "claim_status": "reported",
                        "confidence": "alta",
                        "support_scope": "texto",
                    }
                ]
            }
        )
    )

    parsed, provenance = await service._parse_or_repair(
        SimpleNamespace(), result, ExternalClaimExtractionOutput
    )

    assert parsed.claims[0].confidence == 0.9
    assert provenance["local_shape_normalizations"] == [
        "external_claim_confidence_label"
    ]
    service._complete.assert_not_awaited()


@pytest.mark.asyncio
async def test_global_wrong_root_uses_global_only_repair() -> None:
    service = ScriptGenerationJobService(
        AsyncMock(), gateway=AsyncMock(), config=_config()
    )
    invalid = _result(json.dumps({"chapter-001": {"title": "Capítulo"}}))
    service._complete = AsyncMock(  # type: ignore[method-assign]
        return_value=_result(_global_json(), role=LLMTaskRole.REPAIR)
    )
    parsed, provenance = await service._parse_or_repair(
        SimpleNamespace(),
        invalid,
        GlobalEditorialPlanOutput,
        repair_contract=_global_plan_output_contract(["chapter-001"]),
    )
    assert parsed.chapters[0].key == "chapter-001"
    assert provenance["repair_reason"] == "ValidationError"
    assert "chapters" in provenance["repair_validation_errors"]
    prompt = service._complete.await_args.kwargs["prompt"]
    assert "VALIDATION ERRORS" in prompt
    assert "Do not return sections" in prompt
    assert "IMMUTABLE BATCH SKELETON" not in prompt


@pytest.mark.asyncio
async def test_section_wrong_root_repairs_only_that_batch() -> None:
    service = ScriptGenerationJobService(
        AsyncMock(), gateway=AsyncMock(), config=_config()
    )
    keys = ["section-001", "section-002"]
    invalid = _result(json.dumps({key: _section_dict(key) for key in keys}))
    service._complete = AsyncMock(  # type: ignore[method-assign]
        return_value=_result(_batch_json(keys), role=LLMTaskRole.REPAIR)
    )
    parsed, _ = await service._parse_or_repair(
        SimpleNamespace(),
        invalid,
        PlannedSectionBatchOutput,
        repair_contract=_section_batch_output_contract(keys),
    )
    assert [section.key for section in parsed.sections] == keys
    prompt = service._complete.await_args.kwargs["prompt"]
    assert "section-001" in prompt and "section-002" in prompt
    assert "GLOBAL THESIS" not in prompt
    assert "audience_promise" not in prompt
    assert "EditorialPlanOutput" not in prompt


@pytest.mark.asyncio
async def test_fragment_repair_is_bounded_and_truncation_is_terminal() -> None:
    service = ScriptGenerationJobService(
        AsyncMock(), gateway=AsyncMock(), config=_config()
    )
    service._complete = AsyncMock(  # type: ignore[method-assign]
        return_value=_result(
            "{",
            role=LLMTaskRole.REPAIR,
            finish_reason="length",
            max_tokens=2500,
            completion_tokens=2490,
        )
    )
    with pytest.raises(LLMGatewayError) as captured:
        await service._parse_or_repair(
            SimpleNamespace(), _result("{"), PlannedSectionBatchOutput
        )
    assert captured.value.category is LLMFailureCategory.FORMAT
    service._complete.assert_awaited_once()


@pytest.mark.asyncio
async def test_three_sections_assemble_exact_host_owned_plan(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service, _, run, rows = _planning_fixture(monkeypatch)
    service._complete = AsyncMock(  # type: ignore[method-assign]
        side_effect=[
            _result(_global_json(), max_tokens=2500),
            _result(
                _batch_json(["section-001", "section-002", "section-003"]),
                max_tokens=4000,
            ),
        ]
    )
    await service._plan(run)
    canonical = EditorialPlanOutput.model_validate(run.plan["editorial"])
    assert [section.key for section in canonical.sections] == [
        "section-001",
        "section-002",
        "section-003",
    ]
    assert run.phase == "writing"
    assert run.plan["planning_state"]["status"] == "completed"
    assert len(run.plan["planning_state"]["accepted_batches"]) == 1
    assert [row.status for row in rows] == ["pending", "pending", "pending"]
    assert [row.section_plan["target_words"] for row in rows] == [596, 596, 596]
    schemas = [call.kwargs["schema"] for call in service._complete.await_args_list]
    assert schemas == [
        GlobalEditorialPlanOutput.model_json_schema(),
        PlannedSectionBatchOutput.model_json_schema(),
    ]
    assert EditorialPlanOutput.model_json_schema() not in schemas
    assert all(
        call.kwargs["structured_mode"] == "json_schema"
        for call in service._complete.await_args_list
    )


@pytest.mark.asyncio
async def test_wrong_section_batch_root_repairs_only_batch_in_real_plan(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service, _, run, _ = _planning_fixture(monkeypatch)
    keyed_root = json.dumps(
        {
            key: _section_dict(key)
            for key in ["section-001", "section-002", "section-003"]
        }
    )
    service._complete = AsyncMock(  # type: ignore[method-assign]
        side_effect=[
            _result(_global_json()),
            _result(keyed_root, completion_tokens=900),
            _result(
                _batch_json(["section-001", "section-002", "section-003"]),
                role=LLMTaskRole.REPAIR,
            ),
        ]
    )
    await service._plan(run)
    assert run.phase == "writing"
    roles = [call.kwargs["role"] for call in service._complete.await_args_list]
    assert roles == [LLMTaskRole.PLANNING, LLMTaskRole.PLANNING, LLMTaskRole.REPAIR]
    repair_prompt = service._complete.await_args_list[2].kwargs["prompt"]
    assert "section-001" in repair_prompt
    assert "Uma tese editorial verificável" not in repair_prompt
    assert "claim_ledger" not in repair_prompt


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "actual_keys",
    [
        ["section-001", "section-002", "section-003", "section-004"],
        ["section-001", "section-002"],
        ["section-001", "wrong-key", "section-003"],
        ["section-002", "section-001", "section-003"],
    ],
    ids=["extra", "missing", "wrong", "reordered"],
)
async def test_section_batch_contract_mismatch_is_rejected_locally(
    monkeypatch: pytest.MonkeyPatch, actual_keys: list[str]
) -> None:
    service, _, run, rows = _planning_fixture(monkeypatch)
    service._complete = AsyncMock(  # type: ignore[method-assign]
        side_effect=[_result(_global_json()), _result(_batch_json(actual_keys))]
    )
    with pytest.raises(GenerationJobError) as captured:
        await service._plan(run)
    assert captured.value.category is GenerationFailureCategory.SCHEMA
    assert "section planning batch contract mismatch" in str(captured.value)
    assert all(row.status == "planning" for row in rows)


@pytest.mark.asyncio
async def test_truncated_multi_section_batch_splits_deterministically(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service, _, run, _ = _planning_fixture(monkeypatch)
    service._complete = AsyncMock(  # type: ignore[method-assign]
        side_effect=[
            _result(_global_json()),
            _result(
                "{", finish_reason="length", max_tokens=4000, completion_tokens=3990
            ),
            _result(_batch_json(["section-001"])),
            _result(_batch_json(["section-002", "section-003"])),
        ]
    )
    await service._plan(run)
    state = run.plan["planning_state"]
    assert len(state["truncated_batches"]) == 1
    assert len(state["accepted_batches"]) == 2
    assert [section["key"] for section in run.plan["editorial"]["sections"]] == [
        "section-001",
        "section-002",
        "section-003",
    ]


@pytest.mark.asyncio
async def test_singleton_batch_truncation_is_terminal_format(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service, _, run, rows = _planning_fixture(monkeypatch, section_count=1)
    service._complete = AsyncMock(  # type: ignore[method-assign]
        side_effect=[
            _result(_global_json()),
            _result(
                "{", finish_reason="length", max_tokens=3000, completion_tokens=2990
            ),
        ]
    )
    with pytest.raises(LLMGatewayError) as captured:
        await service._plan(run)
    assert captured.value.category is LLMFailureCategory.FORMAT
    assert "finish_reason=length" in str(captured.value)
    assert rows[0].status == "planning"


@pytest.mark.asyncio
async def test_resume_reuses_global_and_completed_sections(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service, _, run, rows = _planning_fixture(monkeypatch)
    for budget in run.plan["sections"]:
        key = str(budget["key"])
        completed = key != "section-003"
        rows.append(
            SimpleNamespace(
                run_id=run.id,
                section_key=key,
                section_order=budget["order"],
                chapter_order=budget["chapter_order"],
                status="pending" if completed else "planning",
                section_plan={
                    **budget,
                    **(_section_dict(key) if completed else {}),
                    "planning_status": "completed" if completed else "pending",
                },
                prompt_provenance={"already_completed": True} if completed else None,
            )
        )
    run.plan["planning_state"] = {
        "version": "fragmented_editorial_planning_v1",
        "status": "planning",
        "global_output": json.loads(_global_json()),
        "global_provenance": {"persisted": True},
        "accepted_batches": [{"expected_section_keys": ["section-001", "section-002"]}],
        "truncated_batches": [],
    }
    service._complete = AsyncMock(  # type: ignore[method-assign]
        return_value=_result(_batch_json(["section-003"]))
    )
    await service._plan(run)
    service._complete.assert_awaited_once()
    assert service._complete.await_args.kwargs["role"] is LLMTaskRole.PLANNING
    assert [row.section_plan["title"] for row in rows[:2]] == [
        "Plano section-001",
        "Plano section-002",
    ]
    assert len(run.plan["planning_state"]["accepted_batches"]) == 2


def test_long_form_batches_are_bounded_for_13_and_28_sections() -> None:
    batches_13 = _section_batches(_budgets(13, chapter_count=3))
    batches_28 = _section_batches(_budgets(28, chapter_count=5))
    assert [len(batch) for batch in batches_13] == [4, 4, 4, 1]
    assert [len(batch) for batch in batches_28] == [4, 4, 4, 4, 4, 4, 4]
    assert max(map(len, [*batches_13, *batches_28])) == 4


@pytest.mark.asyncio
async def test_28_sections_never_request_monolithic_editorial_schema(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service, _, run, _ = _planning_fixture(
        monkeypatch, section_count=28, chapter_count=5
    )
    results = [_result(_global_json(chapter_count=5))]
    results.extend(
        _result(_batch_json([str(item["key"]) for item in batch]))
        for batch in _section_batches(run.plan["sections"])
    )
    service._complete = AsyncMock(side_effect=results)  # type: ignore[method-assign]
    await service._plan(run)
    assert service._complete.await_count == 8
    schemas = [call.kwargs["schema"] for call in service._complete.await_args_list]
    assert schemas[0] == GlobalEditorialPlanOutput.model_json_schema()
    assert all(
        schema == PlannedSectionBatchOutput.model_json_schema()
        for schema in schemas[1:]
    )
    assert EditorialPlanOutput.model_json_schema() not in schemas
    assert len(run.plan["editorial"]["sections"]) == 28


def test_planning_and_repair_token_budgets_remain_bounded() -> None:
    assert _planning_max_tokens(1) == 6000
    assert _planning_max_tokens(4) == 6000
    with pytest.raises(ValueError, match="at least one"):
        _planning_max_tokens(0)
    assert (
        _repair_max_tokens(_result("{}", completion_tokens=1519, max_tokens=4000))
        == 3519
    )
    assert (
        _repair_max_tokens(_result("{}", completion_tokens=5000, max_tokens=6000))
        == 6000
    )


def test_writing_capacity_uses_headroom_and_remains_bounded() -> None:
    assert _writing_max_tokens(580) == 7480
    assert _writing_max_tokens(580) > 1467
    assert _writing_max_tokens(700) > _writing_max_tokens(580)
    assert _writing_max_tokens(10_000) == 10_000
    with pytest.raises(ValueError, match="positive"):
        _writing_max_tokens(0)


def test_writer_schema_does_not_echo_host_owned_section_metadata() -> None:
    properties = WrittenSectionOutput.model_json_schema()["properties"]
    assert set(properties) == {"content"}


def test_section_claims_are_selected_only_by_explicit_approved_claim_refs() -> None:
    run = SimpleNamespace(
        plan={
            "editorial": {
                "claim_ledger": [
                    {"id": "claim-1", "source_refs": ["source-a"]},
                    {"id": "claim-2", "source_refs": ["source-b"]},
                ]
            }
        }
    )
    claims = ScriptGenerationJobService._claims_for_section(
        run, {"evidence_refs": ["source-a"], "claim_refs": ["claim-2"]}
    )
    assert [item["id"] for item in claims] == ["claim-2"]
    assert (
        ScriptGenerationJobService._claims_for_section(
            run, {"evidence_refs": ["source-b"], "claim_refs": []}
        )
        == []
    )


@pytest.mark.asyncio
async def test_writing_stop_does_not_use_capacity_retry() -> None:
    service, _, run, section = _writing_fixture()
    service._complete = AsyncMock(  # type: ignore[method-assign]
        return_value=_result(
            _written_json(580),
            role=LLMTaskRole.WRITING,
            max_tokens=7480,
            completion_tokens=1700,
        )
    )

    await service._write_section(run, section)

    service._complete.assert_awaited_once()
    assert service._complete.await_args.kwargs["max_tokens"] == 7480
    assert section.status == "completed"
    assert section.attempt_count == 1
    assert section.local_validation["actual_words"] == 580
    assert section.prompt_provenance["capacity_retry_count"] == 0
    assert section.prompt_provenance["editorial_revision_count"] == 0


@pytest.mark.asyncio
async def test_writing_resume_preserves_bounded_editorial_attempt_count() -> None:
    service, _, run, section = _writing_fixture()
    section.attempt_count = 1
    service._complete = AsyncMock(  # type: ignore[method-assign]
        return_value=_result(
            _written_json(580),
            role=LLMTaskRole.WRITING,
            max_tokens=7480,
            completion_tokens=1700,
        )
    )

    await service._write_section(run, section)

    assert service._complete.await_count == 1
    assert section.status == "completed"
    assert section.attempt_count == 2
    assert section.prompt_provenance["editorial_revision_count"] == 1


@pytest.mark.asyncio
async def test_writing_truncation_regenerates_once_at_hard_ceiling() -> None:
    service, _, run, section = _writing_fixture()
    service._complete = AsyncMock(  # type: ignore[method-assign]
        side_effect=[
            _result(
                '{"content":"partial',
                role=LLMTaskRole.WRITING,
                finish_reason="length",
                max_tokens=7480,
                completion_tokens=7470,
            ),
            _result(
                _written_json(580, marker="accepted"),
                role=LLMTaskRole.WRITING,
                max_tokens=10_000,
                completion_tokens=1800,
            ),
        ]
    )

    await service._write_section(run, section)

    assert service._complete.await_count == 2
    assert [
        call.kwargs["max_tokens"] for call in service._complete.await_args_list
    ] == [7480, 10_000]
    assert section.status == "completed"
    assert section.attempt_count == 1
    assert section.output["content"].startswith("accepted")
    assert "partial" not in section.output["content"]
    assert section.prompt_provenance["capacity_retry_count"] == 1
    assert section.prompt_provenance["editorial_revision_count"] == 0
    calls = section.prompt_provenance["writing_calls"]
    assert [item["outcome"] for item in calls] == ["truncated", "completed"]
    assert calls[1]["reason"] == "output_capacity_retry"


@pytest.mark.asyncio
async def test_second_writing_truncation_is_terminal_and_diagnostic() -> None:
    service, session, run, section = _writing_fixture()
    service._complete = AsyncMock(  # type: ignore[method-assign]
        side_effect=[
            _result(
                "{",
                role=LLMTaskRole.WRITING,
                finish_reason="length",
                max_tokens=7480,
                completion_tokens=7470,
            ),
            _result(
                "{",
                role=LLMTaskRole.WRITING,
                finish_reason="max_output_tokens",
                max_tokens=10_000,
                completion_tokens=9990,
            ),
        ]
    )

    with pytest.raises(LLMGatewayError) as captured:
        await service._write_section(run, section)

    assert captured.value.category is LLMFailureCategory.FORMAT
    assert service._complete.await_count == 2
    assert section.status == "writing"
    assert section.attempt_count == 1
    assert section.output is None
    assert section.prompt_provenance["capacity_retry_count"] == 1
    assert [
        item["result"]["finish_reason"]
        for item in section.prompt_provenance["writing_calls"]
    ] == ["length", "max_output_tokens"]
    assert session.commit.await_count == 4


@pytest.mark.asyncio
@pytest.mark.parametrize("first_word_count", [200, 800], ids=["under", "over"])
async def test_stopped_output_outside_word_budget_uses_editorial_revision(
    first_word_count: int,
) -> None:
    service, _, run, section = _writing_fixture()
    service._complete = AsyncMock(  # type: ignore[method-assign]
        side_effect=[
            _result(
                _written_json(first_word_count),
                role=LLMTaskRole.WRITING,
                max_tokens=7480,
                completion_tokens=1000,
            ),
            _result(
                _written_json(580),
                role=LLMTaskRole.WRITING,
                max_tokens=7480,
                completion_tokens=1700,
            ),
        ]
    )

    await service._write_section(run, section)

    assert service._complete.await_count == 2
    assert [
        call.kwargs["max_tokens"] for call in service._complete.await_args_list
    ] == [7480, 7480]
    assert section.status == "completed"
    assert section.attempt_count == 2
    assert section.local_validation["actual_words"] == 580
    assert section.prompt_provenance["capacity_retry_count"] == 0
    assert section.prompt_provenance["editorial_revision_count"] == 1
    assert [
        item["editorial_attempt"]
        for item in section.prompt_provenance["validation_attempts"]
    ] == [1, 2]


def test_task_temperature_policy_keeps_repair_deterministic() -> None:
    assert _temperature_for_role(LLMTaskRole.REPAIR) == 0.0
    assert _temperature_for_role(LLMTaskRole.PLANNING) == 0.5
    assert _temperature_for_role(LLMTaskRole.CRITIC) == 0.0
    assert _temperature_for_role(LLMTaskRole.WRITING) == 0.7


def test_claim_extraction_capacity_has_reasoning_headroom_and_hard_ceiling() -> None:
    assert _claim_extraction_max_tokens(1) >= 3000
    assert _claim_extraction_max_tokens(4) == 4360
    assert _claim_extraction_max_tokens(20) == 6000


@pytest.mark.asyncio
async def test_process_refreshes_new_planning_rows_before_writing() -> None:
    section = SimpleNamespace(status="pending")
    run = SimpleNamespace(
        id=uuid4(),
        status="running",
        phase="planning",
        sections=[],
        plan={"sections": [], "chapter_count": 1},
        evidence_dossier={"research_complete": True},
        completed_sections=0,
        heartbeat_at=None,
        completed_at=None,
        roteiro_id=None,
    )
    session = AsyncMock()

    async def refresh(target, *, attribute_names):
        if attribute_names == ["sections"]:
            target.sections = [section]

    session.refresh.side_effect = refresh
    service = ScriptGenerationJobService(session, gateway=AsyncMock(), config=_config())
    service.get = AsyncMock(return_value=run)  # type: ignore[method-assign]

    async def complete_plan(target):
        target.plan = {
            **target.plan,
            "editorial": {},
            "planning_state": {
                "version": "fragmented_editorial_planning_v1",
                "status": "completed",
            },
        }

    async def write_section(_run, target):
        target.status = "completed"

    service._plan = AsyncMock(side_effect=complete_plan)  # type: ignore[method-assign]
    service._write_section = AsyncMock(side_effect=write_section)  # type: ignore[method-assign]
    service._assemble = AsyncMock()  # type: ignore[method-assign]

    result = await service.process(run.id)

    assert result.status == "completed"
    service._write_section.assert_awaited_once_with(run, section)
    assert any(
        call.kwargs.get("attribute_names") == ["sections"]
        for call in session.refresh.await_args_list
    )


@pytest.mark.asyncio
async def test_process_with_persisted_plan_resumes_at_pending_section() -> None:
    section = SimpleNamespace(status="pending")
    run = SimpleNamespace(
        id=uuid4(),
        status="running",
        phase="writing",
        sections=[section],
        plan={
            "editorial": {},
            "planning_state": {
                "version": "fragmented_editorial_planning_v1",
                "status": "completed",
            },
        },
        evidence_dossier={"research_complete": True},
        completed_sections=0,
        heartbeat_at=None,
        completed_at=None,
        roteiro_id=None,
    )
    session = AsyncMock()
    service = ScriptGenerationJobService(session, gateway=AsyncMock(), config=_config())
    service.get = AsyncMock(return_value=run)  # type: ignore[method-assign]

    async def write_section(_run, target):
        target.status = "completed"

    service._plan = AsyncMock()  # type: ignore[method-assign]
    service._write_section = AsyncMock(side_effect=write_section)  # type: ignore[method-assign]
    service._assemble = AsyncMock()  # type: ignore[method-assign]

    result = await service.process(run.id)

    assert result.status == "completed"
    service._plan.assert_not_awaited()
    service._write_section.assert_awaited_once_with(run, section)


@pytest.mark.asyncio
async def test_resume_preserves_completed_sections_and_requeues_only_failure() -> None:
    completed = SimpleNamespace(
        status="completed", error_category=None, error_message=None
    )
    failed = SimpleNamespace(
        status="failed", error_category="provider", error_message="down"
    )
    run = SimpleNamespace(
        id=uuid4(),
        status="failed",
        phase="failed",
        sections=[completed, failed],
        plan={
            "editorial": {},
            "planning_state": {
                "version": "fragmented_editorial_planning_v1",
                "status": "completed",
            },
        },
        error_category="provider",
        error_message="down",
        completed_at=object(),
    )
    session = AsyncMock()
    service = ScriptGenerationJobService(session, gateway=AsyncMock(), config=_config())
    service.get = AsyncMock(return_value=run)  # type: ignore[method-assign]
    resumed = await service.resume(run.id)
    assert resumed.status == "queued"
    assert completed.status == "completed"
    assert failed.status == "pending"
    assert resumed.phase == "writing"
    session.flush.assert_awaited_once()
    session.refresh.assert_awaited_once_with(run)


@pytest.mark.asyncio
async def test_resume_incomplete_fragmented_plan_returns_to_planning() -> None:
    planning = SimpleNamespace(
        status="planning", error_category=None, error_message=None
    )
    run = SimpleNamespace(
        id=uuid4(),
        status="failed",
        phase="failed",
        sections=[planning],
        plan={
            "planning_state": {
                "version": "fragmented_editorial_planning_v1",
                "status": "planning",
            }
        },
        error_category="provider",
        error_message="down",
        completed_at=object(),
    )
    service = ScriptGenerationJobService(
        AsyncMock(), gateway=AsyncMock(), config=_config()
    )
    service.get = AsyncMock(return_value=run)  # type: ignore[method-assign]
    resumed = await service.resume(run.id)
    assert resumed.phase == "planning"


@pytest.mark.asyncio
async def test_cancel_is_idempotent_for_terminal_run() -> None:
    run = SimpleNamespace(id=uuid4(), status="completed", phase="completed")
    session = AsyncMock()
    service = ScriptGenerationJobService(session, gateway=AsyncMock(), config=_config())
    service.get = AsyncMock(return_value=run)  # type: ignore[method-assign]
    result = await service.cancel(run.id)
    assert result.status == "completed"
    session.flush.assert_not_awaited()


def test_section_cannot_escape_the_approved_claim_ledger() -> None:
    run = SimpleNamespace(plan={"editorial": {"claim_ledger": [{"id": "claim-1"}]}})
    ScriptGenerationJobService._validate_claim_refs(run, ["claim-1"])
    with pytest.raises(GenerationJobError) as captured:
        ScriptGenerationJobService._validate_claim_refs(run, ["invented-claim"])
    assert captured.value.category is GenerationFailureCategory.GROUNDING


@pytest.mark.asyncio
async def test_claim_next_sets_timezone_aware_timestamps() -> None:
    now = datetime.now(UTC)
    run = SimpleNamespace(
        id=uuid4(),
        status="queued",
        started_at=None,
        heartbeat_at=None,
        criado_em=now - timedelta(seconds=60),
    )
    session = AsyncMock()
    session.execute = AsyncMock(
        return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=run))
    )
    service = ScriptGenerationJobService(
        session,
        gateway=AsyncMock(),
        config=Settings(generation_stale_after_seconds=300),
    )
    claimed = await service.claim_next()
    assert claimed is run
    assert run.status == "running"
    assert run.started_at is not None
    assert run.heartbeat_at is not None
    assert run.started_at.tzinfo is not None
    assert run.heartbeat_at.tzinfo is not None
    session.flush.assert_awaited_once()


@pytest.mark.asyncio
async def test_claim_next_reclaims_stale_running_job() -> None:
    now = datetime.now(UTC)
    run = SimpleNamespace(
        id=uuid4(),
        status="running",
        started_at=now - timedelta(seconds=500),
        heartbeat_at=now - timedelta(seconds=600),
        criado_em=now - timedelta(seconds=700),
    )
    session = AsyncMock()
    session.execute = AsyncMock(
        return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=run))
    )
    service = ScriptGenerationJobService(
        session,
        gateway=AsyncMock(),
        config=Settings(generation_stale_after_seconds=300),
    )
    claimed = await service.claim_next()
    assert claimed is run
    assert run.status == "running"
    assert run.heartbeat_at.tzinfo is not None


@pytest.mark.asyncio
async def test_heartbeat_update_preserves_timezone_awareness() -> None:
    now = datetime.now(UTC)
    run = SimpleNamespace(
        id=uuid4(),
        status="running",
        started_at=now - timedelta(seconds=100),
        heartbeat_at=now - timedelta(seconds=50),
        criado_em=now - timedelta(seconds=200),
        sections=[],
        evidence_dossier={"research_complete": True},
    )
    session = AsyncMock()
    session.commit = AsyncMock()
    session.refresh = AsyncMock()
    service = ScriptGenerationJobService(
        session, gateway=AsyncMock(), config=Settings()
    )
    service.get = AsyncMock(return_value=run)
    run.heartbeat_at = datetime.now(UTC)
    assert run.heartbeat_at.tzinfo is not None


def test_datetime_now_utc_produces_timezone_aware_values() -> None:
    now = datetime.now(UTC)
    assert now.tzinfo is not None
    naive = now.replace(tzinfo=None)
    assert naive.tzinfo is None
    aware_again = naive.replace(tzinfo=UTC)
    assert aware_again.tzinfo is not None


@pytest.mark.asyncio
async def test_v3_writer_receives_policy_audience_and_factuality_over_word_pressure() -> (
    None
):
    service, _, run, section = _writing_fixture()
    service._complete = AsyncMock(  # type: ignore[method-assign]
        return_value=_result(
            _written_json(580),
            role=LLMTaskRole.WRITING,
            max_tokens=7480,
            completion_tokens=1700,
        )
    )

    await service._write_section(run, section)

    call = service._complete.await_args.kwargs
    assert "Diretrizes de qualidade editorial" in call["system_prompt"]
    assert "NARRAÇÃO PT-BR" in call["system_prompt"]
    assert "FACTUALITY OVERRIDES WORD COUNT" in call["prompt"]
    assert "Entender o ponto central" in call["prompt"]
    assert call["prompt_version"] == "section_writer_v3"
    assert set(call["schema"]["properties"]) == {"content"}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("unsupported_prose", "category"),
    [
        ("Jacarés reagem ao ruído de motores.", "unsupported_specificity"),
        (
            "A deformação do terreno muda a dirigibilidade.",
            "unsupported_specificity",
        ),
        (
            "Rotas de cabotagem criam opções táticas e logísticas.",
            "unsupported_specificity",
        ),
        (
            "A Rockstar confirmou que o mapa da comunidade tem escala oficial.",
            "overstated_claim",
        ),
    ],
)
async def test_section_audit_contract_carries_real_unsupported_specificity_examples(
    unsupported_prose: str, category: str
) -> None:
    service, _, run, section = _writing_fixture()
    service._audit_section = ScriptGenerationJobService._audit_section.__get__(  # type: ignore[method-assign]
        service
    )
    issue = EditorialCriticIssue(
        section_key="section-001",
        category=category,  # type: ignore[arg-type]
        severity="revision_required",
        actionable_feedback="Remova ou qualifique a afirmação além da evidência.",
        excerpt=unsupported_prose,
    )
    audit = _section_audit(revision_required=True, issues=[issue], beats=[])
    service._complete = AsyncMock(  # type: ignore[method-assign]
        return_value=_result(
            audit.model_dump_json(),
            role=LLMTaskRole.CRITIC,
            max_tokens=2500,
        )
    )

    parsed, _ = await service._audit_section(
        run,
        section,
        content=unsupported_prose,
        evidence=[
            {
                "source_fragment_id": "official-material",
                "claims": ["O material mostra jacarés ou cenário industrial."],
            }
        ],
        approved_claims=[],
        previous_actual=[],
        idea=SimpleNamespace(author_briefing=None),
        niche_prompt="Separe observação de mecânica.",
    )

    assert parsed.revision_required is True
    assert parsed.issues[0].category == category
    prompt = service._complete.await_args.kwargs["prompt"]
    assert unsupported_prose in prompt
    assert "FULL SECTION PROSE" in prompt
    assert "unsupported_specificity" in prompt
    assert service._complete.await_args.kwargs["structured_mode"] == "json_schema"


@pytest.mark.asyncio
async def test_qualified_community_estimate_can_pass_section_audit() -> None:
    service, _, run, section = _writing_fixture()
    service._audit_section = ScriptGenerationJobService._audit_section.__get__(  # type: ignore[method-assign]
        service
    )
    claim_id = "claim-community"
    run.plan["editorial"]["claim_ledger"] = [{"id": claim_id}]
    audit = _section_audit(
        claims=[claim_id],
        claim_language_assessments=[
            {
                "claim_ref": claim_id,
                "language_proportional": True,
                "attribution_present": True,
                "qualification_present": True,
                "scope_preserved": True,
            }
        ],
    )
    service._complete = AsyncMock(  # type: ignore[method-assign]
        return_value=_result(
            audit.model_dump_json(),
            role=LLMTaskRole.CRITIC,
            max_tokens=2500,
        )
    )
    parsed, _ = await service._audit_section(
        run,
        section,
        content="Uma estimativa da comunidade sugere um mapa maior; não é confirmação da Rockstar.",
        evidence=[],
        approved_claims=[
            {
                "id": claim_id,
                "summary": "A comunidade estima um mapa maior.",
                "source_trust": "community",
                "claim_status": "speculation",
            }
        ],
        previous_actual=[],
        idea=SimpleNamespace(author_briefing=None),
        niche_prompt=None,
    )
    assert parsed.revision_required is False
    assert parsed.actual_claim_refs == [claim_id]


@pytest.mark.asyncio
async def test_section_audit_rejects_unknown_claim_and_drops_unobserved_beats() -> None:
    service, _, run, section = _writing_fixture()
    service._audit_section = ScriptGenerationJobService._audit_section.__get__(  # type: ignore[method-assign]
        service
    )
    service._complete = AsyncMock(  # type: ignore[method-assign]
        return_value=_result(
            _section_audit(claims=["invented"]).model_dump_json(),
            role=LLMTaskRole.CRITIC,
        )
    )
    with pytest.raises(GenerationJobError, match="unknown claims"):
        await service._audit_section(
            run,
            section,
            content="Texto.",
            evidence=[],
            approved_claims=[],
            previous_actual=[],
            idea=SimpleNamespace(author_briefing=None),
            niche_prompt=None,
        )

    service._complete = AsyncMock(  # type: ignore[method-assign]
        return_value=_result(
            _section_audit(beats=["Beat inventado"]).model_dump_json(),
            role=LLMTaskRole.CRITIC,
        )
    )
    audit, provenance = await service._audit_section(
        run,
        section,
        content="Texto.",
        evidence=[],
        approved_claims=[],
        previous_actual=[],
        idea=SimpleNamespace(author_briefing=None),
        niche_prompt=None,
    )
    assert audit.actual_beats_covered == []
    assert provenance["dropped_unplanned_beats"] == ["Beat inventado"]


@pytest.mark.asyncio
async def test_targeted_section_revision_is_bounded_and_uses_actual_audit_metadata() -> (
    None
):
    service, _, run, section = _writing_fixture()
    issue = EditorialCriticIssue(
        section_key="section-001",
        category="fake_hype",
        severity="revision_required",
        actionable_feedback="Remova a grandiosidade sem substância.",
    )
    service._audit_section = AsyncMock(  # type: ignore[method-assign]
        side_effect=[
            (_section_audit(revision_required=True, issues=[issue]), {}),
            (
                _section_audit(
                    beats=[],
                ).model_copy(
                    update={
                        "actual_summary": "Resumo real revisado.",
                        "opened_loops": ["Pergunta real"],
                    }
                ),
                {},
            ),
        ]
    )
    service._complete = AsyncMock(  # type: ignore[method-assign]
        side_effect=[
            _result(_written_json(580, marker="hipérbole"), role=LLMTaskRole.WRITING),
            _result(_written_json(580, marker="concreto"), role=LLMTaskRole.WRITING),
        ]
    )

    await service._write_section(run, section)

    assert service._complete.await_count == 2
    assert section.attempt_count == 2
    assert section.prompt_provenance["editorial_revision_count"] == 1
    assert section.prompt_provenance["capacity_retry_count"] == 0
    assert section.output["actual_summary"] == "Resumo real revisado."
    assert section.output["beats_covered"] == []
    assert (
        run.continuity_state["completed_sections"][0]["actual_summary"]
        == "Resumo real revisado."
    )


@pytest.mark.asyncio
async def test_global_critic_receives_full_staged_content_and_section_audits() -> None:
    session = AsyncMock()
    service = ScriptGenerationJobService(session, gateway=AsyncMock(), config=_config())
    service._editorial_context = AsyncMock(  # type: ignore[method-assign]
        return_value=(SimpleNamespace(author_briefing=None), None, get_profile(None))
    )
    critic = EditorialCriticOutput(
        summary="Sem bloqueadores.",
        issues=[],
        open_loops_closed=True,
        unsupported_claims_detected=False,
    )
    service._global_critic_call = AsyncMock(  # type: ignore[method-assign]
        return_value=(critic, {"critic": "test"})
    )
    marker = "PROBLEMA NO MEIO E NO FIM DA SEÇÃO"
    section = SimpleNamespace(
        section_key="section-001",
        section_order=0,
        chapter_order=0,
        section_plan={"purpose": "Explicar", "must_cover": [], "must_not_repeat": []},
        local_validation={"status": "within_budget"},
        output={
            "content": "abertura " + ("x" * 700) + marker,
            "claims_used": [],
            "section_audit": {"actual_summary": "Resumo real", "issues": []},
        },
    )
    run = SimpleNamespace(
        id=uuid4(),
        ideia_id=uuid4(),
        production_profile="faceless_general",
        generation_strategy="staged",
        sections=[section],
        plan={
            "editorial": {
                "thesis": "Tese",
                "audience_promise": "Promessa",
                "open_loops": [],
                "claim_ledger": [],
            }
        },
    )

    await service._run_global_critic(run, audit_scope="initial")

    payload = service._global_critic_call.await_args.kwargs["payload"]
    assert payload["mode"] == "full_staged_prose"
    assert marker in payload["sections"][0]["full_content"]
    assert payload["sections"][0]["section_audit"]["actual_summary"] == "Resumo real"
    assert run.plan["global_critic"]["summary"] == "Sem bloqueadores."


@pytest.mark.asyncio
async def test_global_critic_unavailable_is_not_silently_factuality_pass() -> None:
    service = ScriptGenerationJobService(
        AsyncMock(), gateway=AsyncMock(), config=_config()
    )
    service._editorial_context = AsyncMock(  # type: ignore[method-assign]
        return_value=(SimpleNamespace(author_briefing=None), None, get_profile(None))
    )
    service._global_critic_call = AsyncMock(  # type: ignore[method-assign]
        side_effect=LLMGatewayError(LLMFailureCategory.PROVIDER, "critic down")
    )
    run = SimpleNamespace(
        id=uuid4(),
        ideia_id=uuid4(),
        production_profile="faceless_general",
        generation_strategy="staged",
        sections=[],
        plan={
            "editorial": {
                "thesis": "Tese",
                "audience_promise": "Promessa",
                "open_loops": [],
                "claim_ledger": [],
            }
        },
    )
    with pytest.raises(LLMGatewayError):
        await service._run_global_critic(run, audit_scope="initial")


@pytest.mark.asyncio
async def test_global_critic_cannot_report_unsupported_claims_without_actionable_issue() -> (
    None
):
    service = ScriptGenerationJobService(
        AsyncMock(), gateway=AsyncMock(), config=_config()
    )
    service._editorial_context = AsyncMock(  # type: ignore[method-assign]
        return_value=(SimpleNamespace(author_briefing=None), None, get_profile(None))
    )
    service._global_critic_call = AsyncMock(  # type: ignore[method-assign]
        return_value=(
            EditorialCriticOutput(
                summary="Há afirmação sem suporte.",
                issues=[],
                open_loops_closed=True,
                unsupported_claims_detected=True,
            ),
            {},
        )
    )
    run = SimpleNamespace(
        id=uuid4(),
        ideia_id=uuid4(),
        production_profile="faceless_general",
        generation_strategy="staged",
        sections=[],
        plan={
            "editorial": {
                "thesis": "Tese",
                "audience_promise": "Promessa",
                "open_loops": [],
                "claim_ledger": [],
            }
        },
    )

    with pytest.raises(GenerationJobError, match="without an actionable factual issue"):
        await service._run_global_critic(run, audit_scope="initial")


@pytest.mark.asyncio
async def test_resume_after_global_correction_never_opens_second_correction_cycle() -> (
    None
):
    service = ScriptGenerationJobService(
        AsyncMock(), gateway=AsyncMock(), config=_config()
    )
    blocking = EditorialCriticOutput(
        summary="Ainda há claim sem suporte.",
        issues=[
            EditorialCriticIssue(
                section_key="section-001",
                category="unsupported_claim",
                severity="blocking",
                actionable_feedback="Remova o claim.",
            )
        ],
        open_loops_closed=True,
        unsupported_claims_detected=True,
    )
    service._run_global_critic = AsyncMock(return_value=blocking)  # type: ignore[method-assign]
    service._apply_global_factual_corrections = AsyncMock()  # type: ignore[method-assign]
    run = SimpleNamespace(
        id=uuid4(),
        ideia_id=uuid4(),
        plan={"global_correction": {"cycles": 1}},
    )

    with (
        patch(
            "app.services.script_generation_jobs.IdeiaRepository.get_by_id",
            new=AsyncMock(return_value=SimpleNamespace()),
        ),
        pytest.raises(GenerationJobError, match="retained unsupported"),
    ):
        await service._assemble(run)

    assert service._run_global_critic.await_args.kwargs["audit_scope"] == "final"
    service._apply_global_factual_corrections.assert_not_awaited()


@pytest.mark.asyncio
async def test_unsupported_claim_warning_is_promoted_to_targeted_revision() -> None:
    service, _, run, section = _writing_fixture()
    issue = EditorialCriticIssue(
        section_key="section-001",
        category="unsupported_claim",
        severity="warning",
        actionable_feedback="Remova a afirmação sem claim aprovado.",
    )
    service._audit_section = AsyncMock(  # type: ignore[method-assign]
        side_effect=[
            (_section_audit(revision_required=True, issues=[issue]), {}),
            (_section_audit(), {}),
        ]
    )
    service._complete = AsyncMock(  # type: ignore[method-assign]
        side_effect=[
            _result(_written_json(580), role=LLMTaskRole.WRITING),
            _result(_written_json(580), role=LLMTaskRole.WRITING),
        ]
    )

    await service._write_section(run, section)

    assert service._complete.await_count == 2
    second_prompt = service._complete.await_args_list[1].kwargs["prompt"]
    assert "Remova a afirmação sem claim aprovado" in second_prompt
    assert section.prompt_provenance["editorial_revision_count"] == 1


@pytest.mark.asyncio
async def test_section_audit_promotes_unsupported_claim_warning_to_revision() -> None:
    service, _, run, section = _writing_fixture()
    service._audit_section = ScriptGenerationJobService._audit_section.__get__(  # type: ignore[method-assign]
        service
    )
    audit = _section_audit(
        issues=[
            EditorialCriticIssue(
                section_key="section-001",
                category="unsupported_claim",
                severity="warning",
                actionable_feedback="Remova.",
            )
        ]
    )
    service._complete = AsyncMock(  # type: ignore[method-assign]
        return_value=_result(
            audit.model_dump_json(),
            role=LLMTaskRole.CRITIC,
            max_tokens=2500,
        )
    )

    parsed, _ = await service._audit_section(
        run,
        section,
        content="Afirmação sem claim aprovado.",
        evidence=[],
        approved_claims=[],
        previous_actual=[],
        idea=SimpleNamespace(author_briefing=None),
        niche_prompt=None,
    )

    assert parsed.revision_required is True


def test_audit_contracts_define_each_issue_field_and_reject_description_alias() -> None:
    section_contract = _section_audit_output_contract()
    global_contract = _global_critic_output_contract()
    for contract in (section_contract, global_contract):
        assert "section_key, category, severity" in contract
        assert "actionable_feedback, claim_ref and excerpt" in contract
        assert "Never use description" in contract
        assert "unsupported_specificity" in contract
    assert "compound beat is covered only" in section_contract


@pytest.mark.asyncio
async def test_description_only_section_issue_is_repaired_with_exact_contract() -> None:
    service, _, run, section = _writing_fixture()
    service._audit_section = ScriptGenerationJobService._audit_section.__get__(  # type: ignore[method-assign]
        service
    )
    invalid = json.dumps(
        {
            "revision_required": True,
            "issues": [
                {"description": "Afirmação mecânica além da evidência disponível."}
            ],
            "actual_claim_refs": [],
            "actual_beats_covered": [],
            "actual_summary": "A seção extrapola a observação disponível.",
            "opened_loops": [],
            "closed_loops": [],
        }
    )
    repaired = _section_audit(
        revision_required=True,
        issues=[
            EditorialCriticIssue(
                section_key="section-001",
                category="unsupported_specificity",
                severity="revision_required",
                actionable_feedback="Remova a reação ao ruído dos motores.",
            )
        ],
        beats=[],
    )
    service._complete = AsyncMock(  # type: ignore[method-assign]
        side_effect=[
            _result(invalid, role=LLMTaskRole.CRITIC, max_tokens=2500),
            _result(
                repaired.model_dump_json(),
                role=LLMTaskRole.REPAIR,
                max_tokens=3500,
            ),
        ]
    )

    parsed, provenance = await service._audit_section(
        run,
        section,
        content="Jacarés reagem ao ruído dos motores.",
        evidence=[],
        approved_claims=[],
        previous_actual=[],
        idea=SimpleNamespace(author_briefing=None),
        niche_prompt=None,
    )

    assert parsed.issues[0].category == "unsupported_specificity"
    assert provenance["repair_reason"] == "ValidationError"
    assert service._complete.await_count == 2
    repair_prompt = service._complete.await_args_list[1].kwargs["prompt"]
    assert "Never use description" in repair_prompt


@pytest.mark.asyncio
async def test_description_only_section_issue_remains_bounded_when_repair_is_invalid() -> (
    None
):
    service, _, run, section = _writing_fixture()
    service._audit_section = ScriptGenerationJobService._audit_section.__get__(  # type: ignore[method-assign]
        service
    )
    invalid = json.dumps(
        {
            "revision_required": True,
            "issues": [{"description": "Sem shape contratual."}],
            "actual_claim_refs": [],
            "actual_beats_covered": [],
            "actual_summary": "Resumo.",
            "opened_loops": [],
            "closed_loops": [],
        }
    )
    service._complete = AsyncMock(  # type: ignore[method-assign]
        side_effect=[
            _result(invalid, role=LLMTaskRole.CRITIC, max_tokens=2500),
            _result(invalid, role=LLMTaskRole.REPAIR, max_tokens=3500),
        ]
    )

    with pytest.raises(LLMGatewayError, match="remained invalid"):
        await service._audit_section(
            run,
            section,
            content="Texto.",
            evidence=[],
            approved_claims=[],
            previous_actual=[],
            idea=SimpleNamespace(author_briefing=None),
            niche_prompt=None,
        )

    assert service._complete.await_count == 2


@pytest.mark.asyncio
async def test_external_research_resume_preserves_completed_claim_checkpoints(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = AsyncMock()
    source = ResearchSource(
        source_id="external-stable-1",
        query="query",
        title="Fonte",
        url="https://news.example/fonte",
        snippet="A fonte sustenta uma afirmação limitada.",
        source_type="external_search_result",
        retrieved_at="2026-08-31T00:00:00+00:00",
        domain="news.example",
    )
    research = AsyncMock()
    research.search.return_value = [source]
    service = ScriptGenerationJobService(
        session, gateway=AsyncMock(), research_client=research, config=_config()
    )
    idea = SimpleNamespace(
        titulo="Pauta factual",
        descricao_breve="Descrição",
        nicho_id=None,
        author_briefing=None,
    )
    monkeypatch.setattr(
        "app.services.script_generation_jobs.IdeiaRepository.get_by_id",
        AsyncMock(return_value=idea),
    )
    claim = {
        "id": "claim-stable",
        "summary": "A fonte sustenta uma afirmação limitada.",
        "source_refs": [source.source_id],
        "source_fragment_id": source.source_id,
        "source_trust": "unverified",
        "claim_status": "reported",
        "confidence": 0.5,
        "qualification": "Relato não confirmado por fonte primária.",
        "support_scope": "Somente a afirmação citada.",
        "evidence_tier": "unverified",
    }
    run = SimpleNamespace(
        id=uuid4(),
        ideia_id=uuid4(),
        production_profile="faceless_general",
        target_words=None,
        evidence_dossier={
            "sources": [source.to_dict()],
            "fragments": [
                {
                    "source_fragment_id": source.source_id,
                    "title": source.title,
                    "url": source.url,
                    "snippet": source.snippet,
                    "source_trust": "unverified",
                    "claim_extraction_status": "completed",
                    "claims": [claim],
                }
            ],
            "claims": [claim],
            "research_complete": False,
        },
        heartbeat_at=None,
    )

    await service._build_external_evidence_dossier(run)

    assert run.evidence_dossier["claims"] == [claim]
    assert run.evidence_dossier["fragments"][0]["claims"] == [claim]
    assert run.evidence_dossier["research_complete"] is True
    service._complete = AsyncMock()  # type: ignore[method-assign]
    await service._extract_external_claims(run, idea)
    service._complete.assert_not_awaited()


@pytest.mark.asyncio
async def test_short_research_expands_before_claim_extraction_when_no_trusted_source(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = AsyncMock()
    unverified = ResearchSource(
        source_id="external-community",
        query="initial",
        title="Community report",
        url="https://unknown.example/gta-vi",
        snippet="Community description of GTA VI.",
        source_type="external_search_result",
        retrieved_at="2026-09-01T00:00:00+00:00",
        domain="unknown.example",
    )
    official = ResearchSource(
        source_id="external-rockstar",
        query="official",
        title="Grand Theft Auto VI - Rockstar Games",
        url="https://www.rockstargames.com/VI",
        snippet="Official descriptions for the GTA VI characters.",
        source_type="external_search_result",
        retrieved_at="2026-09-01T00:00:00+00:00",
        domain="rockstargames.com",
    )
    research = AsyncMock()
    research.search.side_effect = [[unverified], [official]]
    service = ScriptGenerationJobService(
        session, gateway=AsyncMock(), research_client=research, config=_config()
    )
    idea = SimpleNamespace(
        titulo="GTA VI personagens oficiais",
        descricao_breve="Contraste entre personagens apresentados pela Rockstar.",
        nicho_id=None,
        author_briefing="Use apenas informações oficialmente confirmadas pela Rockstar.",
    )
    monkeypatch.setattr(
        "app.services.script_generation_jobs.IdeiaRepository.get_by_id",
        AsyncMock(return_value=idea),
    )
    run = SimpleNamespace(
        id=uuid4(),
        ideia_id=uuid4(),
        production_profile="faceless_general",
        target_duration_seconds=60,
        target_words=145,
        evidence_dossier={},
        heartbeat_at=None,
    )

    async def extract_claims(current_run, _idea):
        dossier = dict(current_run.evidence_dossier)
        claims = [
            {
                "id": f"claim-{index}",
                "summary": f"Official claim {index}",
                "source_refs": [official.source_id],
                "source_fragment_id": official.source_id,
                "source_trust": "primary_official",
                "claim_status": "confirmed",
                "confidence": 0.9,
                "evidence_tier": "official_confirmed",
            }
            for index in range(3)
        ]
        dossier["claims"] = claims
        for fragment in dossier.get("fragments") or []:
            fragment["claims"] = claims
            fragment["claim_extraction_status"] = "completed"
        current_run.evidence_dossier = dossier

    service._extract_external_claims = AsyncMock(  # type: ignore[method-assign]
        side_effect=extract_claims
    )

    await service._build_external_evidence_dossier(run)

    assert research.search.await_count == 2
    assert run.evidence_dossier["query_count"] == 2
    assert run.evidence_dossier["selected_source_count"] == 1
    assert (
        run.evidence_dossier["fragments"][0]["source_fragment_id"] == official.source_id
    )
    assert run.evidence_dossier["source_preselection_expansion"] == {
        "attempted": True,
        "mode": "primary_required",
        "query": research.search.await_args_list[1].args[0],
        "new_candidates": 1,
        "trusted_candidates_found": 1,
        "primary_candidates_found": 1,
    }
    assert research.search.await_args_list[1].args[0].endswith("site:rockstargames.com")
    assert research.search.await_args_list[1].kwargs["include_domains"] == (
        "rockstargames.com",
        "youtube.com",
    )


@pytest.mark.asyncio
async def test_generic_gta_brief_continues_with_reliable_secondary_without_primary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = AsyncMock()
    secondary = ResearchSource(
        source_id="external-reuters",
        query="initial",
        title="Reportagem sobre GTA VI",
        url="https://www.reuters.com/technology/gta-vi-report",
        snippet="A reportagem atribui à empresa uma informação sobre GTA VI.",
        source_type="external_search_result",
        retrieved_at="2026-09-02T00:00:00+00:00",
        domain="reuters.com",
    )
    research = AsyncMock()
    research.search.return_value = [secondary]
    service = ScriptGenerationJobService(
        session, gateway=AsyncMock(), research_client=research, config=_config()
    )
    idea = SimpleNamespace(
        titulo="Faça uma análise de GTA VI",
        descricao_breve="Contextualize o que sabemos até agora.",
        nicho_id=None,
        author_briefing=None,
    )
    monkeypatch.setattr(
        "app.services.script_generation_jobs.IdeiaRepository.get_by_id",
        AsyncMock(return_value=idea),
    )
    run = SimpleNamespace(
        id=uuid4(),
        ideia_id=uuid4(),
        production_profile="faceless_general",
        target_duration_seconds=60,
        target_words=145,
        evidence_dossier={},
        heartbeat_at=None,
    )

    async def extract_claims(current_run, _idea):
        dossier = dict(current_run.evidence_dossier)
        claim = {
            "id": "claim-reported",
            "summary": "A reportagem atribui à empresa uma informação sobre GTA VI.",
            "source_refs": [secondary.source_id],
            "source_fragment_id": secondary.source_id,
            "source_trust": "reliable_secondary",
            "claim_status": "reported",
            "confidence": 0.7,
            "qualification": "Segundo a reportagem.",
            "support_scope": "Somente a informação reportada.",
            "evidence_tier": "reliable_secondary",
        }
        dossier["claims"] = [claim]
        for fragment in dossier.get("fragments") or []:
            fragment["claims"] = [claim]
            fragment["claim_extraction_status"] = "completed"
        current_run.evidence_dossier = dossier

    service._extract_external_claims = AsyncMock(  # type: ignore[method-assign]
        side_effect=extract_claims
    )

    await service._build_external_evidence_dossier(run)

    assert research.search.await_count == 1
    assert run.evidence_dossier["primary_source_required"] is False
    assert run.evidence_dossier["research_status"] == "completed"
    assert run.evidence_dossier["selected_source_count"] == 1
    assert run.evidence_dossier["claims"][0]["source_trust"] == "reliable_secondary"
    assert run.evidence_dossier["claims"][0]["claim_status"] == "reported"
    assert "source_preselection_expansion" not in run.evidence_dossier
    assert (
        run.evidence_dossier["query_count"]
        <= run.evidence_dossier["research_budget"]["total_queries"]
    )


@pytest.mark.asyncio
async def test_short_research_recovers_reliable_source_within_existing_budget(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    community = ResearchSource(
        source_id="external-reddit",
        query="initial",
        title="Community discussion about GTA VI",
        url="https://www.reddit.com/r/GTA6/comments/example",
        snippet="Players discuss a report about GTA VI.",
        source_type="external_search_result",
        retrieved_at="2026-09-02T00:00:00+00:00",
        domain="reddit.com",
    )
    secondary = ResearchSource(
        source_id="external-ign",
        query="trusted recovery",
        title="GTA VI report",
        url="https://www.ign.com/articles/gta-vi-report",
        snippet="IGN reports contextual information about GTA VI.",
        source_type="external_search_result",
        retrieved_at="2026-09-02T00:00:00+00:00",
        domain="ign.com",
    )
    research = AsyncMock()
    research.search.side_effect = [[community], [secondary]]
    service = ScriptGenerationJobService(
        AsyncMock(), gateway=AsyncMock(), research_client=research, config=_config()
    )
    idea = SimpleNamespace(
        titulo="Faça uma análise de GTA VI",
        descricao_breve="Contextualize uma reportagem sem tratá-la como confirmação.",
        nicho_id=None,
        author_briefing=None,
    )
    monkeypatch.setattr(
        "app.services.script_generation_jobs.IdeiaRepository.get_by_id",
        AsyncMock(return_value=idea),
    )
    run = SimpleNamespace(
        id=uuid4(),
        ideia_id=uuid4(),
        production_profile="faceless_general",
        target_duration_seconds=60,
        target_words=145,
        evidence_dossier={},
        heartbeat_at=None,
    )

    async def extract_claims(current_run, _idea):
        dossier = dict(current_run.evidence_dossier)
        claims = [
            {
                "id": f"claim-reported-{index}",
                "summary": f"IGN reports contextual information {index}.",
                "source_refs": [secondary.source_id],
                "source_fragment_id": secondary.source_id,
                "source_trust": "reliable_secondary",
                "claim_status": "reported",
                "confidence": 0.7,
                "qualification": "Segundo a reportagem.",
                "support_scope": "Somente a informação reportada.",
                "evidence_tier": "reliable_secondary",
            }
            for index in range(3)
        ]
        dossier["claims"] = claims
        for fragment in dossier.get("fragments") or []:
            fragment["claims"] = claims
            fragment["claim_extraction_status"] = "completed"
        current_run.evidence_dossier = dossier

    service._extract_external_claims = AsyncMock(  # type: ignore[method-assign]
        side_effect=extract_claims
    )

    await service._build_external_evidence_dossier(run)

    assert research.search.await_count == 2
    assert run.evidence_dossier["query_count"] == 2
    assert (
        run.evidence_dossier["query_count"]
        <= run.evidence_dossier["research_budget"]["total_queries"]
    )
    assert run.evidence_dossier["selected_source_count"] == 1
    assert run.evidence_dossier["fragments"][0]["source_trust"] == (
        "reliable_secondary"
    )
    recovery = run.evidence_dossier["source_preselection_expansion"]
    assert recovery["mode"] == "trusted_preference"
    assert recovery["trusted_candidates_found"] == 1
    hinted_domains = research.search.await_args_list[1].kwargs["include_domains"]
    assert "rockstargames.com" in hinted_domains
    assert "reuters.com" in hinted_domains
    assert "ign.com" in hinted_domains


@pytest.mark.asyncio
async def test_short_research_continues_when_trusted_recovery_does_not_improve(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    community = ResearchSource(
        source_id="external-reddit",
        query="initial",
        title="GTA VI community report",
        url="https://www.reddit.com/r/GTA6/comments/example",
        snippet="Players report observations about GTA VI.",
        source_type="external_search_result",
        retrieved_at="2026-09-02T00:00:00+00:00",
        domain="reddit.com",
    )
    unverified = ResearchSource(
        source_id="external-unknown",
        query="recovery",
        title="GTA VI unofficial summary",
        url="https://unknown.example/gta-vi",
        snippet="An unofficial summary repeats GTA VI community reports.",
        source_type="external_search_result",
        retrieved_at="2026-09-02T00:00:00+00:00",
        domain="unknown.example",
    )
    research = AsyncMock()
    research.search.side_effect = [[community], [unverified]]
    service = ScriptGenerationJobService(
        AsyncMock(), gateway=AsyncMock(), research_client=research, config=_config()
    )
    idea = SimpleNamespace(
        titulo="Faça uma análise de GTA VI",
        descricao_breve="Relatos da comunidade, com qualificação explícita.",
        nicho_id=None,
        author_briefing=None,
    )
    monkeypatch.setattr(
        "app.services.script_generation_jobs.IdeiaRepository.get_by_id",
        AsyncMock(return_value=idea),
    )
    run = SimpleNamespace(
        id=uuid4(),
        ideia_id=uuid4(),
        production_profile="faceless_general",
        target_duration_seconds=60,
        target_words=145,
        evidence_dossier={},
        heartbeat_at=None,
    )

    async def extract_claims(current_run, _idea):
        dossier = dict(current_run.evidence_dossier)
        claims = [
            {
                "id": f"claim-community-{index}",
                "summary": f"Community members report observation {index}.",
                "source_refs": [community.source_id],
                "source_fragment_id": community.source_id,
                "source_trust": "community",
                "claim_status": "reported",
                "confidence": 0.5,
                "qualification": "Relato da comunidade.",
                "support_scope": "Somente a existência do relato.",
                "evidence_tier": "community",
            }
            for index in range(3)
        ]
        dossier["claims"] = claims
        for fragment in dossier.get("fragments") or []:
            fragment["claims"] = claims
            fragment["claim_extraction_status"] = "completed"
        current_run.evidence_dossier = dossier

    service._extract_external_claims = AsyncMock(  # type: ignore[method-assign]
        side_effect=extract_claims
    )

    await service._build_external_evidence_dossier(run)

    assert research.search.await_count == 2
    assert run.evidence_dossier["research_status"] == "completed"
    assert run.evidence_dossier["primary_source_required"] is False
    assert run.evidence_dossier["query_count"] == 2
    assert (
        run.evidence_dossier["query_count"]
        <= run.evidence_dossier["research_budget"]["total_queries"]
    )
    assert {
        fragment["source_trust"] for fragment in run.evidence_dossier["fragments"]
    } == {
        "community",
        "unverified",
    }
    assert (
        run.evidence_dossier["source_preselection_expansion"][
            "trusted_candidates_found"
        ]
        == 0
    )


@pytest.mark.asyncio
async def test_explicit_official_only_brief_fails_after_one_bounded_recovery(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = AsyncMock()
    secondary = ResearchSource(
        source_id="external-reuters",
        query="initial",
        title="Reportagem sobre GTA VI",
        url="https://www.reuters.com/technology/gta-vi-report",
        snippet="Uma reportagem secundária sobre GTA VI.",
        source_type="external_search_result",
        retrieved_at="2026-09-02T00:00:00+00:00",
        domain="reuters.com",
    )
    unverified = ResearchSource(
        source_id="external-unverified",
        query="official recovery",
        title="Resumo não oficial",
        url="https://unknown.example/gta-vi",
        snippet="Um resumo não oficial sobre GTA VI.",
        source_type="external_search_result",
        retrieved_at="2026-09-02T00:00:00+00:00",
        domain="unknown.example",
    )
    research = AsyncMock()
    research.search.side_effect = [[secondary], [unverified]]
    service = ScriptGenerationJobService(
        session, gateway=AsyncMock(), research_client=research, config=_config()
    )
    service._extract_external_claims = AsyncMock()  # type: ignore[method-assign]
    idea = SimpleNamespace(
        titulo="GTA VI confirmado",
        descricao_breve="Liste somente recursos confirmados.",
        nicho_id=None,
        author_briefing="Use apenas informações oficialmente confirmadas pela Rockstar.",
    )
    monkeypatch.setattr(
        "app.services.script_generation_jobs.IdeiaRepository.get_by_id",
        AsyncMock(return_value=idea),
    )
    run = SimpleNamespace(
        id=uuid4(),
        ideia_id=uuid4(),
        production_profile="faceless_general",
        target_duration_seconds=60,
        target_words=145,
        evidence_dossier={},
        heartbeat_at=None,
    )

    with pytest.raises(GenerationJobError, match="primary official evidence"):
        await service._build_external_evidence_dossier(run)

    assert research.search.await_count == 2
    assert research.search.await_args_list[1].args[0].endswith("site:rockstargames.com")
    assert research.search.await_args_list[1].kwargs["include_domains"] == (
        "rockstargames.com",
        "youtube.com",
    )
    assert (
        run.evidence_dossier["query_count"]
        <= run.evidence_dossier["research_budget"]["total_queries"]
    )
    service._extract_external_claims.assert_not_awaited()
    assert run.evidence_dossier["primary_source_required"] is True
    assert run.evidence_dossier["research_status"] == (
        "blocked_primary_source_unavailable"
    )


@pytest.mark.asyncio
async def test_fixed_target_with_insufficient_capacity_blocks_after_one_expansion(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = AsyncMock()
    source = ResearchSource(
        source_id="capacity-source",
        query="query",
        title="Fonte limitada",
        url="https://news.example/limited",
        snippet="Uma única afirmação curta.",
        source_type="external_search_result",
        retrieved_at="2026-09-01T00:00:00+00:00",
        domain="news.example",
    )
    research = AsyncMock()
    research.search.return_value = [source]
    service = ScriptGenerationJobService(
        session, gateway=AsyncMock(), research_client=research, config=_config()
    )
    idea = SimpleNamespace(
        titulo="Pauta extensa",
        descricao_breve="Contrato longo com evidência curta",
        nicho_id=None,
        author_briefing=None,
    )
    monkeypatch.setattr(
        "app.services.script_generation_jobs.IdeiaRepository.get_by_id",
        AsyncMock(return_value=idea),
    )
    run = SimpleNamespace(
        id=uuid4(),
        ideia_id=uuid4(),
        production_profile="faceless_general",
        target_words=2000,
        evidence_dossier={
            "sources": [],
            "fragments": [],
            "claims": [],
            "research_complete": False,
        },
        heartbeat_at=None,
    )

    async def extract_claim(current_run, _idea):
        dossier = dict(current_run.evidence_dossier)
        claim = {
            "id": "claim-limited",
            "summary": "Uma única afirmação curta.",
            "source_refs": [source.source_id],
            "source_fragment_id": source.source_id,
            "source_trust": "unverified",
            "claim_status": "reported",
            "confidence": 0.5,
            "evidence_tier": "unverified",
        }
        dossier["claims"] = [claim]
        for fragment in dossier.get("fragments") or []:
            fragment["claims"] = [claim]
            fragment["claim_extraction_status"] = "completed"
        current_run.evidence_dossier = dossier

    service._extract_external_claims = AsyncMock(  # type: ignore[method-assign]
        side_effect=extract_claim
    )

    with pytest.raises(GenerationJobError, match="insufficient_evidence"):
        await service._build_external_evidence_dossier(run)

    assert research.search.await_count == 4
    assert run.evidence_dossier["capacity"]["advisory_only"] is False
    assert (
        run.evidence_dossier["capacity"]["workflow_action"]
        == "blocked_insufficient_evidence"
    )


@pytest.mark.asyncio
async def test_grounded_profile_fails_when_external_research_is_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    research = AsyncMock()
    research.search.return_value = []
    service = ScriptGenerationJobService(
        AsyncMock(), gateway=AsyncMock(), research_client=research, config=_config()
    )
    monkeypatch.setattr(
        "app.services.script_generation_jobs.IdeiaRepository.get_by_id",
        AsyncMock(
            return_value=SimpleNamespace(
                titulo="Pauta factual",
                descricao_breve="Descrição",
                nicho_id=None,
            )
        ),
    )
    run = SimpleNamespace(
        id=uuid4(),
        ideia_id=uuid4(),
        production_profile="faceless_general",
        target_words=580,
        evidence_dossier={},
        heartbeat_at=None,
    )

    with pytest.raises(GenerationJobError) as captured:
        await service._build_external_evidence_dossier(run)

    assert captured.value.category is GenerationFailureCategory.GROUNDING


def test_review_status_blocks_factual_revision_but_not_style_warning() -> None:
    run = SimpleNamespace(
        sections=[],
        plan={},
    )
    style = EditorialCriticOutput(
        summary="Ajuste de estilo.",
        issues=[
            EditorialCriticIssue(
                category="spoken_language",
                severity="warning",
                actionable_feedback="Simplifique uma frase.",
            )
        ],
        open_loops_closed=True,
        unsupported_claims_detected=False,
    )
    style_review = _editorial_review_payload(run, style)
    assert style_review["editorial_status"] == "warn"
    assert style_review["approval_blocked"] is False

    factual = EditorialCriticOutput(
        summary="Fato sem suporte.",
        issues=[
            EditorialCriticIssue(
                section_key="section-001",
                category="unsupported_specificity",
                severity="blocking",
                actionable_feedback="Remova.",
            )
        ],
        open_loops_closed=True,
        unsupported_claims_detected=True,
    )
    factual_review = _editorial_review_payload(run, factual)
    assert factual_review["approval_blocked"] is True


@pytest.mark.asyncio
async def test_prompt_identity_is_call_specific_and_keeps_strategy_provenance() -> None:
    gateway = MagicMock()
    gateway.model_for.return_value = "standard-route"
    gateway.complete = AsyncMock(
        side_effect=lambda **kwargs: _result(
            "{}", role=kwargs["role"], max_tokens=kwargs["max_tokens"]
        )
    )
    run = SimpleNamespace(
        call_usage={"calls": 0, "total_tokens": 0},
        model_policy={"strategy": "standard"},
        strategy_identity="same-strategy",
    )
    service = ScriptGenerationJobService(AsyncMock(), gateway=gateway, config=_config())
    await service._complete(
        run,
        role=LLMTaskRole.PLANNING,
        prompt="same user text",
        schema={"type": "object"},
        max_tokens=100,
        prompt_version="planning-v1",
        scope="global",
    )
    await service._complete(
        run,
        role=LLMTaskRole.CRITIC,
        prompt="same user text",
        schema={"type": "object"},
        max_tokens=100,
        prompt_version="critic-v1",
        scope="global",
    )
    identities = [
        call.kwargs["prompt_identity"] for call in gateway.complete.await_args_list
    ]
    assert identities[0] != identities[1]
    assert all(len(item) == 64 for item in identities)
    assert {
        item["strategy_identity"] for item in run.call_usage["prompt_identities"]
    } == {"same-strategy"}
