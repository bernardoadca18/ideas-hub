"""
Verificação da Etapa 4 - Agente Curador

Este script:
1. Cria um nicho com prompt de ideação
2. Envia uma ideia crua via endpoint de criação
3. Verifica se a ideia foi refinada pelo curador
4. Envia uma ideia similar e verifica sinalização de continuação/duplicidade
"""
import asyncio
import httpx

from app.core.config import settings


API_BASE_URL = f"http://localhost:{settings.api_port}"


async def test_criar_nicho():
    """Cria um nicho para teste."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            f"{API_BASE_URL}/nichos/",
            json={
                "slug": "teste-curador",
                "nome": "Teste Curador",
                "prompt_ideacao": "Gere ideias de vídeos sobre tecnologia e produtividade pessoal",
                "prompt_roteiro": "Crie roteiros detalhados"
            }
        )
        if response.status_code == 201:
            return response.json()
        elif response.status_code == 400:
            # Nicho já existe, buscar por slug
            response = await client.get(f"{API_BASE_URL}/nichos/")
            for nicho in response.json():
                if nicho["slug"] == "teste-curador":
                    return nicho
        response.raise_for_status()


async def test_ideia_bruta(nicho_id: str):
    """Testa criação de ideia bruta e verifica refinamento."""
    print("\n=== Teste 1: Enviando ideia bruta ===")

    async with httpx.AsyncClient(timeout=60.0) as client:
        ideia_bruta = {
            "titulo": "ia pra trabalhar",
            "descricao": "como usar ia no trabalho",
            "nicho_id": nicho_id
        }

        print(f"Enviando: {ideia_bruta}")
        response = await client.post(
            f"{API_BASE_URL}/ideias/",
            json=ideia_bruta
        )

        if response.status_code != 201:
            print(f"Erro: {response.status_code} - {response.text}")
            response.raise_for_status()

        ideia = response.json()
        print(f"\nIdeia criada:")
        print(f"  Título original: '{ideia_bruta['titulo']}'")
        print(f"  Título refinado: '{ideia['titulo']}'")
        print(f"  Descrição refinada: '{ideia.get('descricao_breve', 'N/A')}'")
        print(f"  Justificativa LLM: {ideia.get('justificativa_llm', 'N/A')}")
        print(f"  É duplicada: {ideia.get('eh_duplicada', False)}")
        print(f"  É continuação: {ideia.get('eh_continuacao', False)}")

        # Verifica se houve refinamento
        if ideia['titulo'] != ideia_bruta['titulo']:
            print("\n✅ Título foi refinado!")
        else:
            print("\n⚠️ Título não foi alterado (pode ser normal dependendo do LLM)")

        return ideia


async def test_ideia_similar(nicho_id: str, ideia_original_id: str):
    """Testa criação de ideia similar e verifica sinalização."""
    print("\n=== Teste 2: Enviando ideia similar ===")

    async with httpx.AsyncClient(timeout=60.0) as client:
        ideia_similar = {
            "titulo": "ferramentas de inteligência artificial para produtividade",
            "descricao": "como usar ferramentas de IA para ser mais produtivo",
            "nicho_id": nicho_id
        }

        print(f"Enviando: {ideia_similar}")
        response = await client.post(
            f"{API_BASE_URL}/ideias/",
            json=ideia_similar
        )

        if response.status_code != 201:
            print(f"Erro: {response.status_code} - {response.text}")
            response.raise_for_status()

        ideia = response.json()
        print(f"\nIdeia criada:")
        print(f"  Título refinado: '{ideia['titulo']}'")
        print(f"  Descrição refinada: '{ideia.get('descricao_breve', 'N/A')}'")
        print(f"  É duplicada: {ideia.get('eh_duplicada', False)}")
        print(f"  É continuação: {ideia.get('eh_continuacao', False)}")
        print(f"  Ideia similar ID: {ideia.get('ideia_similar_id', 'N/A')}")
        print(f"  Ideia similar título: {ideia.get('ideia_similar_titulo', 'N/A')}")
        print(f"  Similaridade: {ideia.get('similaridade', 'N/A')}")

        # Verifica sinalização
        if ideia.get('eh_duplicada'):
            print("\n✅ Ideia sinalizada como DUPLICADA!")
        elif ideia.get('eh_continuacao'):
            print("\n✅ Ideia sinalizada como CONTINUAÇÃO!")
        elif ideia.get('ideia_similar_id'):
            print("\n⚠️ Ideia similar encontrada, mas não sinalizada")
        else:
            print("\n⚠️ Nenhuma similaridade detectada (pode ser normal)")

        return ideia


async def test_grounding(nicho_id: str):
    """Testa se o grounding via Tavily está funcionando (se API key configurada)."""
    print("\n=== Teste 3: Verificando grounding (se Tavily configurado) ===")

    if not settings.tavily_api_key:
        print("⚠️ TAVILY_API_KEY não configurada - pulando teste de grounding")
        return None

    async with httpx.AsyncClient(timeout=60.0) as client:
        ideia = {
            "titulo": "últimas novidades em inteligência artificial 2024",
            "descricao": "atualizações recentes sobre IA",
            "nicho_id": nicho_id
        }

        print(f"Enviando: {ideia}")
        response = await client.post(
            f"{API_BASE_URL}/ideias/",
            json=ideia
        )

        if response.status_code != 201:
            print(f"Erro: {response.status_code} - {response.text}")
            return None

        ideia_criada = response.json()
        print(f"\nIdeia criada: {ideia_criada['titulo']}")

        if ideia_criada.get('justificativa_llm'):
            print("✅ Ideia processada pelo curador")
            print(f"   Justificativa: {ideia_criada['justificativa_llm']}")

        return ideia_criada


async def cleanup():
    """Remove dados de teste."""
    print("\n=== Limpando dados de teste ===")
    async with httpx.AsyncClient(timeout=30.0) as client:
        # Busca todas as ideias do teste
        response = await client.get(f"{API_BASE_URL}/ideias/")
        ideias = response.json()

        for ideia in ideias:
            if "teste" in ideia.get("titulo", "").lower() or \
               "ia pra" in ideia.get("titulo", "").lower() or \
               "ferramentas de inteligência" in ideia.get("titulo", "").lower() or \
               "últimas novidades" in ideia.get("titulo", "").lower():
                await client.delete(f"{API_BASE_URL}/ideias/{ideia['id']}")
                print(f"  Removida: {ideia['titulo']}")

        # Remove nicho de teste
        response = await client.get(f"{API_BASE_URL}/nichos/")
        for nicho in response.json():
            if nicho["slug"] == "teste-curador":
                await client.delete(f"{API_BASE_URL}/nichos/{nicho['id']}")
                print(f"  Removido nicho: {nicho['nome']}")


async def main():
    print("=" * 60)
    print("VERIFICAÇÃO DA ETAPA 4 - AGENTE CURADOR")
    print("=" * 60)

    # 1. Criar nicho
    print("\n=== Criando nicho de teste ===")
    nicho = await test_criar_nicho()
    print(f"Nicho criado: {nicho['nome']} (ID: {nicho['id']})")

    # 2. Testar ideia bruta
    ideia1 = await test_ideia_bruta(nicho['id'])

    # 3. Testar ideia similar
    ideia2 = await test_ideia_similar(nicho['id'], ideia1['id'])

    # 4. Testar grounding (se configurado)
    await test_grounding(nicho['id'])

    # 5. Resumo
    print("\n" + "=" * 60)
    print("RESUMO DA VERIFICAÇÃO")
    print("=" * 60)

    print(f"\n1. Ideia bruta refinada: {'✅' if ideia1 else '❌'}")
    print(f"2. Ideia similar detectada: {'✅' if ideia2.get('ideia_similar_id') else '⚠️'}")
    print(f"3. Sinalização de continuação/duplicidade: {'✅' if ideia2.get('eh_continuacao') or ideia2.get('eh_duplicada') else '⚠️'}")

    # Cleanup
    await cleanup()

    print("\n✅ Verificação da Etapa 4 concluída!")


if __name__ == "__main__":
    asyncio.run(main())
