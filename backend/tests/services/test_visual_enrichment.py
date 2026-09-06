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
    """Test that visual enrichment rejects roteiros that are not manual."""
    generator = RoteiroGenerator(AsyncMock())

    # Create a non-manual roteiro
    non_manual = SimpleNamespace(
        id=uuid4(),
        status="rascunho",
        revision_kind="staged_generation",  # Not manual_create
        estrutura={"titulo": "Gerado"},
    )

    generator.roteiro_repo = AsyncMock()
    generator.roteiro_repo.get_by_id.return_value = non_manual

    with pytest.raises(ValueError, match="Visual enrichment only for manual scripts"):
        await generator.create_visual_enrichment_revision(non_manual.id)


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
