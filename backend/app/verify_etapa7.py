"""
Verificação da Etapa 7 - Agente Roteirista

Este script:
1. Cria um nicho de teste
2. Cria uma ideia manual
3. Aprova a ideia
4. Gera um roteiro a partir da ideia aprovada
5. Verifica se o roteiro foi criado com status rascunho
6. Aprova o roteiro
7. Verifica se o status do roteiro e da ideia foram atualizados corretamente
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
                "slug": "teste-roteirista",
                "nome": "Teste Roteirista",
                "prompt_ideacao": "IA e tecnologia para criadores de conteúdo",
                "prompt_roteiro": "Crie roteiros dinâmicos e envolventes para vídeos sobre tecnologia e IA, com duração de 3-5 minutos",
            }
        )
        if response.status_code == 201:
            return response.json()
        elif response.status_code == 400:
            # Nicho já existe, buscar por slug
            response = await client.get(f"{API_BASE_URL}/nichos/")
            for nicho in response.json():
                if nicho["slug"] == "teste-roteirista":
                    return nicho
        response.raise_for_status()


async def test_criar_ideia(nicho_id: str):
    """Cria uma ideia manual."""
    print("\n=== Criando ideia ===")
    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.post(
            f"{API_BASE_URL}/ideias/",
            json={
                "titulo": "Como usar IA para criar vídeos automaticamente",
                "descricao": "Tutorial prático sobre ferramentas de IA para criação de conteúdo em vídeo",
                "nicho_id": nicho_id,
            }
        )
        if response.status_code == 201:
            ideia = response.json()
            print(f"  Ideia criada: {ideia['titulo'][:60]}...")
            print(f"  Status: {ideia['status']}")
            return ideia
        response.raise_for_status()


async def test_aprovar_ideia(ideia_id: str):
    """Aprova uma ideia."""
    print("\n=== Aprovando ideia ===")
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.patch(f"{API_BASE_URL}/ideias/{ideia_id}/aprovar")
        if response.status_code == 200:
            ideia = response.json()
            print(f"  Ideia aprovada: {ideia['titulo'][:60]}...")
            print(f"  Status: {ideia['status']}")
            return ideia
        print(f"  Erro: {response.status_code} - {response.text}")
        response.raise_for_status()


async def test_gerar_roteiro(ideia_id: str):
    """Gera roteiro a partir da ideia aprovada."""
    print("\n=== Gerando roteiro ===")
    async with httpx.AsyncClient(timeout=120.0) as client:
        response = await client.post(f"{API_BASE_URL}/ideias/{ideia_id}/roteiro")
        if response.status_code == 201:
            resultado = response.json()
            print(f"  Roteiro gerado: {resultado['titulo'][:60]}...")
            print(f"  Versão: {resultado['versao']}")
            print(f"  Duração: {resultado['duracao_total_segundos']}s")
            print(f"  Blocos: {resultado['num_blocos']}")
            print(f"  Status: {resultado['status']}")
            return resultado
        print(f"  Erro: {response.status_code} - {response.text}")
        response.raise_for_status()


async def test_listar_roteiros(status: str | None = None):
    """Lista roteiros."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        params = {"limit": 10}
        if status:
            params["status"] = status
        response = await client.get(f"{API_BASE_URL}/roteiros/", params=params)
        return response.json()


async def test_verificar_roteiro(roteiro_id: str):
    """Busca roteiro pelo ID."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.get(f"{API_BASE_URL}/roteiros/{roteiro_id}")
        if response.status_code == 200:
            return response.json()
        return None


async def test_aprovar_roteiro(roteiro_id: str):
    """Aprova um roteiro."""
    print("\n=== Aprovando roteiro ===")
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.patch(f"{API_BASE_URL}/roteiros/{roteiro_id}/aprovar")
        if response.status_code == 200:
            roteiro = response.json()
            print(f"  Roteiro aprovado: {roteiro['estrutura']['titulo'][:60]}...")
            print(f"  Status: {roteiro['status']}")
            return roteiro
        print(f"  Erro: {response.status_code} - {response.text}")
        response.raise_for_status()


async def test_verificar_ideia(ideia_id: str):
    """Busca ideia pelo ID."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.get(f"{API_BASE_URL}/ideias/{ideia_id}")
        if response.status_code == 200:
            return response.json()
        return None


