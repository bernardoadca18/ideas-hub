"""Transactional, version-safe production-script application service."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from functools import partial
from typing import Any
from uuid import UUID

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.analise_jogos import analise_jogos_service
from app.agents.roteirista import RoteiroEstruturado, roteirista_service
from app.core.config import settings
from app.models.ideia import Ideia
from app.models.roteiro import Roteiro
from app.production_profiles import ProductionProfile, get_profile
from app.repositories.ideia_repository import IdeiaRepository
from app.repositories.nicho_repository import NichoRepository
from app.repositories.roteiro_repository import RoteiroRepository
from app.schemas.analise_jogo import AnaliseJogoRequest
from app.schemas.ideia import IdeiaCreate, IdeiaUpdate
from app.schemas.llm_outputs import LLMOutputError
from app.schemas.roteiro import (
    RoteiroCreate,
    RoteiroEstrutura,
    RoteiroUpdate,
    ScriptEditRevisionRequest,
)
from app.services.author_briefing import author_briefing_identity
from app.services.duration_contract import (
    DurationCalibration,
    duration_budget_prompt,
    duration_calibration_client,
    evaluate_duration,
    evaluate_editorial_quality,
)

logger = structlog.get_logger("services.roteiro_generator")


class ScriptGenerationError(RuntimeError):
    """Safe, categorized failure returned after configured provider retries."""

    def __init__(self, category: str, public_message: str):
        super().__init__(public_message)
        self.category = category
        self.public_message = public_message


class RoteiroGenerator:
    """Coordinates LLM work and commits one coherent business transaction."""

    def __init__(self, session: AsyncSession):
        self.session = session
        self.ideia_repo = IdeiaRepository(session)
        self.roteiro_repo = RoteiroRepository(session)
        self.nicho_repo = NichoRepository(session)

    async def _call_script_agent(
        self,
        operation: Callable[[], Awaitable[RoteiroEstruturado]],
        *,
        ideia_id: UUID | None,
        workflow: str,
    ) -> RoteiroEstruturado:
        try:
            return await operation()
        except LLMOutputError as exc:
            logger.warning(
                "script_generation_rejected",
                ideia_id=str(ideia_id) if ideia_id else None,
                workflow=workflow,
                failure_category=exc.category,
            )
            raise ScriptGenerationError(exc.category, exc.public_message) from exc
        except Exception as exc:
            logger.exception(
                "script_provider_failure",
                ideia_id=str(ideia_id) if ideia_id else None,
                workflow=workflow,
                failure_category="provider_failure",
                provider_error_type=type(exc).__name__,
            )
            raise ScriptGenerationError(
                "provider_failure",
                "Não foi possível gerar o roteiro após as tentativas configuradas.",
            ) from exc

    @staticmethod
    def _briefing_snapshot(ideia: Ideia) -> tuple[str | None, str]:
        return ideia.author_briefing, author_briefing_identity(ideia.author_briefing)

    @staticmethod
    def _target_duration(ideia: Ideia) -> int | None:
        # Historical/test projections may predate the migration. Real mapped rows
        # always expose the attribute; absence preserves legacy estimate-only behavior.
        if not hasattr(ideia, "target_duration_seconds"):
            return None
        # A profile range is editorial guidance, not an author-selected target.
        # Inventing its midpoint would make `target` indistinguishable from a
        # deterministic estimate and would incorrectly block otherwise valid scripts.
        return ideia.target_duration_seconds

    async def _profile_for_idea(self, ideia: Ideia) -> ProductionProfile:
        """Resolve profile through the owning niche; ideas do not own this policy."""

        if ideia.nicho_id:
            nicho = await self.nicho_repo.get_by_id(ideia.nicho_id)
            if nicho:
                return get_profile(nicho.perfil_producao)
        return get_profile(None)

    @staticmethod
    def _attach_validation(
        generated: RoteiroEstruturado,
        *,
        target_seconds: int | None,
        calibration: DurationCalibration,
        profile: ProductionProfile,
    ) -> None:
        generated.duration_contract = evaluate_duration(
            generated.blocos,
            target_seconds=target_seconds,
            calibration=calibration,
            profile=profile,
        )
        generated.editorial_quality = evaluate_editorial_quality(generated.blocos)
        if generated.prompt_trace is not None:
            generated.prompt_trace.update(
                {
                    "duration_contract_version": generated.duration_contract["version"],
                    "duration_calibration_identity": calibration.identity,
                    "duration_target_seconds": target_seconds,
                    "editorial_validator_version": generated.editorial_quality[
                        "version"
                    ],
                    "llm_provider": "litellm_openai_compatible",
                }
            )

    @staticmethod
    def _targeted_revision_feedback(generated: RoteiroEstruturado) -> str:
        contract = generated.duration_contract or {}
        sections = contract.get("sections") or []
        weak = [
            f"section {item['index'] + 1} ({item['type']}): "
            f"{item['actual_words']} words vs target {item['target_words']}"
            for item in sections
            if item.get("status") not in {"excellent", "acceptable", "estimate_only"}
        ]
        direction = "expand" if (contract.get("ratio") or 1) < 1 else "compress"
        return (
            "TARGETED DURATION REVISION. Do not regenerate indiscriminately. "
            f"Action: {direction}. Target={contract.get('target_duration_seconds')}s; "
            f"predicted={contract.get('predicted_duration_seconds')}s; "
            f"delta={contract.get('delta_seconds')}s. Weak sections: {'; '.join(weak)}. "
            "Preserve supported facts, claims, VisualQueries and useful beats. Add evidence, "
            "examples, comparisons, counterexamples, implications and payoff when expanding; "
            "remove duplication and compact redundant beats when shortening. Never add filler, "
            "generic recap or unsupported claims."
        )

    async def _persist_revision(
        self,
        *,
        ideia: Ideia,
        estrutura: RoteiroEstrutura,
        revision_kind: str,
        parent_roteiro_id: UUID | None = None,
        revision_feedback: str | None = None,
    ) -> Roteiro:
        latest_version = await self.roteiro_repo.get_latest_version_number_for_update(
            ideia.id
        )
        snapshot, identity = self._briefing_snapshot(ideia)
        roteiro = await self.roteiro_repo.create(
            RoteiroCreate(
                ideia_id=ideia.id,
                versao=latest_version + 1,
                estrutura=estrutura,
                status="rascunho",
                author_briefing_snapshot=snapshot,
                author_briefing_identity=identity,
                parent_roteiro_id=parent_roteiro_id,
                revision_kind=revision_kind,
                revision_feedback=revision_feedback,
            )
        )
        await self.ideia_repo.update(ideia.id, IdeiaUpdate(status="em_roteiro"))
        logger.info(
            "script_revision_persisted",
            ideia_id=str(ideia.id),
            roteiro_id=str(roteiro.id),
            script_version=roteiro.versao,
            revision_kind=revision_kind,
            author_briefing_present=snapshot is not None,
            author_briefing_identity=identity,
        )
        return roteiro

    @staticmethod
    def _summary(roteiro: Roteiro, estrutura: RoteiroEstrutura) -> dict[str, Any]:
        return {
            "ideia_id": str(roteiro.ideia_id),
            "roteiro_id": str(roteiro.id),
            "versao": roteiro.versao,
            "titulo": estrutura.titulo,
            "duracao_total_segundos": estrutura.duracao_total_segundos,
            "num_blocos": len(estrutura.blocos),
            "status": roteiro.status,
        }

    async def generate_from_ideia(self, ideia_id: UUID) -> dict[str, Any]:
        ideia = await self.ideia_repo.get_by_id(ideia_id)
        if not ideia:
            raise ValueError("Ideia não encontrada")
        if ideia.status != "aprovada":
            raise ValueError(f"Ideia não está aprovada (status: {ideia.status})")

        prompt_roteiro = None
        perfil_id = None
        if ideia.nicho_id:
            nicho = await self.nicho_repo.get_by_id(ideia.nicho_id)
            if nicho:
                prompt_roteiro = nicho.prompt_roteiro
                perfil_id = nicho.perfil_producao

        profile = get_profile(perfil_id)
        target_seconds = self._target_duration(ideia)
        calibration = await duration_calibration_client.get(profile.id)
        budget_prompt = duration_budget_prompt(target_seconds, calibration)

        roteiro_anterior = None
        if ideia.eh_continuacao_de and ideia.numero_parte and ideia.numero_parte > 1:
            previous = await self.roteiro_repo.get_latest_version_by_ideia(
                ideia.eh_continuacao_de
            )
            if previous:
                roteiro_anterior = {
                    "id": str(previous.id),
                    "estrutura": previous.estrutura,
                }

        generated = await self._call_script_agent(
            lambda: roteirista_service.gerar_roteiro(
                ideia_titulo=ideia.titulo,
                ideia_descricao=ideia.descricao_breve,
                prompt_roteiro=prompt_roteiro,
                roteiro_anterior=roteiro_anterior,
                numero_parte=ideia.numero_parte,
                ideia_id=str(ideia_id),
                perfil_id=perfil_id,
                author_briefing=ideia.author_briefing,
                duration_contract_prompt=budget_prompt,
            ),
            ideia_id=ideia_id,
            workflow="standard",
        )
        self._attach_validation(
            generated,
            target_seconds=target_seconds,
            calibration=calibration,
            profile=profile,
        )
        for _ in range(settings.duration_revision_max_iterations):
            if (
                not generated.duration_contract
                or not generated.duration_contract["revision_required"]
            ):
                break
            revision_source = roteirista_service.to_dict(generated)
            feedback = self._targeted_revision_feedback(generated)
            generated = await self._call_script_agent(
                partial(
                    roteirista_service.gerar_roteiro,
                    ideia_titulo=ideia.titulo,
                    ideia_descricao=ideia.descricao_breve,
                    prompt_roteiro=prompt_roteiro,
                    ideia_id=str(ideia_id),
                    perfil_id=profile.id,
                    author_briefing=ideia.author_briefing,
                    revision_source=revision_source,
                    revision_feedback=feedback,
                    duration_contract_prompt=budget_prompt,
                ),
                ideia_id=ideia_id,
                workflow="targeted_duration_revision",
            )
            self._attach_validation(
                generated,
                target_seconds=target_seconds,
                calibration=calibration,
                profile=profile,
            )
        if generated.prompt_trace is not None:
            generated.prompt_trace["author_briefing_identity"] = (
                ideia.author_briefing_identity
            )
        estrutura = RoteiroEstrutura.model_validate(
            roteirista_service.to_dict(generated)
        )
        created = await self._persist_revision(
            ideia=ideia,
            estrutura=estrutura,
            revision_kind="llm_generation",
        )
        return self._summary(created, estrutura)

    async def generate_from_notas(self, request: AnaliseJogoRequest) -> dict[str, Any]:
        prompt_nicho = None
        if request.nicho_id:
            nicho = await self.nicho_repo.get_by_id(request.nicho_id)
            if nicho:
                prompt_nicho = nicho.prompt_roteiro

        calibration = await duration_calibration_client.get("game_analysis")

        generated = await self._call_script_agent(
            lambda: analise_jogos_service.gerar_roteiro_de_notas(
                titulo_provisorio=request.titulo_provisorio,
                anotacoes=request.anotacoes,
                nome_jogo=request.nome_jogo,
                prompt_nicho=prompt_nicho,
                usar_grounding=request.usar_grounding,
                media_project_id=request.media_project_id,
                media_session_ids=request.media_session_ids,
                author_briefing=request.author_briefing,
                duration_contract_prompt=duration_budget_prompt(
                    request.target_duration_seconds,
                    calibration,
                ),
            ),
            ideia_id=None,
            workflow="game_analysis",
        )

        ideia = await self.ideia_repo.create(
            IdeiaCreate(
                nicho_id=request.nicho_id,
                origem="notas_gameplay",
                titulo=generated.titulo,
                descricao_breve=(request.anotacoes[:497] + "...")
                if len(request.anotacoes) > 500
                else request.anotacoes,
                author_briefing=request.author_briefing,
                target_duration_seconds=request.target_duration_seconds,
                status="aprovada",
                justificativa_llm=(
                    "Ideia criada diretamente a partir de anotações de gameplay "
                    "(workflow de análise de jogos)."
                ),
            )
        )
        self._attach_validation(
            generated,
            target_seconds=request.target_duration_seconds,
            calibration=calibration,
            profile=get_profile("game_analysis"),
        )
        for _ in range(settings.duration_revision_max_iterations):
            if (
                not generated.duration_contract
                or not generated.duration_contract["revision_required"]
            ):
                break
            revision_source = roteirista_service.to_dict(generated)
            feedback = self._targeted_revision_feedback(generated)
            generated = await self._call_script_agent(
                partial(
                    analise_jogos_service.gerar_roteiro_de_notas,
                    titulo_provisorio=request.titulo_provisorio,
                    anotacoes=request.anotacoes,
                    nome_jogo=request.nome_jogo,
                    prompt_nicho=prompt_nicho,
                    usar_grounding=request.usar_grounding,
                    media_project_id=request.media_project_id,
                    media_session_ids=request.media_session_ids,
                    author_briefing=request.author_briefing,
                    duration_contract_prompt=duration_budget_prompt(
                        request.target_duration_seconds,
                        calibration,
                    ),
                    revision_source=revision_source,
                    revision_feedback=feedback,
                ),
                ideia_id=None,
                workflow="game_analysis_targeted_duration_revision",
            )
            self._attach_validation(
                generated,
                target_seconds=request.target_duration_seconds,
                calibration=calibration,
                profile=get_profile("game_analysis"),
            )
        if generated.prompt_trace is not None:
            generated.prompt_trace["author_briefing_identity"] = (
                ideia.author_briefing_identity
            )
        estrutura = RoteiroEstrutura.model_validate(
            roteirista_service.to_dict(generated)
        )
        created = await self._persist_revision(
            ideia=ideia,
            estrutura=estrutura,
            revision_kind="game_analysis_generation",
        )
        return self._summary(created, estrutura)

    async def create_manual_draft(
        self, ideia_id: UUID, estrutura: RoteiroEstrutura
    ) -> Roteiro:
        """Preserve the legacy create endpoint without accepting caller-owned provenance."""

        ideia = await self.ideia_repo.get_by_id(ideia_id)
        if not ideia:
            raise ValueError("Ideia não encontrada")
        profile = await self._profile_for_idea(ideia)
        calibration = await duration_calibration_client.get(profile.id)
        payload = estrutura.model_dump(mode="json")
        payload["duration_contract"] = evaluate_duration(
            estrutura.blocos,
            target_seconds=self._target_duration(ideia),
            calibration=calibration,
            profile=profile,
        )
        payload["editorial_quality"] = evaluate_editorial_quality(estrutura.blocos)
        return await self._persist_revision(
            ideia=ideia,
            estrutura=RoteiroEstrutura.model_validate(payload),
            revision_kind="manual_create",
        )

    async def create_human_edit_revision(
        self,
        roteiro_id: UUID,
        request: ScriptEditRevisionRequest,
    ) -> Roteiro:
        source = await self.roteiro_repo.get_by_id(roteiro_id)
        if not source:
            raise ValueError("Roteiro não encontrado")
        source_structure = RoteiroEstrutura.model_validate(source.estrutura)
        if len(request.blocos) != len(source_structure.blocos):
            raise ValueError(
                "A edição segura deve preservar a quantidade e a ordem dos blocos; "
                "use regeneração com feedback para mudanças estruturais."
            )

        blocks: list[dict[str, Any]] = []
        for edited, original in zip(
            request.blocos, source_structure.blocos, strict=True
        ):
            block = edited.model_dump(mode="json")
            block["visual_queries"] = [
                item.model_dump(mode="json") for item in original.visual_queries
            ]
            blocks.append(block)
        structure_payload = source_structure.model_dump(mode="json")
        structure_payload.update(
            {
                "titulo": request.titulo,
                "duracao_total_segundos": sum(
                    item.duracao_segundos for item in request.blocos
                ),
                "blocos": blocks,
                "tags": request.tags,
                "referencias": request.referencias,
            }
        )
        estrutura = RoteiroEstrutura.model_validate(structure_payload)
        profile = await self._profile_for_idea(source.ideia)
        calibration = await duration_calibration_client.get(profile.id)
        structure_payload["duration_contract"] = evaluate_duration(
            estrutura.blocos,
            target_seconds=self._target_duration(source.ideia),
            calibration=calibration,
            profile=profile,
        )
        structure_payload["editorial_quality"] = evaluate_editorial_quality(
            estrutura.blocos
        )
        estrutura = RoteiroEstrutura.model_validate(structure_payload)
        return await self._persist_revision(
            ideia=source.ideia,
            estrutura=estrutura,
            revision_kind="human_edit",
            parent_roteiro_id=source.id,
            revision_feedback=request.edit_summary,
        )

    async def regenerate_with_feedback(
        self, roteiro_id: UUID, feedback: str
    ) -> Roteiro:
        source = await self.roteiro_repo.get_by_id(roteiro_id)
        if not source:
            raise ValueError("Roteiro não encontrado")
        ideia = source.ideia
        prompt_roteiro = None
        perfil_id = None
        if ideia.nicho_id:
            nicho = await self.nicho_repo.get_by_id(ideia.nicho_id)
            if nicho:
                prompt_roteiro = nicho.prompt_roteiro
                perfil_id = nicho.perfil_producao

        profile = get_profile(perfil_id)
        target_seconds = self._target_duration(ideia)
        calibration = await duration_calibration_client.get(profile.id)
        budget_prompt = duration_budget_prompt(target_seconds, calibration)

        generated = await self._call_script_agent(
            lambda: roteirista_service.gerar_roteiro(
                ideia_titulo=ideia.titulo,
                ideia_descricao=ideia.descricao_breve,
                prompt_roteiro=prompt_roteiro,
                ideia_id=str(ideia.id),
                perfil_id=perfil_id,
                author_briefing=ideia.author_briefing,
                revision_source=source.estrutura,
                revision_feedback=feedback,
                duration_contract_prompt=budget_prompt,
            ),
            ideia_id=ideia.id,
            workflow="regeneration_with_feedback",
        )
        self._attach_validation(
            generated,
            target_seconds=target_seconds,
            calibration=calibration,
            profile=profile,
        )
        for _ in range(settings.duration_revision_max_iterations):
            if (
                not generated.duration_contract
                or not generated.duration_contract["revision_required"]
            ):
                break
            revision_source = roteirista_service.to_dict(generated)
            targeted_feedback = self._targeted_revision_feedback(generated)
            generated = await self._call_script_agent(
                partial(
                    roteirista_service.gerar_roteiro,
                    ideia_titulo=ideia.titulo,
                    ideia_descricao=ideia.descricao_breve,
                    prompt_roteiro=prompt_roteiro,
                    ideia_id=str(ideia.id),
                    perfil_id=profile.id,
                    author_briefing=ideia.author_briefing,
                    revision_source=revision_source,
                    revision_feedback=targeted_feedback,
                    duration_contract_prompt=budget_prompt,
                ),
                ideia_id=ideia.id,
                workflow="targeted_duration_revision",
            )
            self._attach_validation(
                generated,
                target_seconds=target_seconds,
                calibration=calibration,
                profile=profile,
            )
        if generated.prompt_trace is not None:
            generated.prompt_trace["author_briefing_identity"] = (
                ideia.author_briefing_identity
            )
        estrutura = RoteiroEstrutura.model_validate(
            roteirista_service.to_dict(generated)
        )
        return await self._persist_revision(
            ideia=ideia,
            estrutura=estrutura,
            revision_kind="llm_regeneration",
            parent_roteiro_id=source.id,
            revision_feedback=feedback,
        )

    async def aprovar_roteiro(self, roteiro_id: UUID) -> dict[str, Any]:
        roteiro = await self.roteiro_repo.get_by_id(roteiro_id)
        if not roteiro:
            raise ValueError("Roteiro não encontrado")
        if roteiro.status != "rascunho":
            raise ValueError(f"Roteiro não está em rascunho (status: {roteiro.status})")
        latest = await self.roteiro_repo.get_latest_version_by_ideia(roteiro.ideia_id)
        if latest is None or latest.id != roteiro.id:
            raise ValueError(
                "Somente a versão mais recente do roteiro pode ser aprovada"
            )

        estrutura = RoteiroEstrutura.model_validate(roteiro.estrutura)
        contract = estrutura.duration_contract
        if contract and contract.get("revision_required"):
            target = contract.get("target_duration_seconds")
            predicted = contract.get("predicted_duration_seconds")
            raise ValueError(
                "O contrato de duração exige revisão antes da aprovação "
                f"(target={target}s, predicted={predicted}s, status={contract.get('status')})."
            )

        updated = await self.roteiro_repo.update(
            roteiro_id, RoteiroUpdate(status="aprovado")
        )
        assert updated is not None
        await self.ideia_repo.update(
            roteiro.ideia_id, IdeiaUpdate(status="roteirizada")
        )
        return {
            "roteiro_id": str(roteiro_id),
            "ideia_id": str(roteiro.ideia_id),
            "status": updated.status,
            "mensagem": "Roteiro aprovado com sucesso",
        }

    async def duration_report(self, roteiro_id: UUID) -> dict[str, Any]:
        roteiro = await self.roteiro_repo.get_by_id(roteiro_id)
        if not roteiro:
            raise ValueError("Roteiro não encontrado")
        structure = RoteiroEstrutura.model_validate(roteiro.estrutura)
        profile = await self._profile_for_idea(roteiro.ideia)
        calibration = await duration_calibration_client.get(profile.id)
        report = evaluate_duration(
            structure.blocos,
            target_seconds=self._target_duration(roteiro.ideia),
            calibration=calibration,
            profile=profile,
        )
        report["roteiro_id"] = str(roteiro.id)
        report["script_version"] = roteiro.versao
        return report

    async def rejeitar_roteiro(self, roteiro_id: UUID) -> dict[str, Any]:
        roteiro = await self.roteiro_repo.get_by_id(roteiro_id)
        if not roteiro:
            raise ValueError("Roteiro não encontrado")
        if roteiro.status != "rascunho":
            raise ValueError(f"Roteiro não está em rascunho (status: {roteiro.status})")
        latest = await self.roteiro_repo.get_latest_version_by_ideia(roteiro.ideia_id)
        if latest is None or latest.id != roteiro.id:
            raise ValueError(
                "Somente a versão mais recente do roteiro pode ser rejeitada"
            )

        updated = await self.roteiro_repo.update(
            roteiro_id, RoteiroUpdate(status="rejeitado")
        )
        assert updated is not None
        await self.ideia_repo.update(roteiro.ideia_id, IdeiaUpdate(status="aprovada"))
        return {
            "roteiro_id": str(roteiro_id),
            "ideia_id": str(roteiro.ideia_id),
            "status": updated.status,
            "mensagem": "Roteiro rejeitado. Ideia voltou para status aprovada.",
        }


def get_roteiro_generator(session: AsyncSession) -> RoteiroGenerator:
    return RoteiroGenerator(session)
