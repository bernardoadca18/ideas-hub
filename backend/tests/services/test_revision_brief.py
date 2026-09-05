from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from app.core.config import Settings
from app.production_profiles import get_profile
from app.prompts.editorial_v3 import compose_editorial_v3_prompt
from app.schemas.generation import (
    EditorialCriticIssue,
    EditorialCriticOutput,
    GlobalEditorialPlanOutput,
    SectionEditorialAuditOutput,
)
from app.schemas.roteiro import RoteiroEstrutura
from app.services.duration_contract import (
    DurationCalibration,
    revision_duration_diagnostics,
)
from app.services.llm_gateway import LLMCallResult, LLMTaskRole
from app.services.revision_brief import build_revision_brief, scoped_revision_context
from app.services.script_generation_jobs import (
    FACTUAL_BLOCKING_CATEGORIES,
    FRAGMENTED_PLANNING_VERSION,
    ScriptGenerationJobService,
)


def _parent_structure() -> RoteiroEstrutura:
    global_issues = [
        {
            "section_key": "section-002",
            "category": "payoff",
            "severity": "revision_required",
            "actionable_feedback": "Entregue a análise visual concreta prometida.",
        },
        {
            "section_key": "section-003",
            "category": "redundancy",
            "severity": "revision_required",
            "actionable_feedback": "Remova a repetição da tese da abertura.",
        },
    ]
    return RoteiroEstrutura.model_validate(
        {
            "titulo": "O que o trailer realmente mostra",
            "duracao_total_segundos": 720,
            "blocos": [
                {
                    "tipo": "abertura",
                    "duracao_segundos": 240,
                    "conteudo": "ABERTURA_CONCRETA " + "fala " * 399,
                    "purpose": "Apresentar a pergunta central.",
                },
                {
                    "tipo": "análise visual",
                    "duracao_segundos": 240,
                    "conteudo": "SECAO_VISUAL_GENERICA " + "fala " * 314,
                    "purpose": "Analisar as cenas prometidas.",
                },
                {
                    "tipo": "conclusão",
                    "duracao_segundos": 240,
                    "conteudo": "CONCLUSAO_REPETITIVA " + "fala " * 433,
                    "purpose": "Resolver a promessa de abertura.",
                },
            ],
            "duration_contract": {
                "target_duration_seconds": 720,
                "predicted_duration_seconds": 490,
                "ratio": 0.6806,
                "status": "far_below_target",
                "revision_required": True,
                "target_words": 1740,
                "speakable_words": 1149,
                "sections": [
                    {
                        "index": 0,
                        "type": "abertura",
                        "target_duration_seconds": 240,
                        "predicted_duration_seconds": 166,
                        "target_words": 580,
                        "actual_words": 400,
                        "ratio": 0.6917,
                        "status": "far_below_target",
                    },
                    {
                        "index": 1,
                        "type": "análise visual",
                        "target_duration_seconds": 240,
                        "predicted_duration_seconds": 130,
                        "target_words": 580,
                        "actual_words": 315,
                        "ratio": 0.5417,
                        "status": "far_below_target",
                    },
                    {
                        "index": 2,
                        "type": "conclusão",
                        "target_duration_seconds": 240,
                        "predicted_duration_seconds": 194,
                        "target_words": 580,
                        "actual_words": 434,
                        "ratio": 0.8083,
                        "status": "below_target",
                    },
                ],
            },
            "editorial_review": {
                "audit_status": "completed",
                "editorial_status": "needs_revision",
                "factuality_status": "pass",
                "global_summary": "Boa base factual, mas faltam concretude e payoff.",
                "global_issues": global_issues,
                "section_issues": {},
            },
            "section_audits": {
                "section-001": {
                    "revision_required": False,
                    "issues": [],
                    "actual_summary": "Abertura forte e factual.",
                },
                "section-002": {
                    "revision_required": True,
                    "issues": [
                        {
                            "section_key": "section-002",
                            "category": "spoken_language",
                            "severity": "revision_required",
                            "actionable_feedback": "Troque abstrações por observações apoiadas.",
                        }
                    ],
                    "actual_summary": "A análise permaneceu genérica.",
                },
                "section-003": {
                    "revision_required": True,
                    "issues": [global_issues[1]],
                    "actual_summary": "A conclusão repetiu a abertura.",
                },
            },
            "global_critic": {
                "summary": "Boa base factual, mas faltam concretude e payoff.",
                "issues": global_issues,
            },
            "evidence_provenance": {
                "version": "evidence_dossier_v3",
                "claim_ledger_version": "canonical_claim_ledger_v1",
                "generation_run_id": "parent-run-id",
                "sources": [
                    {
                        "source_id": "source-official",
                        "title": "Material oficial",
                        "url": "https://example.com/official",
                        "source_trust": "official_primary",
                    }
                ],
                "claim_ledger": [
                    {
                        "id": "claim-scene",
                        "summary": "O material mostra uma cena delimitada.",
                        "source_refs": ["source-official"],
                        "source_trust": "official_primary",
                        "claim_status": "official_observation",
                    }
                ],
            },
            "prompt_trace": {"strategy_identity": "parent-strategy"},
            "generation_run_id": "parent-run-id",
        }
    )


