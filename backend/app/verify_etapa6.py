"""
Verificação da Etapa 6 - Geração de Ideias a partir de Trends

Este script:
1. Cria um nicho de teste
2. Coleta trends
3. Aprova uma trend
4. Gera ideias a partir da trend aprovada
5. Verifica se as ideias foram criadas com status rascunho
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
                "slug": "teste-ideias-trends",
                "nome": "Teste Ideias Trends",
                "prompt_ideacao": "IA e tecnologia para criadores de conteúdo",
                "prompt_roteiro": "Crie roteiros detalhados para vídeos sobre IA",
            }
        )
        if response.status_code == 201:
            return response.json()
        elif response.status_code == 400:
            # Nicho já existe, buscar por slug
            response = await client.get(f"{API_BASE_URL}/nichos/")
            for nicho in response.json():
                if nicho["slug"] == "teste-ideias-trends":
                    return nicho
        response.raise_for_status()


async def test_configurar_fontes(nicho_id: str):
    """Configura fontes de trend para o nicho."""
    print("\n=== Configurando fontes de trend ===")

    async with httpx.AsyncClient(timeout=30.0) as client:
        # RSS - TechCrunch (mais confiável)
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
        else:
            print(f"  ⚠️ Erro ao configurar RSS: {response.status_code}")


async def test_coletar_trends(nicho_id: str):
    """Coleta trends para o nicho."""
    print("\n=== Coletando trends ===")

    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.post(
            f"{API_BASE_URL}/trends/coletar",
            json={
                "nicho_id": nicho_id,
                "termos_adicionais": ["inteligência artificial"]
            }
        )

        if response.status_code != 201:
            print(f"Erro: {response.status_code} - {response.text}")
            response.raise_for_status()

        resultado = response.json()
        print(f"  Total coletado: {resultado['total_coletado']}")
        return resultado


async def test_aprovar_trend(nicho_id: str):
    """Aprova uma trend para geração de ideias."""
    print("\n=== Aprovando trend ===")

    async with httpx.AsyncClient(timeout=30.0) as client:
        # Busca trends pendentes
        response = await client.get(
            f"{API_BASE_URL}/trends/",
            params={"nicho_id": nicho_id, "status": "pendente", "limit": 1}
        )
        trends = response.json()

        if not trends:
            print("  ⚠️ Nenhuma trend pendente encontrada")
            return None

        trend = trends[0]
        print(f"  Trend: {trend['termo_bruto'][:60]}...")

        # Aprova a trend
        response = await client.patch(f"{API_BASE_URL}/trends/{trend['id']}/aprovar")
        if response.status_code == 200:
            print(f"  ✅ Trend aprovada")
            return trend

        return None


async def test_gerar_ideias(trend_id: str, num_ideias: int = 3):
    """Gera ideias a partir da trend aprovada."""
    print(f"\n=== Gerando {num_ideias} ideias a partir da trend ===")

    async with httpx.AsyncClient(timeout=120.0) as client:
        response = await client.post(
            f"{API_BASE_URL}/trends/{trend_id}/gerar-ideias",
            params={"num_ideias": num_ideias}
        )

        if response.status_code != 201:
            print(f"Erro: {response.status_code} - {response.text}")
            response.raise_for_status()

        resultado = response.json()
        print(f"\nResultado da geração:")
        print(f"  Trend: {resultado['termo_trend'][:60]}...")
        print(f"  Ideias geradas: {resultado['ideias_geradas']}")
        if resultado.get('erros'):
            print(f"  Erros: {resultado['erros']}")

        return resultado


async def test_listar_ideias(nicho_id: str, trend_id: str):
    """Lista ideias geradas."""
    print("\n=== Listando ideias geradas ===")

    async with httpx.AsyncClient(timeout=30.0) as client:
        # Busca ideias do nicho
        response = await client.get(
            f"{API_BASE_URL}/ideias/",
            params={"nicho_id": nicho_id, "origem": "trend", "limit": 20}
        )
        response.raise_for_status()

        ideias = response.json()
        print(f"\nTotal de ideias: {len(ideias)}")

        # Filtra ideias da trend específica
        ideias_trend = [i for i in ideias if i.get('fonte_trend_id') == trend_id]

        for i, ideia in enumerate(ideias_trend[:5], 1):
            print(f"\n  Ideia {i}:")
            print(f"    Título: {ideia['titulo'][:70]}...")
            print(f"    Status: {ideia['status']}")
            if ideia.get('descricao_breve'):
                print(f"    Descrição: {ideia['descricao_breve'][:80]}...")

        return ideias_trend


async def cleanup(nicho_id: str):
    """Remove dados de teste."""
    print("\n=== Limpando dados de teste ===")
    async with httpx.AsyncClient(timeout=30.0) as client:
        # Remove ideias
        response = await client.get(
            f"{API_BASE_URL}/ideias/",
            params={"nicho_id": nicho_id, "limit": 100}
        )
        ideias = response.json()
        for ideia in ideias:
            await client.delete(f"{API_BASE_URL}/ideias/{ideia['id']}")
        print(f"  Removidas {len(ideias)} ideias")

        # Remove trends
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
    print("VERIFICAÇÃO DA ETAPA 6 - GERAÇÃO DE IDEIAS A PARTIR DE TRENDS")
    print("=" * 60)

    # 1. Criar nicho
    print("\n=== Criando nicho de teste ===")
    nicho = await test_criar_nicho()
    print(f"Nicho criado: {nicho['nome']} (ID: {nicho['id']})")

    # 2. Configurar fontes
    await test_configurar_fontes(nicho['id'])

    # 3. Coletar trends
    await test_coletar_trends(nicho['id'])

    # 4. Aprovar uma trend
    trend = await test_aprovar_trend(nicho['id'])
    if not trend:
        print("\n❌ Não foi possível aprovar uma trend para teste")
        return

    # 5. Gerar ideias a partir da trend
    num_ideias = settings.ideias_por_trend
    resultado = await test_gerar_ideias(trend['id'], num_ideias)

    # 6. Listar ideias geradas
    ideias = await test_listar_ideias(nicho['id'], trend['id'])

    # 7. Resumo
    print("\n" + "=" * 60)
    print("RESUMO DA VERIFICAÇÃO")
    print("=" * 60)

    ideias_rascunho = [i for i in ideias if i['status'] == 'rascunho']

    print(f"\n1. Trend aprovada: {trend['termo_bruto'][:50]}...")
    print(f"2. Ideias geradas: {resultado['ideias_geradas']}")
    print(f"3. Ideias com status 'rascunho': {len(ideias_rascunho)}")
    print(f"4. Critério de pronto (N ideias rascunho): {'✅ ATENDIDO' if len(ideias_rascunho) >= 1 else '❌ NÃO ATENDIDO'}")

    # Cleanup
    await cleanup(nicho['id'])

    if len(ideias_rascunho) >= 1:
        print("\n✅ Verificação da Etapa 6 concluída com sucesso!")
    else:
        print("\n⚠️ Verificação concluída, mas nenhuma ideia foi gerada")


if __name__ == "__main__":
    asyncio.run(main())
