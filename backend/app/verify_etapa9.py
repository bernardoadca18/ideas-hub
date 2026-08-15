"""
Verificação da Etapa 9 - Observabilidade e Robustez

Este script verifica:
1. Logging estruturado está funcionando
2. Retry está configurado corretamente
3. Testes automatizados passam
"""
import subprocess
import sys


def check_logging_module():
    """Verifica se o módulo de logging existe e pode ser importado."""
    print("\n=== Verificando Módulo de Logging ===")
    try:
        from app.core.logging import (
            setup_logging,
            curador_logger,
            roteirista_logger,
            gerador_ideias_logger,
            AgentLogger,
            AgentMetrics,
        )
        print("✅ Módulo de logging importado com sucesso")
        print(f"   - curador_logger: {type(curador_logger).__name__}")
        print(f"   - roteirista_logger: {type(roteirista_logger).__name__}")
        print(f"   - gerador_ideias_logger: {type(gerador_ideias_logger).__name__}")
        return True
    except ImportError as e:
        print(f"❌ Erro ao importar módulo de logging: {e}")
        return False


def check_retry_module():
    """Verifica se o módulo de retry existe e pode ser importado."""
    print("\n=== Verificando Módulo de Retry ===")
    try:
        from app.core.retry import (
            retry_llm,
            retry_tavily,
            retry_api,
        )
        print("✅ Módulo de retry importado com sucesso")
        print(f"   - retry_llm: {retry_llm.__name__}")
        print(f"   - retry_tavily: {retry_tavily.__name__}")
        print(f"   - retry_api: {retry_api.__name__}")
        return True
    except ImportError as e:
        print(f"❌ Erro ao importar módulo de retry: {e}")
        return False


def check_agents_use_logging():
    """Verifica se os agentes usam logging."""
    print("\n=== Verificando Uso de Logging nos Agentes ===")

    agentes = {
        "curador": "app.agents.curador",
        "roteirista": "app.agents.roteirista",
        "gerador_ideias": "app.services.trends.gerador_ideias",
    }

    resultados = {}
    for nome, modulo in agentes.items():
        try:
            # Tenta importar e verificar se tem logger
            mod = __import__(modulo, fromlist=[""])
            if hasattr(mod, "curador_logger") or hasattr(mod, "roteirista_logger") or hasattr(mod, "gerador_ideias_logger"):
                print(f"✅ {nome}: usa logger")
                resultados[nome] = True
            else:
                # Verifica se importou o logger
                import inspect
                source = inspect.getsource(mod)
                if "logger" in source.lower() or "logging" in source.lower():
                    print(f"✅ {nome}: referências a logging encontradas")
                    resultados[nome] = True
                else:
                    print(f"⚠️ {nome}: não encontrou referências diretas a logging")
                    resultados[nome] = False
        except Exception as e:
            print(f"❌ {nome}: erro ao verificar - {e}")
            resultados[nome] = False

    return all(resultados.values())


def check_agents_use_retry():
    """Verifica se os agentes usam retry."""
    print("\n=== Verificando Uso de Retry nos Agentes ===")

    agentes = {
        "curador": "app.agents.curador",
        "roteirista": "app.agents.roteirista",
    }

    resultados = {}
    for nome, modulo in agentes.items():
        try:
            import inspect
            mod = __import__(modulo, fromlist=[""])
            source = inspect.getsource(mod)

            if "@retry" in source or "retry_llm" in source or "retry_tavily" in source:
                print(f"✅ {nome}: usa retry decorators")
                resultados[nome] = True
            else:
                print(f"⚠️ {nome}: não encontrou retry decorators")
                resultados[nome] = False
        except Exception as e:
            print(f"❌ {nome}: erro ao verificar - {e}")
            resultados[nome] = False

    return all(resultados.values())


