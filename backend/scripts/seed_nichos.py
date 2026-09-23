"""
Script de seed idempotente para popular a tabela de nichos.

Uso: python -m scripts.seed_nichos

Cada nicho é criado ou atualizado pelo slug, permitindo rodar múltiplas vezes
sem duplicação. Os prompts são específicos de cada nicho e complementam (não
repetem) as orientações já presentes nos ProductionProfiles.
"""

import asyncio

from app.core.database import AsyncSessionLocal
from app.repositories import NichoRepository
from app.schemas import NichoCreate, NichoUpdate

# Dados dos nichos a criar/atualizar
# Cada entrada contém slug, nome, descricao, perfil_producao, categoria_google_trends,
# e os prompts específicos do nicho (que complementam, não repetem, o perfil).

NICHOS_DATA = [
    {
        "slug": "pov_storyboard", "nome": "POV / Histórias em primeira pessoa",
        "descricao": "Histórias de autoria externa importadas em JSON com storyboard.",
        "perfil_producao": "pov_storyboard", "categoria_google_trends": None,
        "prompt_ideacao": "Autoria externa. Importe JSON manual.",
        "prompt_roteiro": "Autoria externa. Importe neovids_pov_script_v1.",
    },
    {
        "slug": "cultura_pop",
        "nome": "Cultura Pop — Listas e Explicações",
        "descricao": (
            "Filmes, séries, games, quadrinhos, universos ficcionais, lore, personagens, "
            "eventos. Formatos principais: listas estruturadas, rankings, breakdowns de "
            "facções/grupos/equipamentos, explicação de conceitos de lore. Nicho com foco "
            "em universos populares como Marvel, DC, Star Wars, anime, games AAA."
        ),
        "perfil_producao": "faceless_pop_culture_lists",
        "categoria_google_trends": "Entertainment",
        "prompt_ideacao": (
            "Ângulos preferidos para este nicho: explicação de membros de um grupo/facção "
            "(ex.: 'os 7 membros originais dos Vingadores explicados'), breakdown de itens/objetos "
            "de um universo (ex.: 'todas as Joias do Infinito explicadas'), comparações de poder "
            "ou hierarquia dentro de um universo, origens de personagens, guias de lore para "
            "iniciantes. Evite títulos genéricos como 'tudo sobre X' — prefira recortes específicos "
            "que prometam uma entrega clara e verificável. Ângulos crossover (ex.: 'poderes de "
            "personagens de universos diferentes comparados') são válidos quando há base factual "
            "suficiente, mas devem ser sinalizados como especulação comparativa, não como canônicos."
        ),
        "prompt_roteiro": (
            "Para listas/rankings: cada item precisa de introdução clara, desenvolvimento com "
            "detalhes relevantes de lore/continuidade, e fechamento que conecte ao próximo item "
            "quando possível. Ordene estrategicamente (crescente em impacto, ou por tema) — nunca "
            "pela ordem aleatória em que a informação foi encontrada. Evite spoilers de eventos "
            "recentes sem aviso. Diferencie fato canônico de teoria de fandom explicitamente. "
            "Para breakdowns de grupos/facções: inclua papel no universo, membros conhecidos, "
            "eventos marcantes, e status atual (se aplicável)."
        ),
    },
    {
        "slug": "tecnologia",
        "nome": "Tecnologia e Computação",
        "descricao": (
            "Tecnologia, computação, engenharia, curiosidades técnicas. Foco em explicar "
            "conceitos, comparar tecnologias, contar histórias de desenvolvimento de produtos "
            "e empresas. Conteúdo educacional com rigor factual em números, specs e datas."
        ),
        "perfil_producao": "faceless_informational",
        "categoria_google_trends": "Technology",
        "prompt_ideacao": (
            "Ângulos preferidos: comparações técnicas entre produtos/tecnologias concorrentes "
            "(ex.: 'M1 vs Snapdragon: a batalha dos chips mobile'), história de desenvolvimento "
            "de uma tecnologia (ex.: 'como o Bluetooth surgiu e evoluiu'), explicações de "
            "conceitos técnicos para leigos (ex.: 'como funciona machine learning na prática'), "
            "curiosidades de engenharia com 'porquê importa' claro. Evite notícias efêmeras "
            "que perdem relevância em dias — prefira temas com longevidade. Não cubra rumours "
            "de produtos não anunciados como se fossem fatos."
        ),
        "prompt_roteiro": (
            "Precisão é obrigatória: números, specs, datas e afirmações técnicas precisam "
            "ser verificados via grounding. Ao citar benchmarks ou comparações, deixe claro "
            "o contexto (hardware usado, versão de software, condições de teste). Explique "
            "jargão técnico na primeira aparição de forma concisa — não assuma conhecimento "
            "prévio, mas também não se alongue demais. Evite correlação apresentada como "
            "causalidade. Estrutura preferida: contexto do problema/tecnologia → explicação "
            "técnica → impacto prático → conclusão com perspectiva futura quando relevante."
        ),
    },
    {
        "slug": "ciencia",
        "nome": "Ciência e Curiosidades Científicas",
        "descricao": (
            "Física, biologia, astronomia, química, geologia, neurociência, medicina. "
            "Descobertas, fenômenos naturais, curiosidades científicas com rigor factual. "
            "Conteúdo educacional que torna ciência acessível sem simplificar demais."
        ),
        "perfil_producao": "faceless_informational",
        "categoria_google_trends": "Science",
        "prompt_ideacao": (
            "Ângulos preferidos: fenômenos naturais explicados (ex.: 'por que o céu muda de cor "
            "durante o pôr do sol'), descobertas recentes com contexto de porquê importam, "
            "comparações de escala (ex.: 'tamanhos de estrelas comparados'), histórias de "
            "descobertas científicas e seus impactos. Evite sensacionalismo — não apresente "
            "descobertas preliminares como verdades estabelecidas. Diferencie teoria científica "
            "de uso cotidiano da palavra 'teoria'."
        ),
        "prompt_roteiro": (
            "Use metáforas e analogias para tornar conceitos abstratos acessíveis, mas sempre "
            "qualifique que são metáforas. Cite fontes ou estudos quando relevante, especialmente "
            "para descobertas recentes. Evite apresentar hipóteses como fatos comprovados — use "
            "'acredita-se que', 'a hipótese mais aceita é', 'estudos sugerem' quando apropriado. "
            "Para fenômenos naturais: contexto → explicação do mecanismo → exemplos visuais "
            "concretos → aplicações práticas ou curiosidades adicionais."
        ),
    },
    {
        "slug": "historia",
        "nome": "História e Eventos Históricos",
        "descricao": (
            "Eventos históricos, períodos, personagens, civilizações, guerras, movimentos. "
            "Foco em eventos pouco conhecidos e perspectivas alternativas sobre marcos "
            "conhecidos. Estrutura narrativa que conecta causa, evento e consequência."
        ),
        "perfil_producao": "faceless_informational",
        "categoria_google_trends": None,  # Não há categoria específica de história no Google Trends
        "prompt_ideacao": (
            "Ângulos preferidos: eventos pouco conhecidos com impacto surpreendente, conexões "
            "entre eventos históricos aparentemente não relacionados, biografias de figuras "
            "históricas negligenciadas, explicações de como instituições/tradições surgiram, "
            "comparações de períodos ou civilizações. Evite recortes já exaustivamente cobertos "
            "sem um ângulo novo. Prefira histórias com arco narrativo claro (problema → conflito → "
            "resolução → consequências). Não romantize figuras históricas — apresente nuances."
        ),
        "prompt_roteiro": (
            "Use estrutura de timeline quando o evento se desenrola ao longo do tempo, ou "
            "causa-consequência quando o foco é entender por que algo aconteceu e suas "
            "repercussões. Contextualize a época (o que era normal naquele período, não julgue "
            "com lentes exclusivamente modernas). Cite fontes primárias ou historiadores quando "
            "disponível. Evite anacronismos. Conecte eventos históricos ao presente quando "
            "houver linha direta de influência, mas não force conexões artificiais."
        ),
    },
    {
        "slug": "futebol",
        "nome": "Futebol — Estatísticas e Análise",
        "descricao": (
            "Estatísticas, análise técnica, história de clubes e jogadores, táticas, recordes. "
            "Foco em dados verificáveis e análises fundamentadas, não em especulação "
            "transferência ou fofoca. Perfil informational: estatísticas e fatos históricos "
            "têm prioridade sobre narrativas sensacionalistas."
        ),
        "perfil_producao": "faceless_informational",
        "categoria_google_trends": "Sports",
        "prompt_ideacao": (
            "Ângulos preferidos: comparações estatísticas entre jogadores/épocas (com contexto "
            "de mudanças de regras e estilo de jogo), evolução tática de times ou ligas, recordes "
            "e marcas históricas explicadas, histórias de clubes ou jogadores menos conhecidos, "
            "análise de decisões táticas marcantes. Evite rumores de transferência, fofoca de "
            "jogadores, ou conteúdo que perde relevância em dias. Não cubra resultados de jogos "
            "recentes como tema principal — o foco é análise e história, não notícia."
        ),
        "prompt_roteiro": (
            "Ao comparar estatísticas entre épocas, sempre contextualize: mudanças de regras, "
            "número de jogos, nível da liga, etc. Não apresente stats brutas como verdade "
            "absoluta sem contexto. Cite fontes de dados quando relevante. Para análises "
            "táticas, explique o 'porquê' da decisão, não apenas o 'o quê'. Evite comparar "
            "jogadores de posições muito diferentes como se fossem equivalentes. Tom objetivo, "
            "sem paixão clubística aparente."
        ),
    },
    {
        "slug": "financas",
        "nome": "Educação Financeira e Economia",
        "descricao": (
            "Educação financeira, conceitos econômicos, curiosidades sobre dinheiro e mercados, "
            "história de empresas e crashes financeiros. CONTEÚDO EXCLUSIVAMENTE EDUCACIONAL — "
            "NÃO é aconselhamento financeiro personalizado nem recomendação de investimento."
        ),
        "perfil_producao": "faceless_informational",
        "categoria_google_trends": "Finance",
        "prompt_ideacao": (
            "Ângulos preferidos: explicação de conceitos financeiros para leigos (ex.: 'o que "
            "é inflação e como afeta seu bolso'), história de crashes financeiros e lições "
            "aprendidas, como funcionam instrumentos financeiros (CDB, Tesouro, ações, FIIs), "
            "curiosidades econômicas com impacto real. NUNCA gere ideias que prometam 'dicas "
            "de como enriquecer', 'ações para comprar agora', ou previsões de mercado como "
            "certezas. Conteúdo educacional sobre mecânica e história, não recomendação."
        ),
        "prompt_roteiro": (
            "REGRA CRÍTICA: Este canal NÃO oferece aconselhamento financeiro personalizado. "
            "Todo conteúdo é educacional/informativo. NUNCA apresente previsões de mercado, "
            "preços futuros de ativos, ou recomendações de compra/venda como certezas ou como "
            "se fossem aplicáveis à situação específica do espectador. Use linguagem como "
            "'historicamente...', 'em geral...', 'depende do seu perfil...' quando tratar "
            "de estratégias. Cite fontes de dados financeiros. Explique riscos de qualquer "
            "instrumento ou estratégia mencionada. Disclaimers são bem-vindos quando apropriado."
        ),
    },
    {
        "slug": "gta6_rockstar",
        "nome": "GTA 6 e Universo Rockstar Games",
        "descricao": (
            "Notícias, teorias, trailers, easter eggs e detalhes de GTA 6 e do universo "
            "Rockstar Games. Cuidado redobrado com rumores vs. fatos oficiais devido ao "
            "status de jogo ainda não lançado."
        ),
        "perfil_producao": "faceless_pop_culture_lists",
        "categoria_google_trends": "Games",
        "prompt_ideacao": (
            "Ângulos preferidos: breakdown de trailers oficiais (detalhes, referências, "
            "conexões com jogos anteriores), easter eggs confirmados em materiais divulgados, "
            "comparações com GTA V e outros jogos Rockstar, histórico da franquia e evolução, "
            "análise de mapas e locações baseadas em material oficial. ATENÇÃO: como o jogo "
            "ainda não foi lançado, RUMOR e FATO se confundem facilmente. Sempre qualifique "
            "a fonte: 'confirmado pela Rockstar', 'segundo vazamento não verificado', 'teoria "
            "baseada em indícios no trailer'. Evite apresentar especulação como fato. Nicho "
            "com potencial de cobertura contínua pós-lançamento."
        ),
        "prompt_roteiro": (
            "Sempre diferencie: informação oficial da Rockstar, vazamento com credibilidade "
            "estabelecida (citar fonte), e teoria/especulação de fãs. Use 'segundo a Rockstar...', "
            "'vazamentos sugerem...', 'fãs teorizam que...' para deixar claro o nível de "
            "certeza. Ao analisar trailers, descreva o que está visível antes de interpretar. "
            "Evite perpetuar rumores desmentidos. Conexões com jogos anteriores da Rockstar "
            "são bem-vindas quando fundamentadas. Estrutura preferida: contexto (histórico da "
            "franquia) → análise do material disponível → teorias qualificadas → conclusão "
            "com perspectiva de atualização quando houver novos desenvolvimentos."
        ),
    },
    {
        "slug": "analise_jogos",
        "nome": "Análise de Jogos (a partir de Gameplay)",
        "descricao": (
            "Vídeos de análise baseados na experiência real de jogar, gravada e anotada pelo "
            "autor. Este nicho NÃO passa pelo workflow de ideação/curadoria automática — "
            "é consumido via endpoint dedicado POST /roteiros/analise-jogo."
        ),
        "perfil_producao": "game_analysis",
        "categoria_google_trends": None,
        "prompt_ideacao": (
            "Este nicho não utiliza ideação automática via trends/curadoria. As análises são "
            "geradas a partir de anotações de gameplay fornecidas pelo autor. Não crie ideias "
            "para este nicho via workflow padrão."
        ),
        "prompt_roteiro": (
            "Preferências de tom para análises neste canal: equilíbrio entre aspectos técnicos "
            "(performance, mecânicas, design de níveis) e narrativos (história, personagens, "
            "world-building), com foco no que as anotações efetivamente sustentam. Nível de "
            "humor: sutil e contextual, não forçado. Evite linguagem excessivamente informal "
            "ou slang que envelhece mal. Críticas devem ser específicas e justificadas nas "
            "anotações, não genéricas. Preserve a voz do autor — o agente estrutura e edita, "
            "não impõe opiniões próprias."
        ),
    },
]


