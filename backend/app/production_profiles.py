"""
Registro de Production Profiles do Ideas Hub.

Um ProductionProfile descreve *como* um canal/nicho quer que a ideação e a
roteirização se comportem: política de duração, estrutura sugerida (não
rígida), regras editoriais e qual workflow de roteiro ele usa por padrão.

Isso não é uma tabela de banco de propósito: perfis são comportamento de
código (prompts + regras), enquanto o Nicho continua sendo o dado editável
pelo usuário (nome, prompts livres, fontes de trend). Adicionar um novo
perfil = adicionar uma entrada aqui.
"""

import hashlib
import json
from dataclasses import asdict, dataclass, field


@dataclass(frozen=True, slots=True)
class VisualRequirementsPolicy:
    """Profile-owned visual density and readiness contract."""

    target_beat_seconds: int = 30
    max_beats_per_llm_call: int = 5
    requires_visual_queries_for_final: bool = True
    version: str = "visual_requirements_v2"

    def __post_init__(self) -> None:
        if self.target_beat_seconds <= 0 or self.max_beats_per_llm_call <= 0:
            raise ValueError("visual requirements policy limits must be positive")

    @property
    def identity(self) -> str:
        payload = json.dumps(asdict(self), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode()).hexdigest()


@dataclass(frozen=True)
class SourceMatchRule:
    """Versionable source rule prepared for host/path/account-level policies."""

    host: str
    path_prefix: str | None = None
    account: str | None = None


@dataclass(frozen=True)
class SourceSearchRule:
    """Topic-scoped primary-source search guidance owned by source policy."""

    topic_terms: tuple[str, ...]
    query_suffix: str


@dataclass(frozen=True)
class SourcePolicy:
    """Deterministic source classification and grounding policy.

    Domain lists are intentionally profile configuration rather than provider/model
    judgments. An empty list means "unknown", never implicitly trustworthy.
    """

    # Small configurable official registry for the current production vertical.
    # YouTube is official only for an explicit publisher path, never by host alone.
    primary_domains: tuple[str, ...] = (
        "rockstargames.com",
        "take2games.com",
    )
    primary_sources: tuple[SourceMatchRule, ...] = (
        SourceMatchRule(
            host="youtube.com",
            path_prefix="/@rockstargames",
            account="rockstargames",
        ),
    )
    primary_search_rules: tuple[SourceSearchRule, ...] = (
        SourceSearchRule(
            topic_terms=("gta", "grand theft auto", "rockstar"),
            query_suffix="site:rockstargames.com",
        ),
    )
    # Small, host-owned baseline for the current production vertical. These outlets
    # may support reported claims; they never promote a claim to confirmed.
    reliable_domains: tuple[str, ...] = (
        "reuters.com",
        "bloomberg.com",
        "bbc.com",
        "theverge.com",
        "gamesindustry.biz",
        "ign.com",
        "digitalfoundry.net",
    )
    # A path may intentionally opt out of a host-wide authority rating. This keeps
    # editorial articles and community-maintained areas on the same host distinct.
    unverified_sources: tuple[SourceMatchRule, ...] = (
        SourceMatchRule(host="ign.com", path_prefix="/wikis"),
    )
    reliable_sources: tuple[SourceMatchRule, ...] = (
        SourceMatchRule(host="eurogamer.net", path_prefix="/digitalfoundry"),
    )
    community_domains: tuple[str, ...] = (
        "reddit.com",
        "facebook.com",
        "instagram.com",
        "youtube.com",
        "youtu.be",
    )
    unknown_default: str = "unverified"
    grounding_required: bool = True
    minimum_claims: int = 1
    version: str = "source_policy_v6"


