"""
Verificação da Etapa 3 - Embeddings + Busca por Similaridade

Este script:
1. Cria duas ideias parecidas (mas não idênticas)
2. Gera embeddings para ambas
3. Busca similares da primeira
4. Confirma que a segunda é encontrada como candidata a continuação
"""
import asyncio
from app.core.database import AsyncSessionLocal
from app.core.config import settings
from app.repositories import NichoRepository, IdeiaRepository
from app.schemas import NichoCreate, IdeiaCreate
from app.services.embeddings import embedding_service


def check_litellm_proxy():
    """Verifica se o LiteLLM Proxy está acessível."""
    import httpx
    try:
        # LiteLLM pode retornar 401 se precisar de auth, mas significa que está acessível
        response = httpx.get(f"{settings.litellm_base_url}/health", timeout=2.0)
        if response.status_code in (200, 401):
            return True
    except Exception:
        pass

    print(f"❌ ERRO: LiteLLM Proxy não está acessível em {settings.litellm_base_url}")
    print("\nPara executar este script de verificação:")
    print("  1. Certifique-se de que o LiteLLM Proxy está rodando localmente")
    print("  2. Verifique se o modelo de embedding está configurado no proxy")
    print(f"  3. Confirme que a porta 4000 está exposta e acessível via {settings.litellm_base_url}")
    return False


async def main():
    async with AsyncSessionLocal() as session:
        nicho_repo = NichoRepository(session)
        ideia_repo = IdeiaRepository(session)

        # Criar ou obter nicho
        nicho = await nicho_repo.get_by_slug('tecnologia-ia')
        if not nicho:
            nicho_data = NichoCreate(
                slug='tecnologia-ia',
                nome='Tecnologia e IA',
                prompt_ideacao='Gere ideias de vídeos sobre tecnologia e IA',
                prompt_roteiro='Crie roteiros detalhados sobre tecnologia e IA'
            )
            nicho = await nicho_repo.create(nicho_data)
        print(f'=== Nicho: {nicho.nome} (ID: {nicho.id}) ===')

        # Criar primeira ideia
        ideia1_data = IdeiaCreate(
            nicho_id=nicho.id,
            origem='manual',
            titulo='Como usar inteligência artificial para melhorar sua produtividade',
            descricao_breve='Dicas práticas para usar ferramentas de IA no dia a dia',
            status='rascunho'
        )
        ideia1 = await ideia_repo.create(ideia1_data)
        print(f'\n=== Ideia 1 criada: {ideia1.titulo} ===')

        # Criar segunda ideia (parecida, mas não idêntica)
        ideia2_data = IdeiaCreate(
            nicho_id=nicho.id,
            origem='manual',
            titulo='Ferramentas de IA para aumentar sua produtividade no trabalho',
            descricao_breve='Guia completo de ferramentas de inteligência artificial',
            status='rascunho'
        )
        ideia2 = await ideia_repo.create(ideia2_data)
        print(f'=== Ideia 2 criada: {ideia2.titulo} ===')

        # Gerar embeddings
        print('\n=== Gerando embeddings... ===')
        embedding1 = await embedding_service.generate_for_ideia(
            ideia1.titulo,
            ideia1.descricao_breve
        )
        await ideia_repo.update_embedding(ideia1.id, embedding1)
        print(f'Embedding 1 gerado ({len(embedding1)} dimensões)')

        embedding2 = await embedding_service.generate_for_ideia(
            ideia2.titulo,
            ideia2.descricao_breve
        )
        await ideia_repo.update_embedding(ideia2.id, embedding2)
        print(f'Embedding 2 gerado ({len(embedding2)} dimensões)')

        # Buscar ideias similares à primeira (excluindo ela mesma)
        print(f'\n=== Buscando ideias similares (threshold: {settings.ideia_similarity_threshold}) ===')
        similares = await ideia_repo.find_similar(
            embedding=embedding1,
            threshold=settings.ideia_similarity_threshold,
            exclude_id=ideia1.id,
            limit=5
        )

        print(f'Encontradas {len(similares)} ideia(s) similar(es):')
        for s in similares:
            print(f'  - {s.titulo}')

        # Verificar se a segunda ideia foi encontrada
        ideia2_encontrada = any(s.id == ideia2.id for s in similares)

        if ideia2_encontrada:
            print(f'\n✅ SUCESSO: Ideia 2 foi encontrada como candidata a continuação de Ideia 1!')
            print(f'   Isso confirma que a busca por similaridade está funcionando corretamente.')
        else:
            print(f'\n❌ FALHA: Ideia 2 NÃO foi encontrada.')
            print(f'   Verifique se o threshold ({settings.ideia_similarity_threshold}) está adequado.')

        # Limpeza (opcional - comentar para manter dados)
        # await ideia_repo.delete(ideia1.id)
        # await ideia_repo.delete(ideia2.id)
        # print('\n=== Ideias de teste removidas ===')


if __name__ == "__main__":
    if not check_litellm_proxy():
        exit(1)
    asyncio.run(main())
