"""Ideas Hub embedding service over the direct Ollama boundary."""

from collections.abc import Sequence

from app.core.config import settings
from app.services.embedding_provider import (
    EmbeddingProvider,
    ollama_embedding_provider,
)


class EmbeddingService:
    """Gera vetores com dimensão compatível com o schema persistido."""

    def __init__(
        self,
        provider: EmbeddingProvider = ollama_embedding_provider,
        *,
        model: str = settings.embedding_model,
        dimensions: int = settings.embedding_dim,
    ):
        self.provider = provider
        self.model = model
        self.dimensions = dimensions

    async def generate_batch(self, texts: Sequence[str]) -> list[list[float]]:
        return await self.provider.embed(
            texts,
            model=self.model,
            expected_dimensions=self.dimensions,
        )

    async def generate(self, text: str) -> list[float]:
        """
        Gera embedding para um texto.

        Args:
            text: Texto para gerar embedding

        Returns:
            Lista de floats representando o vetor de embedding
        """
        vectors = await self.generate_batch([text])
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