@dataclass(frozen=True)
class DurationPolicy:
    """Versioned editorial duration contract for a production profile."""

    min_seconds: int | None
    target_min_seconds: int | None
    target_max_seconds: int | None
    default_target_seconds: int | None = None
    content_driven_allowed: bool = False
    hard_minimum: bool = (
        False  # se True, o serviço aplica um piso técnico (evitar micro-vídeos)
    )
    allow_extended: bool = True  # se o assunto justificar, pode passar do alvo
    guidance: str = ""  # texto extra para o prompt sobre como tratar duração
    excellent_tolerance_ratio: float = 0.08
    acceptable_tolerance_ratio: float = 0.15

    def as_prompt_text(self) -> str:
        if self.target_min_seconds is None and self.target_max_seconds is None:
            base = (
                "Não existe duração-alvo fixa para este formato. A duração final deve ser "
                "determinada exclusivamente pela profundidade real do material disponível: "
                "termine quando o conteúdo relevante tiver sido desenvolvido adequadamente, "
                "não antes (perdendo argumentos importantes) nem depois (repetindo ou enchendo)."
            )
        else:
            tmin = self.target_min_seconds // 60 if self.target_min_seconds else None
            tmax = self.target_max_seconds // 60 if self.target_max_seconds else None
            base = (
                f"Faixa editorial do perfil: aproximadamente {tmin}-{tmax} minutos. "
                "Quando uma duração-alvo explícita for fornecida, ela é um contrato de "
                "conteúdo verificável, não um rótulo: cumpra o orçamento com evidência, "
                "análise e progressão úteis. Nunca use repetição, silêncio ou filler."
            )
        extra = f" {self.guidance}" if self.guidance else ""
        return base + extra


@dataclass(frozen=True)
class ProductionProfile:
    id: str
    nome: str
    descricao: str
    duracao: DurationPolicy
    estrutura_guidance: str  # como organizar o roteiro (guia, não template fixo)
    ideacao_guidance: (
        str  # o que geração/curadoria de ideias deve priorizar neste perfil
    )
    pesquisa_guidance: str  # como a pesquisa/grounding deve ser usada
    regras_editoriais: list[str] = field(default_factory=list)
    workflow_roteiro: str = (
        "roteiro_padrao"  # id do WorkflowSpec usado para gerar roteiro
    )
    permite_grounding_automatico: bool = True
    generation_strategy: str = "auto"
    research_strategy: str = "query_decomposition"
    model_routing_policy: str = "standard"
    long_form_supported: bool = True
    max_practical_duration_seconds: int = 14_400
    source_policy: SourcePolicy = field(default_factory=SourcePolicy)
    visual_requirements: VisualRequirementsPolicy = field(
        default_factory=VisualRequirementsPolicy
    )
    requires_media_scope: bool = True
    burned_in_captions: bool = True


FACELESS_POP_CULTURE_LISTS = ProductionProfile(
    id="faceless_pop_culture_lists",
    nome="Faceless / Cultura Pop — Listas e Explicações",
    descricao=(
        "Canal faceless de cultura pop, games, filmes, séries, quadrinhos e universos "
        "ficcionais, com formatos estruturados como listas, rankings, breakdowns e "
        "explicações de lore/personagens/eventos."
    ),
    duracao=DurationPolicy(
        min_seconds=None,
        target_min_seconds=600,
        target_max_seconds=900,
        default_target_seconds=720,
        content_driven_allowed=True,
        hard_minimum=False,
        guidance=(
            "Assuntos com lore extensa (ex.: 'todas as Joias do Infinito explicadas') podem "
            "justificar mais tempo; um tópico simples não deve ser esticado só para chegar a 10 min."
        ),
    ),
    estrutura_guidance=(
        "Formatos de lista/ranking/breakdown funcionam bem aqui, mas cada item da lista "
        "precisa ser tratado como uma mini-seção com começo, desenvolvimento e fechamento — "
        "não como uma sequência de verbetes desconectados. Prefira ordenar os itens de forma "
        "estratégica (crescente em interesse/impacto, ou agrupando por tema), não pela ordem "
        "em que a informação foi encontrada na pesquisa. Conecte itens adjacentes com "
        "transições que criem uma sensação de progressão, não apenas 'próximo da lista'."
    ),
    ideacao_guidance=(
        "Priorize ângulos específicos e verificáveis dentro de universos ficcionais/cultura pop "
        "(um personagem, um evento, uma mecânica, um conjunto de itens/objetos) em vez de temas "
        "genéricos demais para sustentar um vídeo interessante. Evite títulos que prometam mais "
        "do que o conteúdo pode entregar."
    ),
    pesquisa_guidance=(
        "Fatos de lore/continuidade devem ser verificados via grounding sempre que possível — "
        "erros de continuidade em conteúdo de cultura pop destroem credibilidade rapidamente."
    ),
    regras_editoriais=[
        "Evite spoilers gratuitos sem aviso quando o formato permitir.",
        "Diferencie claramente fato canônico de teoria/especulação do fandom.",
    ],
    workflow_roteiro="roteiro_padrao",
    burned_in_captions=False,
)

