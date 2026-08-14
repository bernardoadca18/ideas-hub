"""
Verificação da Etapa 5 - Coleta de Trends

Este script:
1. Cria um nicho de teste
2. Configura fontes de trend (Reddit e YouTube)
3. Dispara coleta de trends
4. Verifica se pelo menos 2 fontes retornaram dados
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
                "slug": "teste-trends",
                "nome": "Teste Trends",
                "prompt_ideacao": "IA e tecnologia",
                "prompt_roteiro": "Crie roteiros detalhados para vídeos sobre IA",
            }
        )
        if response.status_code == 201:
            return response.json()
        elif response.status_code == 400:
            # Nicho já existe, buscar por slug
            response = await client.get(f"{API_BASE_URL}/nichos/")
            for nicho in response.json():
                if nicho["slug"] == "teste-trends":
                    return nicho
        response.raise_for_status()


async def test_configurar_fontes(nicho_id: str):
    """Configura fontes de trend para o nicho."""
    print("\n=== Configurando fontes de trend ===")

    async with httpx.AsyncClient(timeout=30.0) as client:
        fontes_criadas = []

        # 1. Reddit - r/technology
        response = await client.post(
            f"{API_BASE_URL}/fontes-trend/",
            json={
                "nicho_id": nicho_id,
                "tipo": "reddit_publico",
                "identificador": "technology",
                "ativo": True
            }
        )
        if response.status_code in [201, 400]:
            print(f"  ✅ Reddit r/technology configurado")
            fontes_criadas.append("reddit_publico")
        else:
            print(f"  ⚠️ Erro ao configurar Reddit: {response.status_code}")

        # 2. YouTube - categoria de tecnologia
        # Nota: YouTube precisa de API key configurada
        if settings.youtube_api_key:
            response = await client.post(
                f"{API_BASE_URL}/fontes-trend/",
                json={
                    "nicho_id": nicho_id,
                    "tipo": "youtube_categoria",
                    "identificador": "28",  # Science & Technology
                    "ativo": True
                }
            )
            if response.status_code in [201, 400]:
                print(f"  ✅ YouTube categoria configurado")
                fontes_criadas.append("youtube")
        else:
            print(f"  ⚠️ YOUTUBE_API_KEY não configurada - pulando")

        # 3. RSS - TechCrunch
        response = await client.post(
            f"{API_BASE_URL}/fontes-trend/",
            json={
                "nicho_id": nicho_id,
                "tipo": "rss",
                "identificador": "https://techcrunch.com/feed/",
                "ativo": True
            }
        )
        if response.status_code in [201, 400]:
            print(f"  ✅ RSS TechCrunch configurado")
            fontes_criadas.append("rss")
        else:
            print(f"  ⚠️ Erro ao configurar RSS: {response.status_code}")

        return fontes_criadas


async def test_coletar_trends(nicho_id: str):
    """Testa coleta de trends."""
    print("\n=== Disparando coleta de trends ===")

    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.post(
            f"{API_BASE_URL}/trends/coletar",
            json={
                "nicho_id": nicho_id,
                "termos_adicionais": ["inteligência artificial", "machine learning"]
            }
        )

        if response.status_code != 201:
            print(f"Erro: {response.status_code} - {response.text}")
            response.raise_for_status()

        resultado = response.json()
        print(f"\nResultado da coleta:")
        print(f"  Total coletado: {resultado['total_coletado']}")
        print(f"  Por fonte: {resultado['por_fonte']}")
        if resultado.get('erros'):
            print(f"  Erros: {resultado['erros']}")

        return resultado


async def test_listar_trends(nicho_id: str):
    """Lista trends coletadas."""
    print("\n=== Listando trends coletadas ===")

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.get(
            f"{API_BASE_URL}/trends/",
            params={"nicho_id": nicho_id, "limit": 20}
        )
        response.raise_for_status()

        trends = response.json()
        print(f"\nTotal de trends: {len(trends)}")

        # Agrupa por fonte
        por_fonte = {}
        for trend in trends:
            fonte = trend['fonte']
            if fonte not in por_fonte:
                por_fonte[fonte] = []
            por_fonte[fonte].append(trend['termo_bruto'])

        for fonte, termos in por_fonte.items():
            print(f"\n  {fonte}: {len(termos)} trends")
            for termo in termos[:3]:
                print(f"    - {termo[:80]}...")

        return por_fonte


async def test_aprovar_rejeitar(nicho_id: str):
    """Testa aprovação e rejeição de trends."""
    print("\n=== Testando aprovação/rejeição ===")

    async with httpx.AsyncClient(timeout=30.0) as client:
        # Busca trends pendentes
        response = await client.get(
            f"{API_BASE_URL}/trends/",
            params={"nicho_id": nicho_id, "status": "pendente", "limit": 2}
        )
        trends = response.json()

        if len(trends) < 2:
            print("  ⚠️ Não há trends suficientes para testar")
            return

        # Aprova primeira
        trend_id = trends[0]['id']
        response = await client.patch(f"{API_BASE_URL}/trends/{trend_id}/aprovar")
        if response.status_code == 200:
            print(f"  ✅ Trend aprovada: {trends[0]['termo_bruto'][:50]}...")

        # Rejeita segunda
        trend_id = trends[1]['id']
        response = await client.patch(f"{API_BASE_URL}/trends/{trend_id}/rejeitar")
        if response.status_code == 200:
            print(f"  ✅ Trend rejeitada: {trends[1]['termo_bruto'][:50]}...")


async def cleanup(nicho_id: str):
    """Remove dados de teste."""
    print("\n=== Limpando dados de teste ===")
    async with httpx.AsyncClient(timeout=30.0) as client:
        # Remove trends (paginate if needed)
        all_trends = []
        for offset in range(0, 500, 100):
            response = await client.get(
                f"{API_BASE_URL}/trends/",
                params={"nicho_id": nicho_id, "limit": 100, "skip": offset}
            )
            batch = response.json()
            if not batch:
                break
            all_trends.extend(batch)

        for trend in all_trends:
            await client.delete(f"{API_BASE_URL}/trends/{trend['id']}")

        print(f"  Removidas {len(all_trends)} trends")

        # Remove fontes
        response = await client.get(
            f"{API_BASE_URL}/fontes-trend/",
            params={"nicho_id": nicho_id, "limit": 100}
        )
        for fonte in response.json():
            if fonte['nicho_id'] == nicho_id:
                await client.delete(f"{API_BASE_URL}/fontes-trend/{fonte['id']}")

        # Remove nicho
        await client.delete(f"{API_BASE_URL}/nichos/{nicho_id}")
        print(f"  Removido nicho de teste")


async def main():
    print("=" * 60)
    print("VERIFICAÇÃO DA ETAPA 5 - COLETA DE TRENDS")
    print("=" * 60)

    # 1. Criar nicho
    print("\n=== Criando nicho de teste ===")
    nicho = await test_criar_nicho()
    print(f"Nicho criado: {nicho['nome']} (ID: {nicho['id']})")

    # 2. Configurar fontes
    fontes = await test_configurar_fontes(nicho['id'])

    # 3. Coletar trends
    resultado = await test_coletar_trends(nicho['id'])

    # 4. Listar trends
    por_fonte = await test_listar_trends(nicho['id'])

    # 5. Testar aprovação/rejeição
    await test_aprovar_rejeitar(nicho['id'])

    # 6. Resumo
    print("\n" + "=" * 60)
    print("RESUMO DA VERIFICAÇÃO")
    print("=" * 60)

    fontes_com_dados = [f for f, termos in por_fonte.items() if termos]
    print(f"\n1. Total de trends coletadas: {resultado['total_coletado']}")
    print(f"2. Fontes com dados: {len(fontes_com_dados)} ({', '.join(fontes_com_dados)})")
    print(f"3. Critério de pronto (≥2 fontes): {'✅ ATENDIDO' if len(fontes_com_dados) >= 2 else '❌ NÃO ATENDIDO'}")

    # Cleanup
    await cleanup(nicho['id'])

    if len(fontes_com_dados) >= 2:
        print("\n✅ Verificação da Etapa 5 concluída com sucesso!")
    else:
        print("\n⚠️ Verificação concluída, mas menos de 2 fontes retornaram dados")


if __name__ == "__main__":
    asyncio.run(main())
