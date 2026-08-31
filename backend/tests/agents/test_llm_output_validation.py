import json

import pytest
from app.agents.roteirista import RoteiristaService
from app.schemas.llm_outputs import (
    LLMOutputError,
    ScriptLLMOutput,
    validate_model_output,
)


def valid_script() -> dict:
    return {
        "titulo": "Título",
        "duracao_total_segundos": 120,
        "blocos": [
            {
                "tipo": "desenvolvimento",
                "duracao_segundos": 120,
                "conteudo": "Narração completa.",
                "dicas_visual": None,
                "dicas_audio": None,
            }
        ],
        "tags": [],
        "referencias": None,
        "justificativa": "Estrutura coerente",
    }


@pytest.mark.parametrize(
    ("raw", "category"),
    [
        ("", "empty_output"),
        ("not-json", "malformed_json"),
        (json.dumps({**valid_script(), "blocos": []}), "contract_validation"),
        (
            json.dumps(
                {
                    **valid_script(),
                    "blocos": [{**valid_script()["blocos"][0], "conteudo": "  "}],
                }
            ),
            "contract_validation",
        ),
    ],
)
def test_invalid_script_output_is_rejected(raw: str, category: str) -> None:
    with pytest.raises(LLMOutputError) as error:
        validate_model_output(ScriptLLMOutput, raw)
    assert error.value.category == category


@pytest.mark.asyncio
async def test_author_briefing_is_separate_in_script_prompt() -> None:
    service = RoteiristaService()
    service.tavily_api_key = None
    captured: list[dict] = []

    async def fake_call(messages, temperature=0.7, max_tokens=8000, **_kwargs):
        captured.extend(messages)
        return json.dumps(valid_script())

    service._call_llm = fake_call
    briefing = "Eu acho que o combate envelheceu mal. Preserve isto como opinião."
    await service.gerar_roteiro(
        ideia_titulo="Análise",
        ideia_descricao="Descrição factual",
        prompt_roteiro=None,
        author_briefing=briefing,
    )

    user_prompt = captured[-1]["content"]
    assert "AUTHOR BRIEFING" in user_prompt
    assert briefing in user_prompt
    assert "não como prova factual" in user_prompt


@pytest.mark.asyncio
async def test_no_briefing_still_generates() -> None:
    service = RoteiristaService()
    service.tavily_api_key = None
    service._call_llm = lambda *args, **kwargs: None  # type: ignore[method-assign]

    async def fake_call(*args, **kwargs):
        return json.dumps(valid_script())

    service._call_llm = fake_call
    result = await service.gerar_roteiro(
        ideia_titulo="Análise",
        ideia_descricao=None,
        prompt_roteiro=None,
    )
    assert result.blocos[0].conteudo == "Narração completa."
