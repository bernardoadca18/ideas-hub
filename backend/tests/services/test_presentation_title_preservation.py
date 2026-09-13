from types import SimpleNamespace

from app.agents.roteirista import RoteiroEstruturado, roteirista_service
from app.schemas.roteiro import RoteiroEstrutura
from app.services.script_generation_jobs import assemble_written_sections


def test_explicit_planned_section_title_is_preserved_separately_from_tipo() -> None:
    section = SimpleNamespace(
        section_order=0,
        section_key="section-001",
        section_plan={"title": "A cidade reage", "target_duration_seconds": 30},
        output={
            "content": "Texto narrado.",
            "visual_intent": None,
            "visual_queries": [],
            "beats_covered": [],
            "claims_used": [],
        },
    )
    block = assemble_written_sections([section], claim_ledger=[])[0]
    assert block.display_title == "A cidade reage"
    payload = roteirista_service.to_dict(
        RoteiroEstruturado(
            titulo="Vídeo",
            duracao_total_segundos=30,
            blocos=[block],
            tags=[],
        )
    )
    structure = RoteiroEstrutura.model_validate(payload)
    assert structure.blocos[0].display_title == "A cidade reage"


def test_legacy_block_without_display_title_remains_valid() -> None:
    structure = RoteiroEstrutura.model_validate(
        {
            "titulo": "Legacy",
            "duracao_total_segundos": 10,
            "blocos": [
                {
                    "tipo": "desenvolvimento",
                    "duracao_segundos": 10,
                    "conteudo": "Texto.",
                }
            ],
        }
    )
    assert structure.blocos[0].display_title is None
