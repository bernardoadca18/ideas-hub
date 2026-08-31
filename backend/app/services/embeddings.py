"""
Serviço de embeddings para geração de vetores de similaridade.
"""

import httpx

from app.core.config import settings


class EmbeddingService:
    """Serviço para geração de embeddings via LiteLLM Proxy."""

    def __init__(self):
        self.base_url = settings.litellm_base_url
        self.api_key = settings.litellm_master_key or "dummy-key"
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
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                f"{self.base_url}/v1/embeddings",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self.model,
                    "input": text,
                },
            )
            response.raise_for_status()
            data = response.json()
            return data["data"][0]["embedding"]

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
