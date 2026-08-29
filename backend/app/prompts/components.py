"""Camadas de contexto do prompt composto: perfil, nicho, workflow e tarefa."""
from app.production_profiles import ProductionProfile


def production_profile_context(profile: ProductionProfile) -> str:
    partes = [
        f"Perfil de produção ativo: {profile.nome}.",
        profile.descricao,
        "",
        f"Estrutura/formato para este perfil: {profile.estrutura_guidance}",
        "",
        f"Diretrizes de ideação para este perfil: {profile.ideacao_guidance}",
        "",
        f"Uso de pesquisa/grounding para este perfil: {profile.pesquisa_guidance}",
        "",
        f"Política de duração: {profile.duracao.as_prompt_text()}",
    ]
    if profile.regras_editoriais:
        partes.append("")
        partes.append("Regras editoriais específicas deste perfil:")
        partes.extend(f"- {r}" for r in profile.regras_editoriais)
    return "\n".join(partes)


def niche_context(prompt_nicho: str | None, rotulo: str = "Diretrizes específicas do nicho/canal") -> str:
    if not prompt_nicho:
        return ""
    return f"{rotulo} (definidas pelo operador do canal, seguir com prioridade alta):\n{prompt_nicho}"


def media_context_context(media_context_text: str | None) -> str:
    """Format media context for inclusion in prompt."""
    if not media_context_text:
        return ""
    return f"Contexto audiovisual (evidência do gameplay, complementa as anotações):\n{media_context_text}"


def grounding_context(texto_grounding: str | None) -> str:
    if not texto_grounding:
        return ""
    return f"Contexto de pesquisa (grounding, use para checar fatos, não copie literalmente):\n{texto_grounding}"


def author_briefing_context(author_briefing: str | None) -> str:
    """Keep deliberate author context separate from every evidence source."""

    if author_briefing is None:
        return ""
    return (
        "AUTHOR BRIEFING (intenção, opinião e contexto editorial fornecidos pelo autor):\n"
        f"{author_briefing}\n\n"
        "Trate este conteúdo como direção editorial e posição do autor, não como prova factual. "
        "Uma opinião aqui pode orientar a voz do roteiro, mas não deve ser convertida em fato "
        "objetivo sem grounding independente. Preserve ressalvas, incertezas e restrições."
    )
