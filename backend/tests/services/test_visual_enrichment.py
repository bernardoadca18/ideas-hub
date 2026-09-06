"""Tests for visual enrichment LLM integration."""
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.schemas.llm_outputs import (
    LLMVisualQuery,
    VisualEnrichmentOutput,
    VisualEnrichmentSectionOutput,
    VisualQueryImportance,
    VisualQueryIntent,
)
from app.schemas.roteiro import RoteiroEstrutura
from app.services.roteiros.gerador_roteiro import RoteiroGenerator


def _make_manual_roteiro():
    """Create a manual roteiro with structure but no visual queries."""
    return SimpleNamespace(
        id=uuid4(),
        ideia_id=uuid4(),
        status="rascunho",
        revision_kind="manual_create",
        estrutura={
            "production_script_schema_version": "2.0",
            "titulo": "Manual Script",
            "duracao_total_segundos": 120,
            "blocos": [
                {
                    "tipo": "introducao",
                    "duracao_segundos": 30,
                    "conteudo": "Este é o texto de introdução do vídeo manual.",
                    "dicas_visual": "Imagens de abertura",
                },
                {
                    "tipo": "desenvolvimento",
                    "duracao_segundos": 60,
                    "conteudo": "Este é o desenvolvimento principal com mais conteúdo detalhado sobre o assunto.",
                    "dicas_visual": "B-roll do tema",
                },
                {
                    "tipo": "conclusao",
                    "duracao_segundos": 30,
                    "conteudo": "Conclusão final do vídeo com recapitulação dos pontos principais.",
                    "dicas_visual": "Imagens de fechamento",
                },
            ],
            "tags": ["manual", "teste"],
            "visual_queries": None,  # No visual queries yet
        },
    )


def _make_llm_visual_enrichment_output():
    """Create a valid LLM output for visual enrichment."""
    return VisualEnrichmentOutput(
        sections=[
            VisualEnrichmentSectionOutput(
                key="block-000",
                visual_queries=[
                    LLMVisualQuery(
                        intent=VisualQueryIntent.illustration,
                        query="Imagens de abertura relacionadas ao tema",
                        narration_excerpt="Este é o texto de introdução",
                        importance=VisualQueryImportance.preferred,
                        source_note_id=None,
                        desired_duration_seconds=10.0,
                    )
                ],
            ),
            VisualEnrichmentSectionOutput(
                key="block-001",
                visual_queries=[
                    LLMVisualQuery(
                        intent=VisualQueryIntent.evidence,
                        query="B-roll demonstrando o conceito principal",
                        narration_excerpt="Este é o desenvolvimento principal",
                        importance=VisualQueryImportance.required,
                        source_note_id=None,
                        desired_duration_seconds=20.0,
                    )
                ],
            ),
            VisualEnrichmentSectionOutput(
                key="block-002",
                visual_queries=[
                    LLMVisualQuery(
                        intent=VisualQueryIntent.atmosphere,
                        query="Imagens de encerramento suaves",
                        narration_excerpt="Conclusão final do vídeo",
                        importance=VisualQueryImportance.optional,
                        source_note_id=None,
                        desired_duration_seconds=8.0,
                    )
                ],
            ),
        ]
    )


@pytest.mark.asyncio
async def test_visual_enrichment_calls_llm_with_correct_workflow() -> None:
    """Test that visual enrichment calls LLM with VISUAL_ENRICHMENT workflow."""
    generator = RoteiroGenerator(AsyncMock())
    manual_roteiro = _make_manual_roteiro()

    generator.roteiro_repo = AsyncMock()
    generator.roteiro_repo.get_by_id.return_value = manual_roteiro

    # Setup ideia and profile
    ideia = SimpleNamespace(
        id=manual_roteiro.ideia_id,
        titulo="Test Ideia",
        descricao_breve="Teste de visual enrichment",
        nicho_id=None,
    )
    generator.ideia_repo = AsyncMock()
    generator.ideia_repo.get_by_id.return_value = ideia

    # Mock LLM response
    llm_output = _make_llm_visual_enrichment_output()

    with (
        patch(
            "app.services.llm_gateway.llm_gateway.complete",
            AsyncMock(return_value=MagicMock(content=llm_output.model_dump_json())),
        ) as llm_complete,
        patch(
            "app.services.visual_requirements.materialize_written_visual_queries"
        ) as materialize,
    ):
        materialize.return_value = []  # Empty list of materialized queries

        # Mock persist_revision
        generator._persist_revision = AsyncMock(
            return_value=SimpleNamespace(id=uuid4())
        )

        await generator.create_visual_enrichment_revision(manual_roteiro.id)

        # Verify LLM was called with correct schema
        llm_complete.assert_awaited_once()
        call_kwargs = llm_complete.await_args.kwargs
        assert call_kwargs["temperature"] == 0.3
        assert call_kwargs["max_tokens"] == 4000
        assert "response_schema" in call_kwargs
        assert call_kwargs["response_schema"]["title"] == "VisualEnrichmentOutput"