def _brief(feedback: str | None = None) -> dict:
    structure = _parent_structure()
    return build_revision_brief(
        parent_roteiro_id=uuid4(),
        parent_version=1,
        parent_revision_kind="staged_generation",
        structure=structure,
        human_feedback=feedback,
        evidence_provenance=structure.evidence_provenance or {},
        factual_issue_categories=FACTUAL_BLOCKING_CATEGORIES,
    ).to_dict()


def _result(content: str, role: LLMTaskRole) -> LLMCallResult:
    return LLMCallResult(
        content=content,
        task_role=role.value,
        model_alias="test-route",
        actual_model="test/model",
        provider="test",
        prompt_identity="prompt",
        temperature=0.5,
        max_tokens=5000,
        prompt_tokens=100,
        completion_tokens=300,
        total_tokens=400,
        latency_seconds=0.01,
        attempt_count=1,
        finish_reason="stop",
    )


def _passing_audit() -> SectionEditorialAuditOutput:
    return SectionEditorialAuditOutput(
        revision_required=False,
        issues=[],
        actual_claim_refs=[],
        actual_beats_covered=["Avançar o argumento"],
        actual_summary="A seção avançou o argumento.",
        opened_loops=[],
        closed_loops=[],
        claim_language_assessments=[],
    )


def test_duration_revision_diagnostics_exposes_exact_total_and_section_deficits() -> (
    None
):
    diagnostics = revision_duration_diagnostics(_parent_structure().duration_contract)

    assert diagnostics["target_words"] == 1740
    assert diagnostics["actual_words"] == 1149
    assert diagnostics["word_deficit"] == 591
    assert diagnostics["status"] == "far_below_target"
    assert [item["word_deficit"] for item in diagnostics["sections"]] == [
        180,
        265,
        146,
    ]


def test_revision_brief_combines_parent_text_editorial_audits_and_human_feedback() -> (
    None
):
    brief = _brief(
        " Preserve a introdução. Torne a seção 2 concreta e evite meta-comentário. "
    )

    assert brief["version"] == "script_revision_brief_v1"
    assert len(brief["identity"]) == 64
    assert brief["human_feedback"].startswith("Preserve a introdução")
    assert brief["parent"]["title"] == "O que o trailer realmente mostra"
    assert brief["parent"]["strategy_identity"] == "parent-strategy"
    assert "ABERTURA_CONCRETA" in brief["parent"]["blocks"][0]["current_content"]
    assert brief["editorial"]["global_summary"].startswith("Boa base factual")
    assert [item["category"] for item in brief["editorial"]["global_issues"]] == [
        "payoff",
        "redundancy",
    ]
    assert brief["sections"][0]["review_state"] == "clean"
    assert brief["sections"][1]["review_state"] == "needs_review"
    assert brief["sections"][1]["audit_issues"][0]["category"] == "spoken_language"
    assert brief["evidence_reuse"]["claim_count"] == 1
    assert brief["evidence_reuse"]["source_count"] == 1
    assert [item["rank"] for item in brief["revision_priorities"]] == sorted(
        item["rank"] for item in brief["revision_priorities"]
    )
    critic_priority = next(
        item for item in brief["revision_priorities"] if item["category"] == "payoff"
    )
    assert critic_priority["diagnostic_only"] is True
    assert critic_priority["source"] == "global_critic"