def check_tests_exist():
    """Verifica se os testes existem."""
    print("\n=== Verificando Existência de Testes ===")

    test_files = [
        "/app/tests/agents/test_curador.py",
        "/app/tests/agents/test_roteirista.py",
        "/app/tests/repositories/test_repositories.py",
        "/app/tests/conftest.py",
    ]

    import os
    resultados = []
    for test_file in test_files:
        if os.path.exists(test_file):
            print(f"✅ {os.path.relpath(test_file, '/app')} existe")
            resultados.append(True)
        else:
            print(f"❌ {os.path.relpath(test_file, '/app')} não encontrado")
            resultados.append(False)

    return all(resultados)


def run_tests():
    """Executa os testes automatizados."""
    print("\n=== Executando Testes Automatizados ===")

    try:
        # Executa pytest
        result = subprocess.run(
            ["python", "-m", "pytest", "tests/", "-v", "--tb=short"],
            cwd="/app",
            capture_output=True,
            text=True,
            timeout=60
        )

        print(result.stdout)

        if result.returncode == 0:
            print("✅ Todos os testes passaram")
            return True
        else:
            print(f"⚠️ Alguns testes falharam (código: {result.returncode})")
            if result.stderr:
                print("STDERR:", result.stderr[:500])
            return False
    except subprocess.TimeoutExpired:
        print("⚠️ Timeout ao executar testes")
        return False
    except Exception as e:
        print(f"❌ Erro ao executar testes: {e}")
        return False


def check_requirements():
    """Verifica se as dependências estão instaladas."""
    print("\n=== Verificando Dependências ===")

    deps = ["structlog", "tenacity", "pytest", "pytest_asyncio"]

    resultados = []
    for dep in deps:
        try:
            __import__(dep)
            print(f"✅ {dep} instalado")
            resultados.append(True)
        except ImportError:
            print(f"❌ {dep} não instalado")
            resultados.append(False)

    return all(resultados)


def main():
    print("=" * 60)
    print("VERIFICAÇÃO DA ETAPA 9 - OBSERVABILIDADE E ROBUSTEZ")
    print("=" * 60)

    criterios = []

    # 1. Dependências
    deps_ok = check_requirements()
    criterios.append(("Dependências instaladas", deps_ok))

    # 2. Logging module
    logging_ok = check_logging_module()
    criterios.append(("Módulo de logging implementado", logging_ok))

    # 3. Retry module
    retry_ok = check_retry_module()
    criterios.append(("Módulo de retry implementado", retry_ok))

    # 4. Agentes usam logging
    agents_logging_ok = check_agents_use_logging()
    criterios.append(("Agentes usam logging estruturado", agents_logging_ok))

    # 5. Agentes usam retry
    agents_retry_ok = check_agents_use_retry()
    criterios.append(("Agentes usam retry", agents_retry_ok))

    # 6. Testes existem
    tests_exist_ok = check_tests_exist()
    criterios.append(("Testes automatizados criados", tests_exist_ok))

    # 7. Testes passam (opcional - pode falhar se dependências não instaladas)
    if deps_ok:
        tests_pass_ok = run_tests()
        criterios.append(("Testes automatizados passam", tests_pass_ok))
    else:
        criterios.append(("Testes automatizados passam", False))

    # Resumo
    print("\n" + "=" * 60)
    print("RESUMO DA VERIFICAÇÃO")
    print("=" * 60)

    todos_atendidos = True
    for criterio, atende in criterios:
        status = "✅ ATENDIDO" if atende else "❌ NÃO ATENDIDO"
        print(f"\n{criterio}: {status}")
        if not atende:
            todos_atendidos = False

    if todos_atendidos:
        print("\n✅ Verificação da Etapa 9 concluída com sucesso!")
        print("\nObservabilidade e robustez implementadas:")
        print("1. Logging estruturado nos 3 agentes")
        print("2. Retry com tenacity para LLM/Tavily/APIs")
        print("3. Testes automatizados dos repositórios e agentes")
    else:
        print("\n⚠️ Verificação concluída com pendências")
        print("\nAções necessárias:")
        if not deps_ok:
            print("- Instale as dependências: pip install structlog pytest pytest-asyncio pytest-mock")


if __name__ == "__main__":
    main()