@pytest.mark.asyncio
async def test_visual_enrichment_uses_index_based_section_keys() -> None:
    """Test that visual enrichment uses index-based keys (block-000, block-001, etc.)."""
    generator = RoteiroGenerator(AsyncMock())
    manual_roteiro = _make_manual_roteiro()

    generator.roteiro_repo = AsyncMock()
    generator.roteiro_repo.get_by_id.return_value = manual_roteiro

    ideia = SimpleNamespace(
        id=manual_roteiro.ideia_id,
        titulo="Test Ideia",
        descricao_breve="Teste",
        nicho_id=None,
    )
    generator.ideia_repo = AsyncMock()
    generator.ideia_repo.get_by_id.return_value = ideia

    llm_output = _make_llm_visual_enrichment_output()

    materialized_calls = []

    def capture_materialize(*args, **kwargs):
        materialized_calls.append((args, kwargs))
        return []

    with (
        patch(
            "app.services.llm_gateway.llm_gateway.complete",
            AsyncMock(return_value=MagicMock(content=llm_output.model_dump_json())),
        ),
        patch(
            "app.services.visual_requirements.materialize_written_visual_queries",
            side_effect=capture_materialize,
        ),
    ):
        generator._persist_revision = AsyncMock(
            return_value=SimpleNamespace(id=uuid4())
        )

        await generator.create_visual_enrichment_revision(manual_roteiro.id)

        # Verify section_key format
        section_keys = [call[1]["section_key"] for call in materialized_calls]
        assert section_keys == ["block-000", "block-001", "block-002"]


@pytest.mark.asyncio
async def test_visual_enrichment_rejects_non_manual_roteiro() -> None:
    """Test that visual enrichment rejects roteiros that are not manual lineage."""
    generator = RoteiroGenerator(AsyncMock())

    # Create a non-manual roteiro (llm_generation is not manual lineage)
    non_manual = SimpleNamespace(
        id=uuid4(),
        status="rascunho",
        revision_kind="llm_generation",  # Not manual_create or human_edit
        estrutura={"titulo": "Gerado"},
    )

    generator.roteiro_repo = AsyncMock()
    generator.roteiro_repo.get_by_id.return_value = non_manual

    with pytest.raises(ValueError, match="Visual enrichment only for manual scripts"):
        await generator.create_visual_enrichment_revision(non_manual.id)


