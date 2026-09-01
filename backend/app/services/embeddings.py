"""Serviço de embeddings pelo boundary compartilhado do 9Router."""

from app.core.config import settings
from app.services.llm_gateway import LLMGateway, llm_gateway


class EmbeddingService:
    """Gera vetores com dimensão compatível com o schema persistido."""

    def __init__(self, gateway: LLMGateway = llm_gateway):
        self.gateway = gateway
        self.model = settings.embedding_model
        self.dimensions = settings.embedding_dim

    async def generate(self, text: str) -> list[float]:
        """
        Gera embedding para um texto.

        Args:
            text: Texto para gerar embedding

        Returns:
            Lista de floats representando o vetor de embedding
        """
        vectors = await self.gateway.embed(
            input=text,
            model_alias=self.model,
            expected_dimensions=self.dimensions,
        )
        return vectors[0]

    async def generate_for_ideia(
        self, titulo: str, descricao: str | None = None
    ) -> list[float]:
        """
        Gera embedding combinando título e descrição de uma ideia.

        Args:
            titulo: Título da ideia
            descricao: Descrição breve (opcional)

        Returns:
            Lista de floats representando o vetor de embedding
        """
        text = titulo
        if descricao:
            text = f"{titulo}\n\n{descricao}"

        return await self.generate(text)


# Instância global do serviço
embedding_service = EmbeddingService()