def test_revision_priorities_keep_factual_boundaries_above_human_direction() -> None:
    structure = _parent_structure()
    payload = structure.model_dump(mode="json")
    payload["editorial_review"]["factuality_status"] = "blocking"
    payload["editorial_review"]["global_issues"].insert(
        0,
        {
            "section_key": "section-002",
            "category": "unsupported_claim",
            "severity": "blocking",
            "actionable_feedback": "Remova a afirmação sem claim aprovado.",
        },
    )
    structure = RoteiroEstrutura.model_validate(payload)

    brief = build_revision_brief(
        parent_roteiro_id=uuid4(),
        parent_version=1,
        parent_revision_kind="staged_generation",
        structure=structure,
        human_feedback="Mantenha todos os detalhes.",
        evidence_provenance=structure.evidence_provenance or {},
        factual_issue_categories=FACTUAL_BLOCKING_CATEGORIES,
    ).to_dict()

    assert brief["revision_priorities"][0]["category"] == "unsupported_claim"
    assert brief["revision_priorities"][0]["rank"] == 1
    human = next(
        item
        for item in brief["revision_priorities"]
        if item["category"] == "human_editorial_direction"
    )
    assert human["rank"] == 2


def test_prompt_projection_keeps_diagnostics_once_and_durable_brief_unchanged() -> None:
    feedback = "Preserve a introdução e torne a análise concreta."
    brief = _brief(feedback)

    prompt_context = scoped_revision_context(brief, section_keys={"section-002"})

    assert prompt_context is not None
    assert prompt_context["human_feedback"] == feedback
    assert "global_issues" not in prompt_context["editorial"]
    assert "audit_issues" not in prompt_context["sections"][0]
    assert "duration" not in prompt_context["sections"][0]
    assert all(
        item["source"]
        not in {"human_feedback", "duration_contract", "revision_semantics"}
        for item in prompt_context["revision_priorities"]
    )
    assert all(
        not item.get("section_key") or item["section_key"] == "section-002"
        for item in prompt_context["revision_priorities"]
    )
    assert len(prompt_context["parent"]["blocks"]) == 1
    # Full diagnostics remain on the durable provenance object.
    assert brief["editorial"]["global_issues"]
    assert any(
        item["source"] == "human_feedback" for item in brief["revision_priorities"]
    )


@pytest.mark.asyncio
async def test_enqueue_revision_without_human_feedback_persists_diagnostics_and_evidence() -> (
    None
):
    structure = _parent_structure()
    source = SimpleNamespace(
        id=uuid4(),
        ideia_id=uuid4(),
        versao=1,
        revision_kind="staged_generation",
        estrutura=structure.model_dump(mode="json"),
        ideia=SimpleNamespace(perfil_producao="faceless_general"),
    )
    repository = AsyncMock()
    repository.get_by_id.return_value = source
    repository.get_latest_version_by_ideia.return_value = source
    expected_run = SimpleNamespace(id=uuid4())
    service = ScriptGenerationJobService(AsyncMock(), config=Settings())
    service.enqueue = AsyncMock(return_value=expected_run)  # type: ignore[method-assign]

    with (
        patch(
            "app.services.script_generation_jobs.RoteiroRepository",
            return_value=repository,
        ),
        patch(
            "app.services.script_generation_jobs.IdeiaRepository.get_by_id",
            AsyncMock(return_value=source.ideia),
        ),
    ):
        result = await service.enqueue_revision(
            source.id,
            idempotency_key="diagnostics-only-revision",
            feedback="   ",
        )

    assert result is expected_run
    kwargs = service.enqueue.await_args.kwargs
    assert kwargs["generation_intent"] == "revision"
    assert kwargs["parent_roteiro_id"] == source.id
    assert kwargs["revision_feedback"] is None
    assert kwargs["revision_brief_override"]["human_feedback"] is None
    assert kwargs["revision_brief_override"]["duration"]["word_deficit"] == 591
    dossier = kwargs["evidence_dossier_override"]
    assert dossier["research_complete"] is True
    assert dossier["claims"] == structure.evidence_provenance["claim_ledger"]
    assert dossier["sources"] == structure.evidence_provenance["sources"]
    assert dossier["revision_source"]["content_identity"]