@pytest.mark.asyncio
async def test_visual_enrichment_accepts_human_edit_roteiro() -> None:
    """Test that visual enrichment accepts human_edit scripts (manual lineage)."""
    generator = RoteiroGenerator(AsyncMock())

    # Create a human_edit roteiro (manual lineage)
    human_edited = SimpleNamespace(
        id=uuid4(),
        ideia_id=uuid4(),
        status="rascunho",
        revision_kind="human_edit",  # Manual lineage
        estrutura={
            "production_script_schema_version": "2.0",
            "titulo": "Human Edited Script",
            "duracao_total_segundos": 60,
            "blocos": [
                {
                    "tipo": "introducao",
                    "duracao_segundos": 60,
                    "conteudo": "Conteúdo editado manualmente",
                    "dicas_visual": "Imagens",
                }
            ],
            "tags": [],
            "visual_queries": None,  # No visual queries yet
        },
    )

    generator.roteiro_repo = AsyncMock()
    generator.roteiro_repo.get_by_id.return_value = human_edited

    ideia = SimpleNamespace(
        id=human_edited.ideia_id,
        titulo="Test",
        descricao_breve="Test",
        nicho_id=None,
    )
    generator.ideia_repo = AsyncMock()
    generator.ideia_repo.get_by_id.return_value = ideia

    llm_output = VisualEnrichmentOutput(
        sections=[
            VisualEnrichmentSectionOutput(
                key="block-000",
                visual_queries=[],
            )
        ]
    )

    with (
        patch(
            "app.services.llm_gateway.llm_gateway.complete",
            AsyncMock(return_value=MagicMock(content=llm_output.model_dump_json())),
        ),
        patch(
            "app.services.visual_requirements.materialize_written_visual_queries"
        ) as materialize,
    ):
        materialize.return_value = []
        generator._persist_revision = AsyncMock(
            return_value=SimpleNamespace(id=uuid4())
        )

        # Should NOT raise - human_edit is manual lineage
        await generator.create_visual_enrichment_revision(human_edited.id)


@pytest.mark.asyncio
async def test_visual_enrichment_rejects_already_enriched() -> None:
    """Test that visual enrichment rejects scripts that already have visual queries."""
    generator = RoteiroGenerator(AsyncMock())

    # Create a roteiro that already has visual queries
    already_enriched = SimpleNamespace(
        id=uuid4(),
        status="rascunho",
        revision_kind="manual_create",
        estrutura={
            "production_script_schema_version": "2.0",
            "titulo": "Already Enriched",
            "duracao_total_segundos": 120,
            "blocos": [
                {
                    "tipo": "introducao",
                    "duracao_segundos": 120,
                    "conteudo": "Conteúdo",
                    "dicas_visual": "Imagens",
                    "visual_queries": [{"intent": "illustration", "query": "test"}],
                }
            ],
            "tags": [],
        },
    )

    generator.roteiro_repo = AsyncMock()
    generator.roteiro_repo.get_by_id.return_value = already_enriched

    with pytest.raises(ValueError, match="Script already has visual queries"):
        await generator.create_visual_enrichment_revision(already_enriched.id)


@pytest.mark.asyncio
async def test_visual_enrichment_preserves_block_content() -> None:
    """Test that visual enrichment passes original block content to materialization."""
    generator = RoteiroGenerator(AsyncMock())
    manual_roteiro = _make_manual_roteiro()

    generator.roteiro_repo = AsyncMock()
    generator.roteiro_repo.get_by_id.return_value = manual_roteiro

    ideia = SimpleNamespace(
        id=manual_roteiro.ideia_id,
        titulo="Test",
        descricao_breve="Test",
        nicho_id=None,
    )
    generator.ideia_repo = AsyncMock()
    generator.ideia_repo.get_by_id.return_value = ideia

    llm_output = _make_llm_visual_enrichment_output()

    materialized_calls = []

    def capture_materialize(*args, **kwargs):
        materialized_calls.append((args, kwargs))
        return []

    with (
        patch(
            "app.services.llm_gateway.llm_gateway.complete",
            AsyncMock(return_value=MagicMock(content=llm_output.model_dump_json())),
        ),
        patch(
            "app.services.visual_requirements.materialize_written_visual_queries",
            side_effect=capture_materialize,
        ),
    ):
        generator._persist_revision = AsyncMock(
            return_value=SimpleNamespace(id=uuid4())
        )

        await generator.create_visual_enrichment_revision(manual_roteiro.id)

        # Verify content is passed correctly
        contents = [call[1]["content"] for call in materialized_calls]
        assert "introdução" in contents[0]
        assert "desenvolvimento" in contents[1]
        assert "Conclusão" in contents[2]


