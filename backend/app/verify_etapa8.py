"""
Verificação da Etapa 8 - Frontend

Este script verifica se o fluxo completo está operável:
1. Backend API funcionando
2. Frontend acessível
3. Endpoints principais respondendo
4. Fluxo de criação de ideia até roteiro aprovado
"""
import asyncio
import httpx

from app.core.config import settings


API_BASE_URL = f"http://localhost:{settings.api_port}"
FRONTEND_URL = "http://localhost:5173"


async def test_backend_health():
    """Verifica se o backend está saudável."""
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            response = await client.get(f"{API_BASE_URL}/health")
            return response.status_code == 200
        except Exception:
            return False


async def test_frontend_accessible():
    """Verifica se o frontend está acessível (dentro da rede Docker)."""
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            # Usa o nome do container na rede Docker
            response = await client.get("http://ideas-hub-frontend:5173")
            return response.status_code == 200
        except Exception:
            # Tenta localhost também
            try:
                response = await client.get("http://localhost:5173")
                return response.status_code == 200
            except Exception:
                return False


async def test_endpoints_responding():
    """Verifica se os endpoints principais estão respondendo."""
    async with httpx.AsyncClient(timeout=10.0) as client:
        endpoints = [
            ("/nichos/", "GET"),
            ("/ideias/", "GET"),
            ("/trends/", "GET"),
            ("/roteiros/", "GET"),
        ]

        results = {}
        for path, method in endpoints:
            try:
                if method == "GET":
                    response = await client.get(f"{API_BASE_URL}{path}")
                results[path] = response.status_code in [200, 201]
            except Exception:
                results[path] = False

        return results


async def test_full_flow():
    """Testa o fluxo completo: nicho → ideia → aprovação → roteiro → aprovação."""
    print("\n=== Testando fluxo completo ===")

    async with httpx.AsyncClient(timeout=120.0) as client:
        # 1. Criar/Buscar nicho
        print("\n1. Verificando nichos...")
        response = await client.get(f"{API_BASE_URL}/nichos/")
        nichos = response.json()

        if not nichos:
            print("  Criando nicho de teste...")
            response = await client.post(
                f"{API_BASE_URL}/nichos/",
                json={
                    "slug": "teste-fluxo-frontend",
                    "nome": "Teste Fluxo Frontend",
                    "prompt_ideacao": "IA e tecnologia para criadores de conteúdo",
                    "prompt_roteiro": "Crie roteiros dinâmicos e envolventes",
                }
            )
            nicho = response.json()
        else:
            nicho = nichos[0]

        print(f"  ✅ Nicho: {nicho['nome']}")

        # 2. Criar ideia
        print("\n2. Criando ideia...")
        response = await client.post(
            f"{API_BASE_URL}/ideias/",
            json={
                "titulo": "Teste frontend - como usar IA para vídeos",
                "descricao": "Teste do fluxo completo via frontend",
                "nicho_id": nicho["id"],
            }
        )
        if response.status_code not in [200, 201]:
            print(f"  ⚠️ Erro ao criar ideia: {response.text}")
            return False

        ideia = response.json()
        print(f"  ✅ Ideia criada: {ideia['titulo'][:50]}... (status: {ideia['status']})")

        # 3. Aprovar ideia
        print("\n3. Aprovando ideia...")
        response = await client.patch(f"{API_BASE_URL}/ideias/{ideia['id']}/aprovar")
        if response.status_code != 200:
            print(f"  ⚠️ Erro ao aprovar ideia: {response.text}")
            return False

        ideia = response.json()
        print(f"  ✅ Ideia aprovada (status: {ideia['status']})")

        # 4. Gerar roteiro
        print("\n4. Gerando roteiro...")
        response = await client.post(f"{API_BASE_URL}/ideias/{ideia['id']}/roteiro")
        if response.status_code not in [200, 201]:
            print(f"  ⚠️ Erro ao gerar roteiro: {response.text}")
            return False

        resultado = response.json()
        roteiro_id = resultado['roteiro_id']
        print(f"  ✅ Roteiro gerado (versão: {resultado['versao']}, status: {resultado['status']})")

        # 5. Verificar roteiro
        print("\n5. Verificando roteiro...")
        response = await client.get(f"{API_BASE_URL}/roteiros/{roteiro_id}")
        roteiro = response.json()
        print(f"  ✅ Roteiro: {roteiro['estrutura']['titulo'][:50]}...")
        print(f"     Blocos: {len(roteiro['estrutura']['blocos'])}")
        print(f"     Status: {roteiro['status']}")

        # 6. Aprovar roteiro
        print("\n6. Aprovando roteiro...")
        response = await client.patch(f"{API_BASE_URL}/roteiros/{roteiro_id}/aprovar")
        if response.status_code != 200:
            print(f"  ⚠️ Erro ao aprovar roteiro: {response.text}")
            return False

        roteiro = response.json()
        print(f"  ✅ Roteiro aprovado (status: {roteiro['status']})")

        # 7. Verificar ideia atualizada
        print("\n7. Verificando status final da ideia...")
        response = await client.get(f"{API_BASE_URL}/ideias/{ideia['id']}")
        ideia_final = response.json()
        print(f"  ✅ Ideia final: {ideia_final['status']}")

        # 8. Cleanup
        print("\n8. Limpando dados de teste...")
        await client.delete(f"{API_BASE_URL}/roteiros/{roteiro_id}")
        await client.delete(f"{API_BASE_URL}/ideias/{ideia['id']}")
        print("  ✅ Dados de teste removidos")

        # Verifica critérios
        criterios = [
            ideia['status'] == 'rascunho',
            ideia_final['status'] == 'roteirizada',
            roteiro['status'] == 'aprovado',
        ]

        return all(criterios)