@pytest.mark.asyncio
async def test_revision_with_reusable_provenance_skips_fresh_research() -> None:
    run = SimpleNamespace(
        id=uuid4(),
        status="running",
        phase="planning",
        generation_intent="revision",
        evidence_dossier={"research_complete": True},
        plan={
            "planning_state": {
                "version": FRAGMENTED_PLANNING_VERSION,
                "status": "completed",
            },
            "editorial": {},
        },
        sections=[],
        completed_sections=0,
        roteiro_id=None,
        completed_at=None,
    )
    service = ScriptGenerationJobService(AsyncMock(), config=Settings())
    service.get = AsyncMock(return_value=run)  # type: ignore[method-assign]
    service._build_evidence_dossier = AsyncMock()  # type: ignore[method-assign]
    service._build_external_evidence_dossier = AsyncMock()  # type: ignore[method-assign]
    service._plan = AsyncMock()  # type: ignore[method-assign]
    service._assemble = AsyncMock()  # type: ignore[method-assign]

    result = await service.process(run.id)

    assert result.status == "completed"
    service._build_evidence_dossier.assert_not_awaited()
    service._build_external_evidence_dossier.assert_not_awaited()
    service._plan.assert_not_awaited()
    service._assemble.assert_awaited_once_with(run)


@pytest.mark.asyncio
async def test_section_planner_receives_scoped_parent_diagnostics() -> None:
    brief = _brief()
    budget = {
        "key": "section-002",
        "order": 1,
        "chapter_order": 0,
        "target_duration_seconds": 240,
        "target_words": 580,
        "min_words": 493,
        "max_words": 667,
    }
    row = SimpleNamespace(
        section_key="section-002",
        section_plan={**budget, "planning_status": "pending"},
        prompt_provenance=None,
        status="planning",
    )
    run = SimpleNamespace(
        id=uuid4(),
        production_profile="faceless_general",
        evidence_dossier={"sources": [], "fragments": []},
        plan={
            "revision_brief": brief,
            "planning_state": {
                "version": FRAGMENTED_PLANNING_VERSION,
                "coverage_failures": [],
            },
        },
        revision_feedback=None,
        heartbeat_at=None,
    )
    output = {
        "sections": [
            {
                "key": "section-002",
                "title": "Análise visual concreta",
                "purpose": "Entregar a análise prometida.",
                "narrative_role": "desenvolvimento",
                "beat_contracts": [
                    {
                        "editorial_goal": "Avançar o argumento",
                        "kind": "editorial",
                        "claim_refs": [],
                        "required": True,
                    }
                ],
                "must_not_repeat": [],
                "transition_target": None,
            }
        ]
    }
    service = ScriptGenerationJobService(AsyncMock(), config=Settings())
    service._planning_rows = AsyncMock(return_value=[row])  # type: ignore[method-assign]
    service._complete = AsyncMock(  # type: ignore[method-assign]
        return_value=_result(json.dumps(output), LLMTaskRole.PLANNING)
    )
    global_output = GlobalEditorialPlanOutput(
        thesis="Tese",
        audience_promise="Entregar análise visual.",
        chapters=[
            {
                "key": "chapter-001",
                "title": "Capítulo",
                "purpose": "Progredir",
            }
        ],
        open_loops=[],
    )

    await service._plan_section_batch(
        run,
        idea=SimpleNamespace(
            titulo="Ideia", descricao_breve="Descrição", author_briefing=None
        ),
        budgets=[budget],
        global_output=global_output,
        claim_ledger=[],
        evidence_index=[],
        niche_prompt=None,
        planning_version=FRAGMENTED_PLANNING_VERSION,
    )

    prompt = service._complete.await_args.kwargs["prompt"]
    trace = service._complete.await_args.kwargs["prompt_trace"]
    assert "REVISION MODE" in prompt
    assert "SECAO_VISUAL_GENERICA" in prompt
    assert "ABERTURA_CONCRETA" not in prompt
    assert 'word_deficit": 265' in prompt
    assert "structured_revision_brief" in trace["components"]
    assert trace["revision_brief_identity"] == brief["identity"]