async def seed_nichos():
    """
    Cria ou atualiza nichos de forma idempotente.

    Para cada nicho em NICHOS_DATA:
    - Se o slug já existe: atualiza os campos
    - Se não existe: cria novo nicho
    """
    async with AsyncSessionLocal() as session:
        repo = NichoRepository(session)

        created_count = 0
        updated_count = 0

        print("=" * 60)
        print("Seed de Nichos - Ideas Hub")
        print("=" * 60)

        for nicho_data in NICHOS_DATA:
            slug = nicho_data["slug"]
            existing = await repo.get_by_slug(slug)

            if existing:
                # Atualizar nicho existente
                update_data = NichoUpdate(
                    nome=nicho_data["nome"],
                    descricao=nicho_data["descricao"],
                    prompt_ideacao=nicho_data["prompt_ideacao"],
                    prompt_roteiro=nicho_data["prompt_roteiro"],
                    perfil_producao=nicho_data["perfil_producao"],
                    categoria_google_trends=nicho_data.get("categoria_google_trends"),
                    ativo=True,
                )
                await repo.update(existing.id, update_data)
                updated_count += 1
                print(f"✓ Atualizado: {slug} (perfil: {nicho_data['perfil_producao']})")
            else:
                # Criar novo nicho
                create_data = NichoCreate(
                    slug=slug,
                    nome=nicho_data["nome"],
                    descricao=nicho_data["descricao"],
                    prompt_ideacao=nicho_data["prompt_ideacao"],
                    prompt_roteiro=nicho_data["prompt_roteiro"],
                    perfil_producao=nicho_data["perfil_producao"],
                    categoria_google_trends=nicho_data.get("categoria_google_trends"),
                    ativo=True,
                )
                await repo.create(create_data)
                created_count += 1
                print(f"✓ Criado: {slug} (perfil: {nicho_data['perfil_producao']})")

        print("=" * 60)
        print(f"Total: {created_count} criados, {updated_count} atualizados")
        print("=" * 60)


if __name__ == "__main__":
    asyncio.run(seed_nichos())