async def main():
    print("=" * 60)
    print("VERIFICAÇÃO DA ETAPA 8 - FRONTEND")
    print("=" * 60)

    # 1. Backend health
    print("\n=== Verificando Backend ===")
    backend_ok = await test_backend_health()
    print(f"Backend saúde: {'✅ OK' if backend_ok else '❌ FALHOU'}")

    # 2. Frontend accessible
    print("\n=== Verificando Frontend ===")
    frontend_ok = await test_frontend_accessible()
    print(f"Frontend acessível: {'✅ OK' if frontend_ok else '❌ FALHOU'}")

    # 3. Endpoints responding
    print("\n=== Verificando Endpoints ===")
    endpoints_ok = await test_endpoints_responding()
    for endpoint, ok in endpoints_ok.items():
        print(f"  {endpoint}: {'✅ OK' if ok else '❌ FALHOU'}")

    # 4. Full flow
    flow_ok = await test_full_flow()

    # Summary
    print("\n" + "=" * 60)
    print("RESUMO DA VERIFICAÇÃO")
    print("=" * 60)

    criterios = [
        ("Backend API funcionando", backend_ok),
        ("Frontend acessível", frontend_ok),
        ("Todos endpoints respondendo", all(endpoints_ok.values())),
        ("Fluxo completo operável", flow_ok),
    ]

    todos_atendidos = True
    for criterio, atende in criterios:
        status = "✅ ATENDIDO" if atende else "❌ NÃO ATENDIDO"
        print(f"\n{criterio}: {status}")
        if not atende:
            todos_atendidos = False

    if todos_atendidos:
        print("\n✅ Verificação da Etapa 8 concluída com sucesso!")
        print("\nO fluxo completo está operável sem tocar no Swagger:")
        print("1. Acesse http://localhost:5173")
        print("2. Tela Ideias: crie ideias, aprove, gere roteiros")
        print("3. Tela Trends: aprove/rejeite trends em lote")
        print("4. Tela Roteiros: revise e aprove roteiros")
    else:
        print("\n⚠️ Verificação concluída com pendências")


if __name__ == "__main__":
    asyncio.run(main())