@pytest.mark.asyncio
async def test_revision_writer_receives_parent_text_priorities_and_exact_deficit() -> (
    None
):
    section = SimpleNamespace(
        section_key="section-002",
        section_order=1,
        status="pending",
        attempt_count=0,
        section_plan={
            "key": "section-002",
            "order": 1,
            "chapter_order": 0,
            "target_duration_seconds": 60,
            "target_words": 100,
            "min_words": 85,
            "max_words": 115,
            "title": "Análise",
            "purpose": "Entregar o payoff.",
            "narrative_role": "desenvolvimento",
            "beats": ["Avançar o argumento"],
            "evidence_refs": [],
            "claim_refs": [],
            "must_cover": ["Avançar o argumento"],
            "must_not_repeat": [],
            "transition_target": None,
        },
        output=None,
        local_validation=None,
        prompt_provenance={},
        output_identity=None,
        error_category=None,
        error_message=None,
        review_state=None,
    )
    brief = _brief("Preserve a abertura.")
    run = SimpleNamespace(
        id=uuid4(),
        ideia_id=uuid4(),
        production_profile="faceless_general",
        sections=[section],
        plan={
            "revision_brief": brief,
            "editorial": {
                "thesis": "Tese",
                "audience_promise": "Entregar análise visual.",
                "open_loops": [],
                "claim_ledger": [],
            },
        },
        evidence_dossier={"fragments": []},
        continuity_state={"introduced_claims": [], "completed_sections": []},
        model_policy={"strategy": "standard"},
        revision_feedback="Preserve a abertura.",
        heartbeat_at=None,
    )
    service = ScriptGenerationJobService(AsyncMock(), config=Settings())
    service._editorial_context = AsyncMock(  # type: ignore[method-assign]
        return_value=(
            SimpleNamespace(author_briefing=None),
            None,
            get_profile("faceless_general"),
        )
    )
    service._complete = AsyncMock(  # type: ignore[method-assign]
        return_value=_result(
            json.dumps(
                {
                    "content": "inicio "
                    + " ".join("fala" for _ in range(98))
                    + " fim",
                    "visual_queries": [
                        {
                            "intent": "illustration",
                            "query": "footage para a abertura",
                            "narration_excerpt": "inicio",
                            "importance": "preferred",
                            "source_note_id": None,
                        },
                        {
                            "intent": "illustration",
                            "query": "footage para o fechamento",
                            "narration_excerpt": "fim",
                            "importance": "preferred",
                            "source_note_id": None,
                        },
                    ],
                }
            ),
            LLMTaskRole.WRITING,
        )
    )
    service._audit_section = AsyncMock(  # type: ignore[method-assign]
        return_value=(_passing_audit(), {"audit": "test"})
    )

    await service._write_section(run, section)

    prompt = service._complete.await_args.kwargs["prompt"]
    system_prompt = service._complete.await_args.kwargs["system_prompt"]
    assert "SECAO_VISUAL_GENERICA" in prompt
    assert "ABERTURA_CONCRETA" not in prompt
    assert 'word_deficit": 265' in prompt
    assert "Preserve a abertura." in prompt
    assert "detalhe ou cena concreta" in system_prompt
    assert "disciplina epistêmica quase invisível" in system_prompt
    assert "resolva a promessa de abertura" in system_prompt


def test_prompt_without_revision_brief_keeps_initial_generation_semantics() -> None:
    prompt = compose_editorial_v3_prompt(
        phase="writing",
        profile=get_profile("faceless_general"),
        task_prompt="Escreva a seção inicial.",
    )

    assert "REVISION MODE" not in prompt.user
    assert "structured_revision_brief" not in prompt.trace["components"]