@pytest.mark.asyncio
async def test_visual_enrichment_integration_with_real_materializer() -> None:
    """Integration test: visual enrichment with real materializer (not mocked).

    This test verifies the full pipeline:
    1. LLM generates visual queries
    2. Real materialize_written_visual_queries creates VisualQuery objects
    3. Stable UUID5 identities are assigned
    4. Provenance is correctly bound
    """
    from uuid import uuid5, NAMESPACE_URL

    from app.schemas.visual_query import VisualQuery
    from app.services.visual_requirements import materialize_written_visual_queries

    generator = RoteiroGenerator(AsyncMock())

    # Create a manual roteiro with SHORT blocks (≤30s = 1 query minimum)
    # This allows us to test with exactly 1 query per block
    manual_roteiro = SimpleNamespace(
        id=uuid4(),
        ideia_id=uuid4(),
        status="rascunho",
        revision_kind="manual_create",
        estrutura={
            "production_script_schema_version": "2.0",
            "titulo": "Manual Script for Real Materializer",
            "duracao_total_segundos": 75,
            "blocos": [
                {
                    "tipo": "introducao",
                    "duracao_segundos": 25,  # 25s = 1 query minimum
                    "conteudo": "Este é o texto de introdução do vídeo manual. Segunda frase para contexto.",
                    "dicas_visual": "Imagens de abertura",
                },
                {
                    "tipo": "desenvolvimento",
                    "duracao_segundos": 25,  # 25s = 1 query minimum
                    "conteudo": "Este é o desenvolvimento principal com mais conteúdo. Adicionamos mais texto aqui.",
                    "dicas_visual": "B-roll do tema",
                },
                {
                    "tipo": "conclusao",
                    "duracao_segundos": 25,  # 25s = 1 query minimum
                    "conteudo": "Conclusão final do vídeo. Recapitulamos os principais pontos abordados.",
                    "dicas_visual": "Imagens de fechamento",
                },
            ],
            "tags": ["manual", "teste"],
            "visual_queries": None,
        },
    )

    generator.roteiro_repo = AsyncMock()
    generator.roteiro_repo.get_by_id.return_value = manual_roteiro

    ideia = SimpleNamespace(
        id=manual_roteiro.ideia_id,
        titulo="Integration Test",
        descricao_breve="Real materializer test",
        nicho_id=None,
    )
    generator.ideia_repo = AsyncMock()
    generator.ideia_repo.get_by_id.return_value = ideia

    # For 25s blocks, minimum is 1 query, max is 5
    # We use 2 queries per block to satisfy the policy (1-5 queries for ≤30s)
    # NOTE: Manual scripts don't have media context, so source_note_id must be None
    # IMPORTANT: narration_excerpt must be LITERAL spans from the content IN ORDER
    # Block 0 content: "Este é o texto de introdução do vídeo manual. Segunda frase para contexto."
    # Block 1 content: "Este é o desenvolvimento principal com mais conteúdo. Adicionamos mais texto aqui."
    # Block 2 content: "Conclusão final do vídeo. Recapitulamos os principais pontos abordados."
    llm_output = VisualEnrichmentOutput(
        sections=[
            VisualEnrichmentSectionOutput(
                key="block-000",
                visual_queries=[
                    LLMVisualQuery(
                        intent=VisualQueryIntent.illustration,
                        query="Imagens de abertura do tema",
                        narration_excerpt="Este é o texto de introdução",  # Start of content
                        importance=VisualQueryImportance.preferred,
                        source_note_id=None,
                        desired_duration_seconds=10.0,
                    ),
                    LLMVisualQuery(
                        intent=VisualQueryIntent.atmosphere,
                        query="Ambiente de abertura",
                        narration_excerpt="Segunda frase para contexto",  # End of content (after first)
                        importance=VisualQueryImportance.optional,
                        source_note_id=None,
                        desired_duration_seconds=8.0,
                    ),
                ],
            ),
            VisualEnrichmentSectionOutput(
                key="block-001",
                visual_queries=[
                    LLMVisualQuery(
                        intent=VisualQueryIntent.evidence,
                        query="Momento específico do desenvolvimento",
                        narration_excerpt="Este é o desenvolvimento principal",  # Start
                        importance=VisualQueryImportance.required,
                        source_note_id=None,
                        desired_duration_seconds=15.0,
                    ),
                    LLMVisualQuery(
                        intent=VisualQueryIntent.illustration,
                        query="B-roll complementar",
                        narration_excerpt="Adicionamos mais texto aqui",  # End (after first)
                        importance=VisualQueryImportance.preferred,
                        source_note_id=None,
                        desired_duration_seconds=10.0,
                    ),
                ],
            ),
            VisualEnrichmentSectionOutput(
                key="block-002",
                visual_queries=[
                    LLMVisualQuery(
                        intent=VisualQueryIntent.atmosphere,
                        query="Imagens de encerramento",
                        narration_excerpt="Conclusão final do vídeo",  # Start
                        importance=VisualQueryImportance.optional,
                        source_note_id=None,
                        desired_duration_seconds=8.0,
                    ),
                    LLMVisualQuery(
                        intent=VisualQueryIntent.transition,
                        query="Transição de fechamento",
                        narration_excerpt="Recapitulamos os principais pontos",  # End (after first)
                        importance=VisualQueryImportance.preferred,
                        source_note_id=None,
                        desired_duration_seconds=5.0,
                    ),
                ],
            ),
        ]
    )

    # Track materialized results for verification
    materialized_results: list[list[VisualQuery]] = []

    def capture_real_materialize(
        generation_run_id, section_key, duration_seconds, content, generated, evidence_dossier
    ):
        result = materialize_written_visual_queries(
            generation_run_id=generation_run_id,
            section_key=section_key,
            duration_seconds=duration_seconds,
            content=content,
            generated=generated,
            evidence_dossier=evidence_dossier,
        )
        materialized_results.append(result)
        return result

    with (
        patch(
            "app.services.llm_gateway.llm_gateway.complete",
            AsyncMock(return_value=MagicMock(content=llm_output.model_dump_json())),
        ),
        patch(
            "app.services.visual_requirements.materialize_written_visual_queries",
            side_effect=capture_real_materialize,
        ),
    ):
        generator._persist_revision = AsyncMock(
            return_value=SimpleNamespace(id=uuid4())
        )

        await generator.create_visual_enrichment_revision(manual_roteiro.id)

        # Verify real materialization occurred
        assert len(materialized_results) == 3  # One per block

        # The generation_run_id passed to materializer is the roteiro_id (source roteiro)
        roteiro_id_as_run_id = manual_roteiro.id

        # Block 0: 2 queries, first is illustration
        block_0_queries = materialized_results[0]
        assert len(block_0_queries) == 2
        assert block_0_queries[0].intent == "illustration"
        assert block_0_queries[0].importance == "preferred"
        assert block_0_queries[0].source_note_id is None
        assert block_0_queries[0].preferred_session_id is None
        # Verify stable UUID5 identity for first query
        expected_id_0_0 = uuid5(
            NAMESPACE_URL,
            f"neovids:visual-query:{roteiro_id_as_run_id}:block-000:0",
        )
        assert block_0_queries[0].id == expected_id_0_0
        # Second query is atmosphere
        assert block_0_queries[1].intent == "atmosphere"
        assert block_0_queries[1].importance == "optional"

        # Block 1: 2 queries, first is evidence (no source_note_id since manual scripts have no media context)
        block_1_queries = materialized_results[1]
        assert len(block_1_queries) == 2
        assert block_1_queries[0].intent == "evidence"
        assert block_1_queries[0].importance == "required"
        assert block_1_queries[0].source_note_id is None
        # No provenance filled since no evidence_dossier
        assert block_1_queries[0].preferred_session_id is None
        assert block_1_queries[0].preferred_start_seconds is None
        assert block_1_queries[0].preferred_end_seconds is None
        # Verify stable UUID5 identity
        expected_id_1_0 = uuid5(
            NAMESPACE_URL,
            f"neovids:visual-query:{roteiro_id_as_run_id}:block-001:0",
        )
        assert block_1_queries[0].id == expected_id_1_0

        # Block 2: 2 queries, first is atmosphere
        block_2_queries = materialized_results[2]
        assert len(block_2_queries) == 2
        assert block_2_queries[0].intent == "atmosphere"
        assert block_2_queries[0].importance == "optional"
        # Second query is transition
        assert block_2_queries[1].intent == "transition"
        assert block_2_queries[1].importance == "preferred"