FACELESS_INFORMATIONAL = ProductionProfile(
    id="faceless_informational",
    nome="Faceless / Tecnologia e Conteúdo Informativo",
    descricao=(
        "Canal faceless educacional/informativo: tecnologia, ciência, história, geografia, "
        "engenharia, curiosidades técnicas."
    ),
    duracao=DurationPolicy(
        min_seconds=None,
        target_min_seconds=600,
        target_max_seconds=900,
        default_target_seconds=720,
        content_driven_allowed=True,
        guidance="Timelines históricas ou comparações técnicas complexas podem justificar mais tempo.",
    ),
    estrutura_guidance=(
        "Escolha a estrutura pelo conteúdo: timeline para eventos históricos, comparação lado a "
        "lado para tecnologias concorrentes, causa-e-consequência para fenômenos técnicos. Não "
        "force todo assunto no mesmo molde de 'lista de 5 pontos'."
    ),
    ideacao_guidance=(
        "Priorize ângulos com um 'porquê isso importa' claro logo no início. Fatos técnicos "
        "isolados sem contexto de relevância tendem a gerar vídeos monótonos."
    ),
    pesquisa_guidance=(
        "Números, datas e afirmações técnicas específicas DEVEM ser verificados via grounding "
        "antes de entrar no roteiro. Não invente estatísticas nem valores aproximados como se "
        "fossem exatos."
    ),
    regras_editoriais=[
        "Explique jargão técnico na primeira aparição, sem se alongar além do necessário.",
        "Não trate correlação como causalidade sem qualificar a afirmação.",
    ],
    workflow_roteiro="roteiro_padrao",
)

FACELESS_GENERAL = ProductionProfile(
    id="faceless_general",
    nome="Faceless / Geral",
    descricao=(
        "Canal faceless de propósito geral, maior liberdade editorial: curiosidades, "
        "histórias, acontecimentos incomuns, sem exigir workflow especializado."
    ),
    duracao=DurationPolicy(
        min_seconds=None,
        target_min_seconds=600,
        target_max_seconds=900,
        default_target_seconds=720,
        content_driven_allowed=True,
        guidance="Este perfil tem a maior liberdade de formato do conjunto faceless.",
    ),
    estrutura_guidance=(
        "Liberdade total de estrutura narrativa — escolha a forma que melhor serve o assunto "
        "específico (narrativa linear, lista, estudo de caso, pergunta-e-resposta), sem se "
        "prender a um formato padrão do canal."
    ),
    ideacao_guidance=(
        "Priorize originalidade e especificidade do ângulo acima de tudo — este perfil compete "
        "por atenção justamente por trazer assuntos incomuns bem contados."
    ),
    pesquisa_guidance="Use grounding para checar qualquer alegação factual central da história.",
    regras_editoriais=[
        "Evite sensacionalismo vazio: a curiosidade deve vir de fatos reais bem contados."
    ],
    workflow_roteiro="roteiro_padrao",
)

FACELESS_POP_CULTURE = ProductionProfile(
    id="faceless_pop_culture",
    nome="Faceless / Cultura Pop Geral",
    descricao=(
        "Canal faceless de cultura pop amplo, sem se limitar a formato de lista: análises, "
        "teorias, retrospectivas, lore, curiosidades sobre filmes, séries, games, franquias."
    ),
    duracao=DurationPolicy(
        min_seconds=None,
        target_min_seconds=600,
        target_max_seconds=1200,
        default_target_seconds=900,
        content_driven_allowed=True,
        guidance="Retrospectivas de franquia ou análises de universo extenso podem passar de 15 min.",
    ),
    estrutura_guidance=(
        "Mais liberdade narrativa que o perfil de listas: uma análise ou teoria pode (e deve, "
        "quando fizer sentido) seguir uma linha argumentativa contínua em vez de tópicos "
        "separados. Use o formato de lista apenas quando o assunto genuinamente pedir."
    ),
    ideacao_guidance=(
        "Explore ângulos de análise, teoria ou retrospectiva, não apenas fatos objetivos — "
        "este perfil pode ter opinião/interpretação editorial, desde que sinalizada como tal."
    ),
    pesquisa_guidance="Separe claramente fato canônico, declaração oficial de autores/estúdio e teoria de fã.",
    regras_editoriais=[
        "Teorias devem ser apresentadas como teorias, nunca como fato estabelecido."
    ],
    workflow_roteiro="roteiro_padrao",
)

