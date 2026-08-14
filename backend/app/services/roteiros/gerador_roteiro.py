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
from app.agents.roteirista import roteirista_service


class RoteiroGenerator:
    """Gera roteiros a partir de ideias aprovadas."""

    def __init__(self, session: AsyncSession):
        self.session = session
        self.ideia_repo = IdeiaRepository(session)
        self.roteiro_repo = RoteiroRepository(session)
        self.nicho_repo = NichoRepository(session)

    async def generate_from_ideia(
        self,
        ideia_id: UUID,
    ) -> dict[str, Any]:
        """
        Gera um roteiro a partir de uma ideia aprovada.

        Args:
            ideia_id: ID da ideia aprovada

        Returns:
            Dict com estatísticas da geração
        """
        # 1. Verifica se a ideia existe e está aprovada
        ideia = await self.ideia_repo.get_by_id(ideia_id)
        if not ideia:
            raise ValueError("Ideia não encontrada")

        if ideia.status != "aprovada":
            raise ValueError(f"Ideia não está aprovada (status: {ideia.status})")

        # 2. Busca o nicho para obter prompt de roteiro
        prompt_roteiro = None
        if ideia.nicho_id:
            nicho = await self.nicho_repo.get_by_id(ideia.nicho_id)
            if nicho:
                prompt_roteiro = nicho.prompt_roteiro

        if not prompt_roteiro:
            prompt_roteiro = "Crie um roteiro envolvente e dinâmico para o tema proposto."

        # 3. Busca roteiro anterior se for continuação (parte 2+)
        roteiro_anterior = None
        numero_parte = ideia.numero_parte

        if ideia.eh_continuacao_de and numero_parte and numero_parte > 1:
            # Busca roteiro da parte anterior
            roteiro_ant = await self.roteiro_repo.get_latest_version_by_ideia(ideia.eh_continuacao_de)
            if roteiro_ant:
                roteiro_anterior = {
                    "id": str(roteiro_ant.id),
                    "estrutura": roteiro_ant.estrutura,
                }

        # 4. Gera roteiro via Agente Roteirista
        roteiro_estruturado = await roteirista_service.gerar_roteiro(
            ideia_titulo=ideia.titulo,
            ideia_descricao=ideia.descricao_breve,
            prompt_roteiro=prompt_roteiro,
            roteiro_anterior=roteiro_anterior,
            numero_parte=numero_parte,
        )

        # 5. Determina próxima versão
        ultima_versao = await self.roteiro_repo.get_latest_version_by_ideia(ideia_id)
        nova_versao = (ultima_versao.versao + 1) if ultima_versao else 1

        # 6. Cria o roteiro no banco
        novo_roteiro_data = RoteiroCreate(
            ideia_id=ideia_id,
            versao=nova_versao,
            estrutura=roteirista_service.to_dict(roteiro_estruturado),
            status="rascunho",
        )

        roteiro_criado = await self.roteiro_repo.create(novo_roteiro_data)

        # 7. Atualiza status da ideia para "em_roteiro"
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

    async def aprovar_roteiro(self, roteiro_id: UUID) -> dict[str, Any]:
        """
        Aprova um roteiro.

        Args:
            roteiro_id: ID do roteiro

        Returns:
            Dict com resultado da operação
        """
        roteiro = await self.roteiro_repo.get_by_id(roteiro_id)
        if not roteiro:
            raise ValueError("Roteiro não encontrado")

        if roteiro.status != "rascunho":
            raise ValueError(f"Roteiro não está em rascunho (status: {roteiro.status})")

        # Atualiza status do roteiro
        from app.schemas.roteiro import RoteiroUpdate
        roteiro_atualizado = await self.roteiro_repo.update(
            roteiro_id,
            RoteiroUpdate(status="aprovado")
        )

        # Atualiza status da ideia para "roteirizada"
        ideia_id = roteiro.ideia_id
        from app.schemas.ideia import IdeiaUpdate
        await self.ideia_repo.update(ideia_id, IdeiaUpdate(status="roteirizada"))

        return {
            'roteiro_id': str(roteiro_id),
            'ideia_id': str(ideia_id),
            'status': roteiro_atualizado.status,
            'mensagem': 'Roteiro aprovado com sucesso',
        }

    async def rejeitar_roteiro(self, roteiro_id: UUID) -> dict[str, Any]:
        """
        Rejeita um roteiro.

        Args:
            roteiro_id: ID do roteiro

        Returns:
            Dict com resultado da operação
        """
        roteiro = await self.roteiro_repo.get_by_id(roteiro_id)
        if not roteiro:
            raise ValueError("Roteiro não encontrado")

        if roteiro.status != "rascunho":
            raise ValueError(f"Roteiro não está em rascunho (status: {roteiro.status})")

        # Atualiza status do roteiro
        from app.schemas.roteiro import RoteiroUpdate
        roteiro_atualizado = await self.roteiro_repo.update(
            roteiro_id,
            RoteiroUpdate(status="rejeitado")
        )

        # Volta status da ideia para "aprovada" (pode gerar novo roteiro)
        ideia_id = roteiro.ideia_id
        from app.schemas.ideia import IdeiaUpdate
        await self.ideia_repo.update(ideia_id, IdeiaUpdate(status="aprovada"))

        return {
            'roteiro_id': str(roteiro_id),
            'ideia_id': str(ideia_id),
            'status': roteiro_atualizado.status,
            'mensagem': 'Roteiro rejeitado. Ideia voltou para status aprovada.',
        }


# Factory
def get_roteiro_generator(session: AsyncSession) -> RoteiroGenerator:
    """Factory para criar instância do gerador."""
    return RoteiroGenerator(session)
