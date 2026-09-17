"""Transactional, version-safe production-script application service."""

from __future__ import annotations

import json
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
from app.schemas.manual_script_import import (
    MANUAL_SCRIPT_SCHEMA_VERSION,
    ManualImportIdeaPreview,
    ManualImportMediaPreview,
    ManualImportNormalizedPreview,
    ManualScriptImportPreviewResponse,
    ManualScriptImportRequest,
    ManualScriptImportResponse,
)
from app.prompts.editorial_v3 import spoken_language_policy
from app.schemas.roteiro import (
    ManualDraftProvenance,
    MediaBindingRequest,
    RoteiroCreate,
    RoteiroEstrutura,
    RoteiroUpdate,
    ScriptEditRevisionRequest,
    ScriptMediaContext,
    VisualQueryRepairRequest,
    script_content_identity,
)
from app.services.author_briefing import author_briefing_identity
from app.services.duration_contract import (
    DurationCalibration,
    duration_budget_prompt,
    duration_calibration_client,
    evaluate_duration,
    evaluate_editorial_quality,
)
from app.services.editorial_generation import (
    DurationMode,
    DurationTargetSource,
    ResolvedDurationIntent,
    resolve_duration_intent,
)
from app.services.manual_script_import import (
    NormalizedManualScript,
    normalize_manual_script,
    validate_manual_media_scope,
)
from app.services.media_indexer_client import MediaIndexerClient
from app.services.production_readiness import evaluate_production_readiness
from app.services.visual_entity_constraints import validate_visual_query_entity_scope
from app.services.visual_requirements import (
    VISUAL_PRODUCTION_SCRIPT_SCHEMA_VERSION,
    validate_preserved_visual_queries,
    validate_visual_readiness,
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

    def __init__(
        self,
        session: AsyncSession,
        *,
        media_indexer_client: MediaIndexerClient | None = None,
    ):
        self.session = session
        self.ideia_repo = IdeiaRepository(session)
        self.roteiro_repo = RoteiroRepository(session)
        self.nicho_repo = NichoRepository(session)
        self.media_indexer_client = media_indexer_client or MediaIndexerClient()

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
    def _duration_intent(ideia: Ideia, profile: ProductionProfile):
        """Resolve legacy nulls explicitly instead of silently treating them as open-ended."""

        target = getattr(ideia, "target_duration_seconds", None)
        raw_mode = getattr(ideia, "duration_mode", None)
        if raw_mode is None:
            if target is None:
                return ResolvedDurationIntent(
                    mode=DurationMode.CONTENT_DRIVEN,
                    source=DurationTargetSource.HISTORICAL,
                    target_seconds=None,
                    profile_id=profile.id,
                )
            raw_mode = DurationMode.EXPLICIT_TARGET
        return resolve_duration_intent(
            mode=raw_mode,
            requested_target_seconds=target,
            profile=profile,
        )

    @classmethod
    def _target_duration(
        cls, ideia: Ideia, profile: ProductionProfile | None = None
    ) -> int | None:
        profile = profile or get_profile(getattr(ideia, "perfil_producao", None))
        return cls._duration_intent(ideia, profile).target_seconds

    async def _profile_for_idea(self, ideia: Ideia) -> ProductionProfile:
        """Resolve profile through the owning niche; ideas do not own this policy."""

        if getattr(ideia, "origem", None) == "notas_gameplay":
            return get_profile("game_analysis")
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
        duration_intent: ResolvedDurationIntent | None = None,
    ) -> None:
        generated.duration_contract = evaluate_duration(
            generated.blocos,
            target_seconds=target_seconds,
            calibration=calibration,
            profile=profile,
        )
        intent = duration_intent or RoteiroGenerator._duration_intent_for_target(
            target_seconds=target_seconds, profile=profile
        )
        generated.duration_contract["duration_intent"] = intent.to_dict()
        generated.editorial_quality = evaluate_editorial_quality(generated.blocos)
        if generated.prompt_trace is not None:
            generated.prompt_trace.update(
                {
                    "duration_contract_version": generated.duration_contract["version"],
                    "duration_calibration_identity": calibration.identity,
                    "duration_target_seconds": target_seconds,
                    "duration_intent": intent.to_dict(),
                    "editorial_validator_version": generated.editorial_quality[
                        "version"
                    ],
                    "model_gateway": "9router",
                }
            )

    @staticmethod
    def _duration_intent_for_target(
        *, target_seconds: int | None, profile: ProductionProfile
    ):
        mode = (
            DurationMode.EXPLICIT_TARGET
            if target_seconds is not None
            else DurationMode.CONTENT_DRIVEN
        )
        return resolve_duration_intent(
            mode=mode,
            requested_target_seconds=target_seconds,
            profile=profile,
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
        status: str = "rascunho",
    ) -> Roteiro:
        if parent_roteiro_id is not None:
            parent = await self.roteiro_repo.get_by_id(parent_roteiro_id)
            if parent is None:
                raise ValueError("Roteiro pai não encontrado")
            estrutura = estrutura.model_copy(
                update={
                    "content_locale": parent.estrutura.get("content_locale", "pt-BR")
                }
            )
        elif "content_locale" not in estrutura.model_fields_set:
            estrutura = estrutura.model_copy(
                update={"content_locale": getattr(ideia, "content_locale", "pt-BR")}
            )
        profile = await self._profile_for_idea(ideia)
        readiness = validate_visual_readiness(estrutura, profile.visual_requirements)
        structure_payload = estrutura.model_dump(mode="json")
        if readiness.status == "ready":
            structure_payload["production_script_schema_version"] = (
                VISUAL_PRODUCTION_SCRIPT_SCHEMA_VERSION
            )
        structure_payload["visual_readiness"] = readiness.to_dict()
        estrutura = RoteiroEstrutura.model_validate(structure_payload)
        latest_version = await self.roteiro_repo.get_latest_version_number_for_update(
            ideia.id
        )
        snapshot, identity = self._briefing_snapshot(ideia)
        roteiro = await self.roteiro_repo.create(
            RoteiroCreate(
                ideia_id=ideia.id,
                versao=latest_version + 1,
                estrutura=estrutura,
                status=status,
                author_briefing_snapshot=snapshot,
                author_briefing_identity=identity,
                parent_roteiro_id=parent_roteiro_id,
                revision_kind=revision_kind,
                revision_feedback=revision_feedback,
            )
        )
        await self.ideia_repo.update(
            ideia.id,
            IdeiaUpdate(status="roteirizada" if status == "aprovado" else "em_roteiro"),
        )
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
        duration_intent = self._duration_intent(ideia, profile)
        target_seconds = duration_intent.target_seconds
        calibration = await duration_calibration_client.get(
            profile.id, getattr(ideia, "content_locale", "pt-BR")
        )
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
            duration_intent=duration_intent,
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
                duration_intent=duration_intent,
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
        if request.content_locale != "pt-BR":
            raise ValueError(
                "Legacy generate_from_notas does not support en-US; "
                "use durable Game Analysis generation"
            )
        prompt_nicho = None
        if request.nicho_id:
            nicho = await self.nicho_repo.get_by_id(request.nicho_id)
            if nicho:
                prompt_nicho = nicho.prompt_roteiro

        game_profile = get_profile("game_analysis")
        duration_intent = resolve_duration_intent(
            mode=request.duration_mode,
            requested_target_seconds=request.target_duration_seconds,
            profile=game_profile,
        )
        calibration = await duration_calibration_client.get(
            "game_analysis", request.content_locale
        )

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
                    duration_intent.target_seconds,
                    calibration,
                ),
            ),
            ideia_id=None,
            workflow="game_analysis",
        )

        ideia = await self.ideia_repo.create(
            IdeiaCreate(
                content_locale=request.content_locale,
                nicho_id=request.nicho_id,
                origem="notas_gameplay",
                titulo=generated.titulo,
                descricao_breve=(request.anotacoes[:497] + "...")
                if len(request.anotacoes) > 500
                else request.anotacoes,
                author_briefing=request.author_briefing,
                target_duration_seconds=duration_intent.target_seconds,
                duration_mode=duration_intent.mode,
                duration_target_source=duration_intent.source,
                status="aprovada",
                justificativa_llm=(
                    "Ideia criada diretamente a partir de anotações de gameplay "
                    "(workflow de análise de jogos)."
                ),
            )
        )
        self._attach_validation(
            generated,
            target_seconds=duration_intent.target_seconds,
            calibration=calibration,
            profile=game_profile,
            duration_intent=duration_intent,
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
                        duration_intent.target_seconds,
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
                target_seconds=duration_intent.target_seconds,
                calibration=calibration,
                profile=game_profile,
                duration_intent=duration_intent,
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
        self,
        ideia_id: UUID,
        estrutura: RoteiroEstrutura,
        *,
        calibration: DurationCalibration | None = None,
        manual_draft_provenance: ManualDraftProvenance | None = None,
    ) -> Roteiro:
        """Preserve the legacy create endpoint without accepting caller-owned provenance."""

        ideia = await self.ideia_repo.get_by_id(ideia_id)
        if not ideia:
            raise ValueError("Ideia não encontrada")
        profile = await self._profile_for_idea(ideia)
        payload = estrutura.model_dump(mode="json")
        if "content_locale" not in estrutura.model_fields_set:
            payload["content_locale"] = getattr(ideia, "content_locale", "pt-BR")
        calibration = calibration or await duration_calibration_client.get(
            profile.id, payload["content_locale"]
        )
        # This method also backs the public manual-create endpoint. Plain-text
        # provenance is accepted only through the composite server-owned adapter.
        payload["manual_draft"] = (
            manual_draft_provenance.model_dump(mode="json")
            if manual_draft_provenance is not None
            else None
        )
        payload["duration_contract"] = evaluate_duration(
            estrutura.blocos,
            target_seconds=self._target_duration(ideia, profile),
            calibration=calibration,
            profile=profile,
        )
        payload["editorial_quality"] = evaluate_editorial_quality(estrutura.blocos)
        return await self._persist_revision(
            ideia=ideia,
            estrutura=RoteiroEstrutura.model_validate(payload),
            revision_kind="manual_create",
        )

    async def _normalize_manual_import(
        self, request: ManualScriptImportRequest
    ) -> tuple[Ideia, ProductionProfile, DurationCalibration, NormalizedManualScript]:
        ideia = await self.ideia_repo.get_by_id(request.ideia_id)
        if not ideia:
            raise ValueError("Ideia não encontrada")
        profile = await self._profile_for_idea(ideia)
        calibration = await duration_calibration_client.get(
            profile.id, request.content_locale or getattr(ideia, "content_locale", "pt-BR")
        )
        normalized = normalize_manual_script(
            request.script,
            content_locale=request.content_locale
            or getattr(ideia, "content_locale", "pt-BR"),
            calibration=calibration,
            profile=profile,
            target_duration_seconds=self._target_duration(ideia, profile),
        )
        await validate_manual_media_scope(
            request.script.media, client=self.media_indexer_client
        )
        return ideia, profile, calibration, normalized

    async def preview_manual_import(
        self, request: ManualScriptImportRequest
    ) -> ManualScriptImportPreviewResponse:
        """Validate and project a manual import without mutating script history."""

        ideia, profile, _, normalized = await self._normalize_manual_import(request)
        media = request.script.media
        preview_payload = normalized.structure.model_dump(mode="json")
        if media is not None:
            preview_payload["media_context"] = {
                "media_project_id": str(media.project_id),
                "media_session_ids": [str(value) for value in media.session_ids],
            }
        preview_structure = RoteiroEstrutura.model_validate(preview_payload)
        visual = validate_visual_readiness(
            preview_structure, profile.visual_requirements
        ).to_dict()
        production = evaluate_production_readiness(
            preview_structure, script_status="rascunho", profile=profile
        )
        warnings = [
            "O arquivo manual não possui auditoria factual automática; use o re-audit explicitamente se necessário."
        ]
        if (
            normalized.structure.duration_contract
            and normalized.structure.duration_contract.get("revision_required")
        ):
            warnings.append(
                "A duração narrável estimada está fora da faixa do target atual."
            )
        if profile.requires_media_scope and media is None:
            warnings.append("O ProductionProfile exige media scope antes da produção.")
        duration_intent = self._duration_intent(ideia, profile)
        return ManualScriptImportPreviewResponse(
            importable=True,
            schema_version=MANUAL_SCRIPT_SCHEMA_VERSION,
            idea=ManualImportIdeaPreview(
                id=ideia.id,
                title=ideia.titulo,
                niche=getattr(getattr(ideia, "nicho", None), "nome", None),
                production_profile=profile.id,
                target_duration_seconds=duration_intent.target_seconds,
                duration_mode=duration_intent.mode.value,
            ),
            normalized=ManualImportNormalizedPreview(
                title=normalized.structure.titulo,
                block_count=len(normalized.structure.blocos),
                word_count=normalized.word_count,
                duration_total_seconds=normalized.structure.duracao_total_segundos,
                normalized_payload_sha256=normalized.normalized_payload_sha256,
                blocks=list(normalized.block_previews),
            ),
            duration=normalized.structure.duration_contract or {},
            media_scope=ManualImportMediaPreview(
                provided=media is not None,
                project_id=media.project_id if media else None,
                session_ids=list(media.session_ids) if media else [],
                scope=(
                    "not_provided"
                    if media is None
                    else "selected_sessions"
                    if media.session_ids
                    else "whole_project"
                ),
            ),
            visual={
                "status": "pending_enrichment",
                "current_readiness": visual,
                "message": (
                    "VisualQueries serão produzidas posteriormente pelo Visual Enrichment canônico."
                ),
            },
            production_readiness={
                "expected_status_after_import": production["status"],
                "diagnostic": production,
            },
            warnings=warnings,
            errors=[],
        )

    async def import_manual_script(
        self, request: ManualScriptImportRequest
    ) -> ManualScriptImportResponse:
        """Persist one idempotent manual_create and optional media_binding lineage."""

        ideia, _, calibration, normalized = await self._normalize_manual_import(request)
        await self.roteiro_repo.lock_revision_stream(ideia.id)
        existing = await self.roteiro_repo.get_manual_import_result(
            ideia.id, normalized.normalized_payload_sha256
        )
        if existing is not None:
            draft, current = existing
            return ManualScriptImportResponse.model_validate(
                {
                    "created": False,
                    "duplicate": True,
                    "normalized_payload_sha256": normalized.normalized_payload_sha256,
                    "draft": draft,
                    "current_revision": current,
                    "media_binding_applied": current.revision_kind == "media_binding",
                }
            )

        payload = normalized.structure.model_dump(mode="json")
        payload["manual_import"] = {
            "schema_version": MANUAL_SCRIPT_SCHEMA_VERSION,
            "source_filename": request.source_filename,
            "normalized_payload_sha256": normalized.normalized_payload_sha256,
            "source": "manual_file_import",
        }
        draft = await self.create_manual_draft(
            ideia.id,
            RoteiroEstrutura.model_validate(payload),
            calibration=calibration,
        )
        current = draft
        media = request.script.media
        if media is not None:
            current = await self.bind_media_context_revision(
                draft.id,
                MediaBindingRequest(
                    media_context=ScriptMediaContext(
                        media_project_id=media.project_id,
                        media_session_ids=media.session_ids,
                    )
                ),
            )
        return ManualScriptImportResponse.model_validate(
            {
                "created": True,
                "duplicate": False,
                "normalized_payload_sha256": normalized.normalized_payload_sha256,
                "draft": draft,
                "current_revision": current,
                "media_binding_applied": current.revision_kind == "media_binding",
            }
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
            # Coverage belongs to the exact speakable text and its editorial duration.
            # An unchanged block can retain its immutable requirements; an edited block
            # becomes explicitly not-ready and can receive a visual_enrichment child
            # revision later.  Never attach stale spans to new narration.
            if (
                edited.conteudo == original.conteudo
                and edited.duracao_segundos == original.duracao_segundos
            ):
                validate_preserved_visual_queries(
                    content=edited.conteudo,
                    queries=original.visual_queries,
                )
                block["visual_queries"] = [
                    item.model_dump(mode="json") for item in original.visual_queries
                ]
            else:
                block["visual_queries"] = []
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
                "source_prompt_trace": source_structure.prompt_trace,
                "prompt_trace": None,
                "inherited_evidence_provenance": source_structure.evidence_provenance
                or source_structure.inherited_evidence_provenance,
                "evidence_provenance": None,
                "source_generation_run_id": source_structure.generation_run_id
                or source_structure.source_generation_run_id,
                "generation_run_id": None,
                "section_audits": None,
                "global_critic": None,
                "audit_status": "human_edit_unvalidated",
                "manual_draft": None,
            }
        )
        estrutura = RoteiroEstrutura.model_validate(structure_payload)
        profile = await self._profile_for_idea(source.ideia)
        calibration = await duration_calibration_client.get(
            profile.id, source_structure.content_locale
        )
        structure_payload["duration_contract"] = evaluate_duration(
            estrutura.blocos,
            target_seconds=self._target_duration(source.ideia, profile),
            calibration=calibration,
            profile=profile,
        )
        structure_payload["editorial_quality"] = evaluate_editorial_quality(
            estrutura.blocos
        )
        current = RoteiroEstrutura.model_validate(structure_payload)
        structure_payload["editorial_review"] = {
            "version": "editorial_review_v1",
            "audit_status": "human_edit_unvalidated",
            "editorial_status": "human_edit_unvalidated",
            "factuality_status": "unvalidated",
            "approval_blocked": True,
            "audit_content_identity": None,
            "current_content_identity": script_content_identity(current),
            "global_summary": (
                "A narração foi alterada manualmente. Os audits da versão pai não "
                "são válidos para este texto; re-audit é obrigatório."
            ),
            "global_issues": [],
            "section_issues": {},
        }
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
        duration_intent = self._duration_intent(ideia, profile)
        target_seconds = duration_intent.target_seconds
        calibration = await duration_calibration_client.get(
            profile.id, source.estrutura.get("content_locale", "pt-BR")
        )
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
            duration_intent=duration_intent,
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
                duration_intent=duration_intent,
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
        calibration = await duration_calibration_client.get(
            profile.id, structure.content_locale
        )
        report = evaluate_duration(
            structure.blocos,
            target_seconds=self._target_duration(roteiro.ideia),
            calibration=calibration,
            profile=profile,
        )
        report["roteiro_id"] = str(roteiro.id)
        report["script_version"] = roteiro.versao
        return report

    async def visual_readiness_report(self, roteiro_id: UUID) -> dict[str, Any]:
        roteiro = await self.roteiro_repo.get_by_id(roteiro_id)
        if not roteiro:
            raise ValueError("Roteiro não encontrado")
        structure = RoteiroEstrutura.model_validate(roteiro.estrutura)
        profile = await self._profile_for_idea(roteiro.ideia)
        return validate_visual_readiness(
            structure, profile.visual_requirements
        ).to_dict()

    async def production_readiness_report(self, roteiro_id: UUID) -> dict[str, Any]:
        roteiro = await self.roteiro_repo.get_by_id(roteiro_id)
        if not roteiro:
            raise ValueError("Roteiro não encontrado")
        structure = RoteiroEstrutura.model_validate(roteiro.estrutura)
        profile = await self._profile_for_idea(roteiro.ideia)
        return evaluate_production_readiness(
            structure, script_status=roteiro.status, profile=profile
        )

    async def bind_media_context_revision(
        self, roteiro_id: UUID, request: MediaBindingRequest
    ) -> Roteiro:
        """Create a metadata-only child revision with a canonical media scope."""

        source = await self.roteiro_repo.get_by_id(roteiro_id)
        if not source:
            raise ValueError("Roteiro não encontrado")
        if source.status == "rejeitado":
            raise ValueError("Roteiro rejeitado não pode receber media binding")
        structure = RoteiroEstrutura.model_validate(source.estrutura)
        if structure.media_context == request.media_context:
            raise ValueError("Media binding is a no-op: this scope is already current")
        payload = structure.model_dump(mode="json")
        payload["media_context"] = request.media_context.model_dump(mode="json")
        return await self._persist_revision(
            ideia=source.ideia,
            estrutura=RoteiroEstrutura.model_validate(payload),
            revision_kind="media_binding",
            parent_roteiro_id=source.id,
            status=source.status,
        )

    async def repair_visual_queries_revision(
        self, roteiro_id: UUID, request: VisualQueryRepairRequest
    ) -> Roteiro:
        """Create a visual-only child revision replacing only named query text."""

        source = await self.roteiro_repo.get_by_id(roteiro_id)
        if not source:
            raise ValueError("Roteiro não encontrado")
        latest = await self.roteiro_repo.get_latest_version_by_ideia(source.ideia_id)
        if latest is None or latest.id != source.id:
            raise ValueError("Somente a versão mais recente pode receber visual repair")
        structure = RoteiroEstrutura.model_validate(source.estrutura)
        authorized_context = "\n".join(
            [
                structure.titulo,
                *(block.conteudo for block in structure.blocos),
                getattr(source.ideia, "titulo", "") or "",
                getattr(source.ideia, "descricao_breve", "") or "",
                getattr(source.ideia, "author_briefing", "") or "",
            ]
        )
        repairs = {item.visual_query_id: item.query for item in request.repairs}
        found: set[UUID] = set()
        payload = structure.model_dump(mode="json")
        for block in payload["blocos"]:
            for query in block.get("visual_queries", []):
                query_id = UUID(str(query["id"])) if query.get("id") else None
                if query_id in repairs:
                    validate_visual_query_entity_scope(
                        query=repairs[query_id], authorized_context=authorized_context
                    )
                    if query.get("query") == repairs[query_id]:
                        raise ValueError(f"VisualQuery repair is a no-op: {query_id}")
                    query["query"] = repairs[query_id]
                    found.add(query_id)
        missing = set(repairs) - found
        if missing:
            raise ValueError(
                "VisualQuery IDs not found: " + ", ".join(sorted(map(str, missing)))
            )
        repaired = RoteiroEstrutura.model_validate(payload)
        if script_content_identity(repaired) != script_content_identity(structure):
            raise ValueError("VisualQuery repair changed speakable narration")
        return await self._persist_revision(
            ideia=source.ideia,
            estrutura=repaired,
            revision_kind="visual_query_repair",
            parent_roteiro_id=source.id,
        )

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

    async def create_visual_enrichment_revision(self, roteiro_id: UUID) -> Roteiro:
        """
        Generate a visual-only immutable revision for any compatible script without queries.

        The host owns beat spans and batches; the LLM only describes footage semantics.
        """
        from app.prompts.builder import PromptBuilder
        from app.prompts.workflows import VISUAL_ENRICHMENT
        from app.schemas.llm_outputs import (
            VisualBeatEnrichmentOutput,
            validate_model_output,
        )
        from app.services.llm_gateway import LLMTaskRole, llm_gateway
        from app.services.visual_requirements import (
            materialize_written_visual_queries,
            segment_visual_beats,
            speakable_content_identity,
            visual_beat_batches,
        )

        source = await self.roteiro_repo.get_by_id(roteiro_id)
        if not source:
            raise ValueError("Roteiro não encontrado")
        source_structure = RoteiroEstrutura.model_validate(source.estrutura)
        total_queries = sum(len(b.visual_queries) for b in source_structure.blocos)
        if total_queries > 0:
            raise ValueError(
                "Script already has visual queries. Use regeneration to modify."
            )

        ideia = await self.ideia_repo.get_by_id(source.ideia_id)
        if not ideia:
            raise ValueError("Ideia não encontrada")
        profile = await self._profile_for_idea(ideia)
        authorized_context = "\n".join(
            [
                source_structure.titulo,
                *(block.conteudo for block in source_structure.blocos),
                getattr(ideia, "titulo", "") or "",
                getattr(ideia, "descricao_breve", "") or "",
                getattr(ideia, "author_briefing", "") or "",
            ]
        )
        before_identity = speakable_content_identity(source_structure.blocos)
        enriched_blocks: list[dict[str, Any]] = []
        for idx, block in enumerate(source_structure.blocos):
            section_key = f"block-{idx:03d}"
            beats = segment_visual_beats(
                section_key=section_key,
                content=block.conteudo,
                duration_seconds=block.duracao_segundos,
                policy=profile.visual_requirements,
            )
            generated: list[Any] = []
            for batch in visual_beat_batches(beats, profile.visual_requirements):
                composed = PromptBuilder(
                    workflow=VISUAL_ENRICHMENT, profile=profile
                ).build(
                    task_context=self._build_visual_enrichment_prompt(
                        section_key=section_key,
                        block=block,
                        beats=batch,
                        authorized_context=authorized_context,
                    )
                )
                llm_output = await llm_gateway.complete(
                    messages=[
                        {
                            "role": "system",
                            "content": composed.system
                            + (
                                "\n\n"
                                + spoken_language_policy(
                                    source_structure.content_locale
                                )
                                if source_structure.content_locale == "en-US"
                                else ""
                            ),
                        },
                        {"role": "user", "content": composed.user},
                    ],
                    role=LLMTaskRole.WRITING,
                    temperature=0.3,
                    max_tokens=2500,
                    response_schema=VisualBeatEnrichmentOutput.model_json_schema(),
                )
                enriched = validate_model_output(
                    VisualBeatEnrichmentOutput, llm_output.content
                )
                assert isinstance(enriched, VisualBeatEnrichmentOutput)
                expected = [beat.order for beat in batch]
                if [item.beat_order for item in enriched.visual_queries] != expected:
                    raise ValueError(
                        "Visual enrichment did not return every host-owned beat in order"
                    )
                for item in enriched.visual_queries:
                    validate_visual_query_entity_scope(
                        query=item.query, authorized_context=authorized_context
                    )
                generated.extend(enriched.visual_queries)
            materialized = materialize_written_visual_queries(
                generation_run_id=roteiro_id,
                section_key=section_key,
                duration_seconds=block.duracao_segundos,
                content=block.conteudo,
                generated=generated,
                evidence_dossier=(
                    source_structure.media_context.model_dump(mode="json")
                    if source_structure.media_context
                    else {}
                ),
                policy=profile.visual_requirements,
                beats=beats,
            )
            block_dict = block.model_dump(mode="json")
            block_dict["visual_queries"] = [vq.to_dict() for vq in materialized]
            enriched_blocks.append(block_dict)

        structure_payload = source_structure.model_dump(mode="json")
        structure_payload["blocos"] = enriched_blocks
        enriched_structure = RoteiroEstrutura.model_validate(structure_payload)
        after_identity = speakable_content_identity(enriched_structure.blocos)
        if before_identity != after_identity:
            raise ValueError("Visual enrichment changed speakable narration")
        readiness = validate_visual_readiness(
            enriched_structure, profile.visual_requirements
        )
        if readiness.status != "ready":
            raise ValueError(
                "Visual enrichment did not produce a production-ready script"
            )
        return await self._persist_revision(
            ideia=ideia,
            estrutura=enriched_structure,
            revision_kind="visual_enrichment",
            parent_roteiro_id=source.id,
            status=source.status,
        )

    @staticmethod
    def _build_visual_enrichment_prompt(
        *, section_key: str, block: Any, beats: Any, authorized_context: str
    ) -> str:
        """Build one bounded semantic batch; temporal fields are not in its schema."""

        return (
            "NÃO reescreva a narração. O host já definiu os spans abaixo. "
            "Retorne exatamente um item por beat_order, contendo apenas intent, query, "
            "importance, source_note_id e notes. Não retorne excerpt, span, duração, "
            "session ID ou timestamp.\n"
            "Preserve as entidades nomeadas do contexto narrativo/midiático autorizado. "
            "Não substitua jogos, produtos, pessoas, lugares ou obras por entidades "
            "adjacentes, salvo quando a narração pedir comparação explicitamente.\n"
            f"CONTEXTO AUTORIZADO: {authorized_context}\n"
            f"BLOCO: {section_key}\nTIPO: {block.tipo}\n"
            f"DICAS VISUAIS: {block.dicas_visual or 'nenhuma'}\n"
            f"BEATS: {json.dumps([{'beat_order': beat.order, 'narration': beat.text} for beat in beats], ensure_ascii=False)}"
        )


def get_roteiro_generator(session: AsyncSession) -> RoteiroGenerator:
    return RoteiroGenerator(session)
