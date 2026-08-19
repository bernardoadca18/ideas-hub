"""
Serviço para gerar roteiros a partir de ideias aprovadas.

Para cada ideia aprovada, gera um roteiro estruturado em blocos narrativos.
"""
from uuid import UUID
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.ideia import Ideia
from app.models.roteiro import Roteiro
from app.repositories.ideia_repository import IdeiaRepository
from app.repositories.roteiro_repository import RoteiroRepository
from app.repositories.nicho_repository import NichoRepository
from app.schemas.roteiro import RoteiroCreate
from app.schemas.ideia import IdeiaCreate
from app.schemas.analise_jogo import AnaliseJogoRequest
from app.agents.roteirista import roteirista_service
from app.agents.analise_jogos import analise_jogos_service
from app.production_profiles import GAME_ANALYSIS


class RoteiroGenerator:
    """Gera roteiros a partir de ideias aprovadas."""

    def __init__(self, session: AsyncSession):
        self.session = session
        self.ideia_repo = IdeiaRepository(session)
        self.roteiro_repo = RoteiroRepository(session)
        self.nicho_repo = NichoRepository(session)

    async def generate_from_ideia(self, ideia_id: UUID) -> dict[str, Any]:
        ideia = await self.ideia_repo.get_by_id(ideia_id)
        if not ideia:
            raise ValueError("Ideia não encontrada")

        if ideia.status != "aprovada":
            raise ValueError(f"Ideia não está aprovada (status: {ideia.status})")

        prompt_roteiro = None
        perfil_id = None
        if ideia.nicho_id:
            nicho = await self.nicho_repo.get_by_id(ideia.nicho_id)
            if nicho:
                prompt_roteiro = nicho.prompt_roteiro
                perfil_id = nicho.perfil_producao

        roteiro_anterior = None
        numero_parte = ideia.numero_parte

        if ideia.eh_continuacao_de and numero_parte and numero_parte > 1:
            roteiro_ant = await self.roteiro_repo.get_latest_version_by_ideia(ideia.eh_continuacao_de)
            if roteiro_ant:
                roteiro_anterior = {"id": str(roteiro_ant.id), "estrutura": roteiro_ant.estrutura}

        roteiro_estruturado = await roteirista_service.gerar_roteiro(
            ideia_titulo=ideia.titulo,
            ideia_descricao=ideia.descricao_breve,
            prompt_roteiro=prompt_roteiro,
            roteiro_anterior=roteiro_anterior,
            numero_parte=numero_parte,
            ideia_id=str(ideia_id),
            perfil_id=perfil_id,
        )

        ultima_versao = await self.roteiro_repo.get_latest_version_by_ideia(ideia_id)
        nova_versao = (ultima_versao.versao + 1) if ultima_versao else 1

        novo_roteiro_data = RoteiroCreate(
            ideia_id=ideia_id,
            versao=nova_versao,
            estrutura=roteirista_service.to_dict(roteiro_estruturado),
            status="rascunho",
        )

        roteiro_criado = await self.roteiro_repo.create(novo_roteiro_data)

        from app.schemas.ideia import IdeiaUpdate
        await self.ideia_repo.update(ideia_id, IdeiaUpdate(status="em_roteiro"))

        return {
            'ideia_id': str(ideia_id),
            'roteiro_id': str(roteiro_criado.id),
            'versao': roteiro_criado.versao,
            'titulo': roteiro_estruturado.titulo,
            'duracao_total_segundos': roteiro_estruturado.duracao_total_segundos,
            'num_blocos': len(roteiro_estruturado.blocos),
            'status': roteiro_criado.status,
        }

    async def generate_from_notas(self, request: AnaliseJogoRequest) -> dict[str, Any]:
        """
        Workflow de Análise de Jogos: cria a Ideia (já aprovada, origem 'notas_gameplay')
        e o Roteiro v1 diretamente a partir das anotações do autor, sem passar pelo
        funil de trends/curadoria automática.
        """
        prompt_nicho = None
        if request.nicho_id:
            nicho = await self.nicho_repo.get_by_id(request.nicho_id)
            if nicho:
                prompt_nicho = nicho.prompt_roteiro

        roteiro_estruturado = await analise_jogos_service.gerar_roteiro_de_notas(
            titulo_provisorio=request.titulo_provisorio,
            anotacoes=request.anotacoes,
            nome_jogo=request.nome_jogo,
            prompt_nicho=prompt_nicho,
            usar_grounding=request.usar_grounding,
            media_project_id=request.media_project_id,
            media_session_ids=request.media_session_ids,
        )

        nova_ideia_data = IdeiaCreate(
            nicho_id=request.nicho_id,
            origem="notas_gameplay",
            titulo=roteiro_estruturado.titulo,
            descricao_breve=(request.anotacoes[:497] + "...") if len(request.anotacoes) > 500 else request.anotacoes,
            status="aprovada",
            eh_continuacao_de=None,
            numero_parte=None,
            fonte_trend_id=None,
            justificativa_llm="Ideia criada diretamente a partir de anotações de gameplay (workflow de análise de jogos).",
        )
        ideia_criada = await self.ideia_repo.create(nova_ideia_data)

        novo_roteiro_data = RoteiroCreate(
            ideia_id=ideia_criada.id,
            versao=1,
            estrutura=roteirista_service.to_dict(roteiro_estruturado),
            status="rascunho",
        )
        roteiro_criado = await self.roteiro_repo.create(novo_roteiro_data)

        from app.schemas.ideia import IdeiaUpdate
        await self.ideia_repo.update(ideia_criada.id, IdeiaUpdate(status="em_roteiro"))

        return {
            'ideia_id': str(ideia_criada.id),
            'roteiro_id': str(roteiro_criado.id),
            'versao': roteiro_criado.versao,
            'titulo': roteiro_estruturado.titulo,
            'duracao_total_segundos': roteiro_estruturado.duracao_total_segundos,
            'num_blocos': len(roteiro_estruturado.blocos),
            'status': roteiro_criado.status,
        }

    async def aprovar_roteiro(self, roteiro_id: UUID) -> dict[str, Any]:
        roteiro = await self.roteiro_repo.get_by_id(roteiro_id)
        if not roteiro:
            raise ValueError("Roteiro não encontrado")
        if roteiro.status != "rascunho":
            raise ValueError(f"Roteiro não está em rascunho (status: {roteiro.status})")

        from app.schemas.roteiro import RoteiroUpdate
        roteiro_atualizado = await self.roteiro_repo.update(roteiro_id, RoteiroUpdate(status="aprovado"))

        ideia_id = roteiro.ideia_id
        from app.schemas.ideia import IdeiaUpdate
        await self.ideia_repo.update(ideia_id, IdeiaUpdate(status="roteirizada"))

        return {
            'roteiro_id': str(roteiro_id), 'ideia_id': str(ideia_id),
            'status': roteiro_atualizado.status, 'mensagem': 'Roteiro aprovado com sucesso',
        }

    async def rejeitar_roteiro(self, roteiro_id: UUID) -> dict[str, Any]:
        roteiro = await self.roteiro_repo.get_by_id(roteiro_id)
        if not roteiro:
            raise ValueError("Roteiro não encontrado")
        if roteiro.status != "rascunho":
            raise ValueError(f"Roteiro não está em rascunho (status: {roteiro.status})")

        from app.schemas.roteiro import RoteiroUpdate
        roteiro_atualizado = await self.roteiro_repo.update(roteiro_id, RoteiroUpdate(status="rejeitado"))

        ideia_id = roteiro.ideia_id
        from app.schemas.ideia import IdeiaUpdate
        await self.ideia_repo.update(ideia_id, IdeiaUpdate(status="aprovada"))

        return {
            'roteiro_id': str(roteiro_id), 'ideia_id': str(ideia_id),
            'status': roteiro_atualizado.status,
            'mensagem': 'Roteiro rejeitado. Ideia voltou para status aprovada.',
        }


def get_roteiro_generator(session: AsyncSession) -> RoteiroGenerator:
    return RoteiroGenerator(session)
