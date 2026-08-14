"""
Verificação da Etapa 1 - Data Layer
"""
import asyncio
from app.core.database import AsyncSessionLocal
from app.repositories import NichoRepository, IdeiaRepository
from app.schemas import IdeiaCreate


async def main():
    async with AsyncSessionLocal() as session:
        nicho_repo = NichoRepository(session)
        ideia_repo = IdeiaRepository(session)

        # Get existing nicho
        nicho = await nicho_repo.get_by_slug('tecnologia-ia')
        print(f'=== Nicho: {nicho.nome} (ID: {nicho.id}) ===')

        # Create ideia
        ideia_data = IdeiaCreate(
            nicho_id=nicho.id,
            origem='manual',
            titulo='Como usar IA para programar melhor',
            descricao_breve='Guia para devs',
            status='rascunho'
        )
        ideia = await ideia_repo.create(ideia_data)
        print(f'=== Ideia criada: {ideia.titulo} ===')

        # Read back
        lida = await ideia_repo.get_by_id(ideia.id)
        print(f'=== Ideia lida: {lida.titulo} ===')

        print('\n✅ Etapa 1 verificada!')


if __name__ == "__main__":
    asyncio.run(main())
