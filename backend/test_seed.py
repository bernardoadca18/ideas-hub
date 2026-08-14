"""
Script para testar a camada de dados - seed manual de um nicho e uma ideia.
"""
import asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import AsyncSessionLocal
from app.repositories import NichoRepository, IdeiaRepository
from app.schemas import NichoCreate, IdeiaCreate


async def test_data_layer():
    """Testa a criação e leitura de nicho e ideia."""
    async with AsyncSessionLocal() as session:
        # Criar repositórios
        nicho_repo = NichoRepository(session)
        ideia_repo = IdeiaRepository(session)

        # 1. Criar um nicho
        print("\n=== Criando nicho ===")
        nicho_data = NichoCreate(
            slug="tecnologia-ia",
            nome="Tecnologia e Inteligência Artificial",
            descricao="Vídeos sobre tendências em tecnologia e IA",
            prompt_ideacao="Gere ideias de vídeos sobre tecnologia e IA para iniciantes",
            prompt_roteiro="Crie um roteiro educativo sobre tecnologia e IA",
            categoria_google_trends="Technology",
            ativo=True
        )
        nicho = await nicho_repo.create(nicho_data)
        print(f"Nicho criado: ID={nicho.id}, slug={nicho.slug}, nome={nicho.nome}")

        # 2. Criar uma ideia
        print("\n=== Criando ideia ===")
        ideia_data = IdeiaCreate(
            nicho_id=nicho.id,
            origem="manual",
            titulo="Como usar o ChatGPT para aumentar sua produtividade",
            descricao_breve="Um guia prático para iniciantes sobre como usar o ChatGPT no dia a dia",
            status="rascunho"
        )
        ideia = await ideia_repo.create(ideia_data)
        print(f"Ideia criada: ID={ideia.id}, título={ideia.titulo}")

        # 3. Ler de volta
        print("\n=== Lendo dados de volta ===")
        nicho_lido = await nicho_repo.get_by_id(nicho.id)
        print(f"Nicho lido: {nicho_lido.nome}")

        ideia_lida = await ideia_repo.get_by_id(ideia.id)
        print(f"Ideia lida: {ideia_lida.titulo}")

        # 4. Listar
        print("\n=== Listando dados ===")
        nichos = await nicho_repo.list(limit=10)
        print(f"Total de nichos: {len(nichos)}")

        ideias = await ideia_repo.list(limit=10)
        print(f"Total de ideias: {len(ideias)}")

        print("\n✅ Teste da camada de dados concluído com sucesso!")


if __name__ == "__main__":
    asyncio.run(test_data_layer())
