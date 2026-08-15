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


def grounding_context(texto_grounding: str | None) -> str:
    if not texto_grounding:
        return ""
    return f"Contexto de pesquisa (grounding, use para checar fatos, não copie literalmente):\n{texto_grounding}"