async def cleanup(nicho_id: str, ideia_id: str, roteiro_id: str):
    """Remove dados de teste."""
    print("\n=== Limpando dados de teste ===")
    async with httpx.AsyncClient(timeout=30.0) as client:
        # Remove roteiro
        await client.delete(f"{API_BASE_URL}/roteiros/{roteiro_id}")
        print(f"  Removido roteiro de teste")

        # Remove ideia
        await client.delete(f"{API_BASE_URL}/ideias/{ideia_id}")
        print(f"  Removida ideia de teste")

        # Remove nicho
        await client.delete(f"{API_BASE_URL}/nichos/{nicho_id}")
        print(f"  Removido nicho de teste")


async def main():
    print("=" * 60)
    print("VERIFICAÇÃO DA ETAPA 7 - AGENTE ROTEIRISTA")
    print("=" * 60)

    # 1. Criar nicho
    print("\n=== Criando nicho de teste ===")
    nicho = await test_criar_nicho()
    print(f"Nicho criado: {nicho['nome']} (ID: {nicho['id']})")

    # 2. Criar ideia
    ideia = await test_criar_ideia(nicho['id'])
    ideia_id = ideia['id']

    # 3. Aprovar ideia
    await test_aprovar_ideia(ideia_id)

    # 4. Gerar roteiro
    resultado = await test_gerar_roteiro(ideia_id)
    roteiro_id = resultado['roteiro_id']

    # 5. Verificar roteiro criado
    print("\n=== Verificando roteiro criado ===")
    roteiro = await test_verificar_roteiro(roteiro_id)
    if roteiro:
        print(f"  Título: {roteiro['estrutura']['titulo'][:60]}...")
        print(f"  Status: {roteiro['status']}")
        print(f"  Blocos: {len(roteiro['estrutura']['blocos'])}")
        for i, bloco in enumerate(roteiro['estrutura']['blocos'][:3], 1):
            print(f"    {i}. {bloco['tipo']} ({bloco['duracao_segundos']}s)")

    # 6. Verificar roteiro em rascunho
    print("\n=== Verificando roteiro em rascunho ===")
    roteiro_rascunho = await test_verificar_roteiro(roteiro_id)
    roteiro_em_rascunho = roteiro_rascunho and roteiro_rascunho['status'] == 'rascunho'
    if roteiro_em_rascunho:
        print(f"  ✅ Roteiro está em rascunho")

    # 7. Aprovar roteiro
    roteiro_aprovado = await test_aprovar_roteiro(roteiro_id)

    # 8. Verificar roteiro aprovado
    print("\n=== Verificando roteiro aprovado ===")
    roteiro_pos_aprovacao = await test_verificar_roteiro(roteiro_id)
    if roteiro_pos_aprovacao:
        print(f"  Status do roteiro: {roteiro_pos_aprovacao['status']}")

    # 9. Verificar status da ideia após aprovação do roteiro
    print("\n=== Verificando status da ideia ===")
    ideia_atualizada = await test_verificar_ideia(ideia_id)
    if ideia_atualizada:
        print(f"  Status da ideia: {ideia_atualizada['status']}")

    # 10. Listar roteiros aprovados (prontos para produção)
    print("\n=== Listando roteiros prontos para produção ===")
    roteiros_aprovados = await test_listar_roteiros(status="aprovado")
    print(f"  Total de roteiros aprovados: {len(roteiros_aprovados)}")

    # 11. Resumo
    print("\n" + "=" * 60)
    print("RESUMO DA VERIFICAÇÃO")
    print("=" * 60)

    criterios = [
        ("Ideia aprovada vira roteiro em rascunho", roteiro_em_rascunho),
        ("Aprovação muda status para 'aprovado'", roteiro_pos_aprovacao and roteiro_pos_aprovacao['status'] == 'aprovado'),
        ("Ideia muda para 'roteirizada'", ideia_atualizada and ideia_atualizada['status'] == 'roteirizada'),
        ("Endpoint GET /roteiros?status=aprovado funciona", len(roteiros_aprovados) >= 1),
    ]

    todos_atendidos = True
    for criterio, atende in criterios:
        status = "✅ ATENDIDO" if atende else "❌ NÃO ATENDIDO"
        print(f"\n{criterio}: {status}")
        if not atende:
            todos_atendidos = False

    # Cleanup
    await cleanup(nicho['id'], ideia_id, roteiro_id)

    if todos_atendidos:
        print("\n✅ Verificação da Etapa 7 concluída com sucesso!")
    else:
        print("\n⚠️ Verificação concluída com pendências")


if __name__ == "__main__":
    asyncio.run(main())