GAME_ANALYSIS = ProductionProfile(
    id="game_analysis",
    nome="Análise de Jogos (a partir de anotações de gameplay)",
    descricao=(
        "Vídeos de análise baseados na experiência real de jogar, gravada e anotada pelo autor. "
        "Workflow independente: a fonte primária é o material fornecido pelo autor, não pesquisa "
        "ou ideação automática."
    ),
    duracao=DurationPolicy(
        min_seconds=None,
        target_min_seconds=None,
        target_max_seconds=None,
        default_target_seconds=None,
        content_driven_allowed=True,
        allow_extended=True,
        guidance=(
            "A duração é inteiramente derivada da profundidade das anotações fornecidas e da "
            "quantidade de argumentos relevantes que elas sustentam. Não existe meta de minutos."
        ),
    ),
    estrutura_guidance=(
        "NÃO organize o roteiro como uma cronologia de sessão de jogo ('fiz isso, depois "
        "aconteceu isso, depois fui ali'). Identifique os temas/argumentos maiores presentes "
        "nas anotações (level design, combate, narrativa, progressão, exploração, IA, direção "
        "de arte, dificuldade, pacing, world-building etc. — conforme o que as anotações "
        "realmente sustentam) e agrupe observações relacionadas de momentos diferentes do jogo "
        "sob o mesmo tema. Preserve ordem cronológica apenas quando ela for parte do argumento "
        "ou da experiência que o autor quer transmitir (ex.: uma progressão de opinião ao longo "
        "do jogo)."
    ),
    ideacao_guidance="Não aplicável — este perfil não passa pelo workflow de ideação/curadoria automática.",
    pesquisa_guidance=(
        "Grounding é opcional e só deve complementar fatos verificáveis sobre o jogo (data de "
        "lançamento, estúdio, mecânicas documentadas) — nunca para substituir ou sobrepor a "
        "experiência e opinião pessoal do autor registradas nas anotações."
    ),
    regras_editoriais=[
        "As anotações do autor são a fonte de prioridade máxima e não podem ser contradizidas.",
        (
            "Nunca invente reações, opiniões ou experiências pessoais que não estejam nas "
            "anotações ou razoavelmente implícitas nelas."
        ),
        (
            "Preserve a perspectiva e as conclusões do autor — o agente edita e estrutura, "
            "não substitui a opinião dele pela própria."
        ),
    ],
    workflow_roteiro="roteiro_analise_jogos",
    permite_grounding_automatico=False,
    max_practical_duration_seconds=28_800,
    source_policy=SourcePolicy(
        grounding_required=False,
        minimum_claims=0,
    ),
)

_REGISTRY: dict[str, ProductionProfile] = {
    p.id: p
    for p in [
        FACELESS_POP_CULTURE_LISTS,
        FACELESS_INFORMATIONAL,
        FACELESS_GENERAL,
        FACELESS_POP_CULTURE,
        GAME_ANALYSIS,
    ]
}

DEFAULT_PROFILE_ID = FACELESS_GENERAL.id


def get_profile(profile_id: str | None) -> ProductionProfile:
    """Resolve um perfil pelo id, com fallback seguro para o perfil default."""
    if not profile_id:
        return _REGISTRY[DEFAULT_PROFILE_ID]
    return _REGISTRY.get(profile_id, _REGISTRY[DEFAULT_PROFILE_ID])


def list_profiles() -> list[ProductionProfile]:
    return list(_REGISTRY.values())


def is_valid_profile_id(profile_id: str) -> bool:
    return profile_id in _REGISTRY