@pytest.mark.asyncio
async def test_revision_assembly_persists_linked_v2_despite_editorial_and_duration_miss() -> (
    None
):
    parent_id = uuid4()
    run_id = uuid4()
    issue = EditorialCriticIssue(
        section_key="section-001",
        category="payoff",
        severity="revision_required",
        actionable_feedback="Resolva a promessa de abertura.",
    )
    critic = EditorialCriticOutput(
        summary="Ainda precisa de payoff.",
        issues=[issue],
        open_loops_closed=False,
        unsupported_claims_detected=False,
    )
    section = SimpleNamespace(
        section_key="section-001",
        section_order=0,
        chapter_order=0,
        review_state="needs_review",
        section_plan={
            "title": "Seção",
            "purpose": "Desenvolver",
            "target_duration_seconds": 720,
            "beats": ["Avançar"],
            "evidence_refs": ["source-official"],
        },
        local_validation={"status": "under_budget"},
        output={
            "content": " ".join("fala" for _ in range(120)),
            "claims_used": ["claim-scene"],
            "beats_covered": ["Avançar"],
            "section_audit": {"issues": []},
            "visual_intent": None,
            "audio_intent": None,
        },
    )
    run = SimpleNamespace(
        id=run_id,
        ideia_id=uuid4(),
        parent_roteiro_id=parent_id,
        generation_intent="revision",
        revision_feedback=None,
        production_profile="faceless_general",
        generation_strategy="staged",
        strategy_identity="strategy",
        duration_mode="profile_default",
        duration_target_source="profile",
        target_duration_seconds=720,
        model_policy={},
        call_usage={},
        sections=[section],
        plan={
            "revision_brief": {
                "identity": "brief-identity",
                "parent": {"generation_run_id": "source-generation-run"},
            },
            "editorial": {
                "thesis": "Tese",
                "audience_promise": "Promessa",
                "open_loops": [],
                "claim_ledger": [
                    {
                        "id": "claim-scene",
                        "summary": "Cena observada.",
                        "source_refs": ["source-official"],
                    }
                ],
            },
        },
        evidence_dossier={
            "version": "evidence_dossier_v3",
            "claim_ledger_version": "canonical_claim_ledger_v1",
            "sources": [
                {
                    "source_id": "source-official",
                    "title": "Oficial",
                    "url": "https://example.com/official",
                    "source_trust": "official_primary",
                }
            ],
        },
        phase="writing",
        roteiro_id=None,
    )
    idea = SimpleNamespace(titulo="Título", id=run.ideia_id)
    service = ScriptGenerationJobService(AsyncMock(), config=Settings())
    service._run_global_critic = AsyncMock(return_value=critic)  # type: ignore[method-assign]
    persisted = SimpleNamespace(id=uuid4())

    with (
        patch(
            "app.services.script_generation_jobs.IdeiaRepository",
            return_value=SimpleNamespace(get_by_id=AsyncMock(return_value=idea)),
        ),
        patch(
            "app.services.script_generation_jobs.duration_calibration_client.get",
            AsyncMock(
                return_value=DurationCalibration.fallback_for(
                    production_profile="faceless_general"
                )
            ),
        ),
        patch(
            "app.services.roteiros.gerador_roteiro.RoteiroGenerator._persist_revision",
            AsyncMock(return_value=persisted),
        ) as persist_revision,
    ):
        await service._assemble(run)

    kwargs = persist_revision.await_args.kwargs
    assert kwargs["revision_kind"] == "llm_regeneration"
    assert kwargs["parent_roteiro_id"] == parent_id
    assert kwargs["revision_feedback"] is None
    assert kwargs["estrutura"].duration_contract["revision_required"] is True
    assert kwargs["estrutura"].editorial_review["editorial_status"] == "needs_revision"
    assert (
        kwargs["estrutura"].evidence_provenance["claim_ledger"][0]["id"]
        == "claim-scene"
    )
    assert (
        kwargs["estrutura"].evidence_provenance["source_generation_run_id"]
        == "source-generation-run"
    )
    assert (
        kwargs["estrutura"].evidence_provenance["revision_brief_identity"]
        == "brief-identity"
    )
    assert kwargs["estrutura"].generation_run_id == str(run_id)
    assert kwargs["estrutura"].prompt_trace["generation_intent"] == "revision"
    assert kwargs["estrutura"].prompt_trace["parent_roteiro_id"] == str(parent_id)
    assert run.plan["duration_contract_warning"]["actual_words"] == 120
    assert run.plan["duration_contract_warning"]["word_deficit"] > 0
    assert run.roteiro_id == persisted.id
