"""Visual-only revision tests for host-owned coverage beats."""

from __future__ import annotations

import json
import re
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.schemas.llm_outputs import LLMOutputError
from app.schemas.roteiro import RoteiroEstrutura
from app.services.roteiros.gerador_roteiro import RoteiroGenerator
from app.services.visual_requirements import (
    speakable_content_identity,
    validate_visual_readiness,
)


def _content(sentences: int) -> str:
    return " ".join(
        f"Sentença {index} contém uma ideia visual concreta e narração preservada."
        for index in range(sentences)
    )


def _source(*, revision_kind: str = "manual_create", duration: int = 60):
    return SimpleNamespace(
        id=uuid4(),
        ideia_id=uuid4(),
        status="aprovado",
        revision_kind=revision_kind,
        estrutura={
            "titulo": "Roteiro existente",
            "duracao_total_segundos": duration,
            "blocos": [
                {
                    "tipo": "desenvolvimento",
                    "duracao_segundos": duration,
                    "conteudo": _content(max(4, duration // 10)),
                    "dicas_visual": "gameplay urbano",
                    "visual_queries": [],
                }
            ],
            "tags": ["preservar"],
            "referencias": ["fonte"],
        },
    )


def _idea(source):
    return SimpleNamespace(
        id=source.ideia_id,
        titulo="Ideia",
        descricao_breve="Contexto",
        nicho_id=None,
        origem=None,
        author_briefing=None,
    )


def _response_for_request(*, fail_after: int | None = None):
    calls = 0

    async def complete(**kwargs):
        nonlocal calls
        calls += 1
        complete.requests.append(kwargs)
        if fail_after is not None and calls > fail_after:
            raise LLMOutputError("provider_failure", "falha controlada")
        prompt = kwargs["messages"][1]["content"]
        orders = [int(value) for value in re.findall(r'"beat_order":\s*(\d+)', prompt)]
        payload = {
            "visual_queries": [
                {
                    "beat_order": order,
                    "intent": "illustration",
                    "query": f"gameplay semântico para beat {order}",
                    "importance": "preferred",
                    "source_note_id": None,
                    "notes": None,
                }
                for order in orders
            ]
        }
        return MagicMock(content=json.dumps(payload))

    complete.call_count_value = lambda: calls
    complete.requests = []
    return complete


async def _generator(source):
    generator = RoteiroGenerator(AsyncMock())
    generator.roteiro_repo = AsyncMock()
    generator.roteiro_repo.get_by_id.return_value = source
    generator.ideia_repo = AsyncMock()
    generator.ideia_repo.get_by_id.return_value = _idea(source)
    generator._persist_revision = AsyncMock(return_value=SimpleNamespace(id=uuid4()))
    return generator


@pytest.mark.asyncio
@pytest.mark.parametrize("revision_kind", ["manual_create", "human_edit", "staged_generation"])
async def test_zero_query_legacy_lineages_are_eligible(revision_kind: str) -> None:
    source = _source(revision_kind=revision_kind, duration=20)
    generator = await _generator(source)
    complete = _response_for_request()
    with patch("app.services.llm_gateway.llm_gateway.complete", complete):
        await generator.create_visual_enrichment_revision(source.id)
    kwargs = generator._persist_revision.await_args.kwargs
    assert kwargs["revision_kind"] == "visual_enrichment"
    assert kwargs["parent_roteiro_id"] == source.id


@pytest.mark.asyncio
async def test_enrichment_preserves_speakable_content_and_metadata() -> None:
    source = _source(duration=60)
    generator = await _generator(source)
    before = RoteiroEstrutura.model_validate(source.estrutura)
    complete = _response_for_request()
    with patch("app.services.llm_gateway.llm_gateway.complete", complete):
        await generator.create_visual_enrichment_revision(source.id)
    enriched = generator._persist_revision.await_args.kwargs["estrutura"]
    assert speakable_content_identity(before.blocos) == speakable_content_identity(
        enriched.blocos
    )
    assert enriched.tags == before.tags
    assert enriched.referencias == before.referencias
    assert validate_visual_readiness(enriched).status == "ready"
    assert len(enriched.blocos[0].visual_queries) == 2


@pytest.mark.asyncio
async def test_long_section_is_enriched_in_bounded_batches_without_losing_beats() -> None:
    source = _source(duration=600)
    generator = await _generator(source)
    complete = _response_for_request()
    with patch("app.services.llm_gateway.llm_gateway.complete", complete):
        await generator.create_visual_enrichment_revision(source.id)
    enriched = generator._persist_revision.await_args.kwargs["estrutura"]
    queries = enriched.blocos[0].visual_queries
    assert complete.call_count_value() == 4
    assert len(queries) == 20
    assert [item.order for item in queries] == list(range(20))
    assert "".join(item.narration_excerpt or "" for item in queries) == source.estrutura[
        "blocos"
    ][0]["conteudo"]


@pytest.mark.asyncio
async def test_partial_batch_failure_never_persists_ready_revision() -> None:
    source = _source(duration=600)
    generator = await _generator(source)
    complete = _response_for_request(fail_after=1)
    with (
        patch("app.services.llm_gateway.llm_gateway.complete", complete),
        pytest.raises(LLMOutputError, match="falha controlada"),
    ):
        await generator.create_visual_enrichment_revision(source.id)
    generator._persist_revision.assert_not_awaited()


@pytest.mark.asyncio
async def test_already_enriched_script_is_not_used_as_backfill_source() -> None:
    source = _source(duration=20)
    source.estrutura["blocos"][0]["visual_queries"] = [
        {
            "id": str(uuid4()),
            "order": 0,
            "intent": "illustration",
            "query": "existente",
            "importance": "preferred",
        }
    ]
    generator = await _generator(source)
    with pytest.raises(ValueError, match="already has visual queries"):
        await generator.create_visual_enrichment_revision(source.id)
    generator._persist_revision.assert_not_awaited()


@pytest.mark.asyncio
async def test_incompatible_script_fails_before_llm_or_persistence() -> None:
    source = SimpleNamespace(
        id=uuid4(),
        ideia_id=uuid4(),
        status="rascunho",
        revision_kind="legacy",
        estrutura={"titulo": "incompleto"},
    )
    generator = await _generator(source)
    complete = AsyncMock()
    with (
        patch("app.services.llm_gateway.llm_gateway.complete", complete),
        pytest.raises(Exception),
    ):
        await generator.create_visual_enrichment_revision(source.id)
    complete.assert_not_awaited()
    generator._persist_revision.assert_not_awaited()


@pytest.mark.asyncio
async def test_llm_receives_host_owned_beats_and_cannot_return_spans() -> None:
    source = _source(duration=20)
    generator = await _generator(source)
    complete = _response_for_request()
    with patch("app.services.llm_gateway.llm_gateway.complete", complete):
        await generator.create_visual_enrichment_revision(source.id)
    request = complete.requests[0]
    schema_properties = request["response_schema"]["$defs"]["LLMVisualBeatQuery"][
        "properties"
    ]
    assert "beat_order" in schema_properties
    assert "narration_excerpt" not in schema_properties
    assert "coverage_start_char" not in schema_properties
    assert "BEATS:" in request["messages"][1]["content"]
