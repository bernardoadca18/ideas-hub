"""
PromptBuilder: compõe o prompt final a partir das camadas (base, qualidade editorial,
perfil de produção, nicho, workflow, contexto de tarefa) e mantém um trace simples para
observabilidade — o que exatamente foi usado para montar aquele prompt.
"""
from dataclasses import dataclass, field

from app.production_profiles import ProductionProfile
from app.prompts.base import base_agent_instructions
from app.prompts.quality import editorial_quality_charter
from app.prompts.components import (
    production_profile_context,
    niche_context,
    grounding_context,
    media_context_context,
)
from app.prompts.workflows import WorkflowSpec


@dataclass
class ComposedPrompt:
    system: str
    user: str
    trace: dict = field(default_factory=dict)


class PromptBuilder:
    """Uso:
        prompt = (
            PromptBuilder(workflow=ROTEIRO_PADRAO, profile=profile)
            .with_niche(nicho.prompt_roteiro)
            .with_grounding(texto_grounding)
            .with_media_context(media_context_text)
            .build(task_context=usuario_message)
        )
    """

    def __init__(self, workflow: WorkflowSpec, profile: ProductionProfile):
        self.workflow = workflow
        self.profile = profile
        self._niche_text: str | None = None
        self._grounding_text: str | None = None
        self._media_context_text: str | None = None

    def with_niche(self, prompt_nicho: str | None) -> "PromptBuilder":
        self._niche_text = prompt_nicho
        return self

    def with_grounding(self, texto: str | None) -> "PromptBuilder":
        self._grounding_text = texto
        return self

    def with_media_context(self, texto: str | None) -> "PromptBuilder":
        self._media_context_text = texto
        return self

    def build(self, task_context: str) -> ComposedPrompt:
        componentes_usados = ["base", "editorial_quality", "profile:" + self.profile.id, "workflow:" + self.workflow.id]

        system_parts = [
            base_agent_instructions(self.workflow.papel_agente, self.workflow.formato_saida),
            editorial_quality_charter(),
            production_profile_context(self.profile),
            f"Instruções específicas desta tarefa ({self.workflow.id}):\n{self.workflow.instrucoes}",
        ]

        niche_text = niche_context(self._niche_text)
        if niche_text:
            system_parts.append(niche_text)
            componentes_usados.append("niche")

        system = "\n\n---\n\n".join(system_parts)

        user_parts = [task_context]

        # Media context comes before grounding in the user message
        media_text = media_context_context(self._media_context_text)
        if media_text:
            user_parts.append(media_text)
            componentes_usados.append("media_context")

        grounding_text = grounding_context(self._grounding_text)
        if grounding_text:
            user_parts.append(grounding_text)
            componentes_usados.append("grounding")

        user = "\n\n".join(user_parts)

        trace = {
            "profile_id": self.profile.id,
            "workflow_id": self.workflow.id,
            "components": componentes_usados,
            "system_prompt_chars": len(system),
            "user_prompt_chars": len(user),
        }

        return ComposedPrompt(system=system, user=user, trace=trace)
