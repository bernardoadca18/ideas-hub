"""Deterministic, TTS-independent script duration and editorial diagnostics."""

from __future__ import annotations

import hashlib
import json
import re
import statistics
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from typing import Any

import httpx

from app.core.config import settings
from app.production_profiles import ProductionProfile

DURATION_CONTRACT_VERSION = "script_duration_contract_v1"
SPEAKABLE_TEXT_VERSION = "speakable_text_blocks_v1"
EDITORIAL_VALIDATOR_VERSION = "editorial_validator_v2"
_WORD_RE = re.compile(r"\b[\wÀ-ÿ]+(?:[-'][\wÀ-ÿ]+)*\b", re.UNICODE)
_SENTENCE_RE = re.compile(r"(?<=[.!?])\s+")
_GENERIC_HOOKS = (
    "hoje vamos falar",
    "hoje vamos analisar",
    "neste vídeo veremos",
    "neste vídeo vamos",
    "desde os primórdios",
    "o universo de",
    "está prestes a mudar para sempre",
)
_GRANDIOSITY_SIGNALS = (
    "sem precedentes",
    "redefine completamente",
    "novo padrão",
    "mudará para sempre",
    "imersão sem precedentes",
)
_ROBOTIC_TRANSITION_SIGNALS = (
    "essa transformação",
    "essa integração",
    "essa consolidação",
    "consequentemente",
    "fundamentalmente",
    "estruturalmente",
)


def _identity(payload: dict[str, Any]) -> str:
    canonical = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def normalize_speakable_text(text: str) -> str:
    """Normalize whitespace only; canonical script content is never rewritten."""

    return " ".join(text.split())


def speakable_text_from_blocks(blocks: Sequence[Any]) -> str:
    """Return exactly the narrative content sent downstream, excluding metadata."""

    parts: list[str] = []
    for block in blocks:
        content = (
            block.get("conteudo", "") if isinstance(block, dict) else block.conteudo
        )
        normalized = normalize_speakable_text(str(content))
        if normalized:
            parts.append(normalized)
    return "\n\n".join(parts)


def count_words(text: str) -> int:
    return len(_WORD_RE.findall(text))


def revision_duration_diagnostics(
    contract: dict[str, Any] | None,
) -> dict[str, Any]:
    """Expose revision deltas from an already-evaluated duration contract.

    Status and tolerance remain owned by ``evaluate_duration`` and the active
    production profile. This helper only makes the persisted measurements explicit
    for a later revision run, including compatibility with older contract payloads.
    """

    value = contract or {}
    target_words = _optional_int(value.get("target_words"))
    actual_words = _optional_int(value.get("speakable_words"))
    target_seconds = _optional_number(value.get("target_duration_seconds"))
    predicted_seconds = _optional_number(value.get("predicted_duration_seconds"))
    sections: list[dict[str, Any]] = []
    for fallback_index, section in enumerate(value.get("sections") or []):
        index = _optional_int(section.get("index"))
        if index is None:
            index = fallback_index
        section_target = _optional_int(section.get("target_words"))
        section_actual = _optional_int(section.get("actual_words"))
        sections.append(
            {
                "section_key": f"section-{index + 1:03d}",
                "index": index,
                "type": section.get("type"),
                "target_duration_seconds": _optional_number(
                    section.get("target_duration_seconds")
                ),
                "predicted_duration_seconds": _optional_number(
                    section.get("predicted_duration_seconds")
                ),
                "target_words": section_target,
                "actual_words": section_actual,
                "word_deficit": _positive_difference(section_target, section_actual),
                "word_surplus": _positive_difference(section_actual, section_target),
                "ratio": section.get("ratio"),
                "status": section.get("status") or "unavailable",
            }
        )
    return {
        "target_seconds": target_seconds,
        "predicted_seconds": predicted_seconds,
        "seconds_deficit": _positive_difference(target_seconds, predicted_seconds),
        "seconds_surplus": _positive_difference(predicted_seconds, target_seconds),
        "target_words": target_words,
        "actual_words": actual_words,
        "word_deficit": _positive_difference(target_words, actual_words),
        "word_surplus": _positive_difference(actual_words, target_words),
        "ratio": value.get("ratio"),
        "status": value.get("status") or "unavailable",
        "revision_required": bool(value.get("revision_required")),
        "sections": sections,
    }


def _optional_int(value: Any) -> int | None:
    if value is None:
        return None
    return int(value)


def _optional_number(value: Any) -> int | float | None:
    if value is None:
        return None
    return value if isinstance(value, (int, float)) else float(value)


def _positive_difference(
    minuend: int | float | None, subtrahend: int | float | None
) -> int | float | None:
    if minuend is None or subtrahend is None:
        return None
    return max(0, minuend - subtrahend)


@dataclass(frozen=True)
class DurationCalibration:
    version: str
    identity: str
    words_per_minute: float
    chars_per_second: float
    sample_count: int
    source_window: str
    generated_at: str | None
    fallback: bool
    language: str
    voice_profile: str | None
    generation_profile: str | None
    production_profile: str | None

    @classmethod
    def fallback_for(cls, *, production_profile: str | None) -> DurationCalibration:
        version = "speaking_rate_fallback_v1"
        words_per_minute = float(settings.duration_fallback_words_per_minute)
        chars_per_second = float(settings.duration_fallback_chars_per_second)
        payload = {
            "version": version,
            "words_per_minute": words_per_minute,
            "chars_per_second": chars_per_second,
            "language": "pt-BR",
            "production_profile": production_profile,
        }
        return cls(
            version=version,
            identity=_identity(payload),
            words_per_minute=words_per_minute,
            chars_per_second=chars_per_second,
            sample_count=0,
            source_window="configured_fallback",
            generated_at=None,
            fallback=True,
            language="pt-BR",
            voice_profile=None,
            generation_profile=None,
            production_profile=production_profile,
        )


class DurationCalibrationClient:
    """Read accepted-take telemetry from Orchestrator, with an explicit fallback."""

    async def get(self, production_profile: str | None) -> DurationCalibration:
        fallback = DurationCalibration.fallback_for(
            production_profile=production_profile
        )
        try:
            async with httpx.AsyncClient(
                timeout=settings.orchestrator_timeout_seconds
            ) as client:
                response = await client.get(
                    f"{settings.orchestrator_base_url.rstrip('/')}/workflow/calibration/speaking-rate",
                    params={"production_profile": production_profile}
                    if production_profile
                    else None,
                )
                response.raise_for_status()
                payload = response.json()
            return DurationCalibration(
                version=str(payload["version"]),
                identity=str(payload["identity"]),
                words_per_minute=float(payload["words_per_minute"]),
                chars_per_second=float(payload["chars_per_second"]),
                sample_count=int(payload["sample_count"]),
                source_window=str(payload["source_window"]),
                generated_at=payload.get("generated_at"),
                fallback=bool(payload["fallback"]),
                language=str(payload.get("language") or "pt-BR"),
                voice_profile=payload.get("voice_profile"),
                generation_profile=payload.get("generation_profile"),
                production_profile=payload.get("production_profile"),
            )
        except (httpx.HTTPError, KeyError, TypeError, ValueError):
            return fallback


def duration_budget_prompt(
    target_seconds: int | None, calibration: DurationCalibration
) -> str:
    if target_seconds is None:
        return (
            "DURATION MODE: estimate-only. There is no explicit editorial target. "
            "Do not invent length; cover only evidence-supported material."
        )
    target_words = round(calibration.words_per_minute * target_seconds / 60)
    tolerance = 0.15
    return (
        "DURATION CONTRACT (deterministic validator follows):\n"
        f"- target_duration_seconds: {target_seconds}\n"
        f"- calibrated target_words: {target_words}\n"
        f"- acceptable word interval: {round(target_words * (1 - tolerance))}-"
        f"{round(target_words * (1 + tolerance))}\n"
        f"- calibration identity: {calibration.identity}\n"
        "Plan section budgets and beats before writing. Every section must add evidence, "
        "contrast, explanation, implication or payoff. Never fill the budget with recap, "
        "paraphrase, generic CTA, artificial pauses or repeated thesis."
    )


def predict_duration_seconds(text: str, calibration: DurationCalibration) -> float:
    """Estimate editorial duration using the canonical calibrated formula."""

    words = count_words(text)
    chars = len(normalize_speakable_text(text))
    estimates = []
    if calibration.words_per_minute > 0:
        estimates.append(words * 60 / calibration.words_per_minute)
    if calibration.chars_per_second > 0:
        estimates.append(chars / calibration.chars_per_second)
    return round(statistics.median(estimates), 3) if estimates else 0.0


def _status(ratio: float, profile: ProductionProfile) -> str:
    delta = ratio - 1.0
    if abs(delta) <= profile.duracao.excellent_tolerance_ratio:
        return "excellent"
    if abs(delta) <= profile.duracao.acceptable_tolerance_ratio:
        return "acceptable"
    if ratio < 0.70:
        return "far_below_target"
    if ratio < 1:
        return "below_target"
    if ratio > 1.30:
        return "far_above_target"
    return "above_target"


def evaluate_duration(
    blocks: Sequence[Any],
    *,
    target_seconds: int | None,
    calibration: DurationCalibration,
    profile: ProductionProfile,
) -> dict[str, Any]:
    text = speakable_text_from_blocks(blocks)
    words = count_words(text)
    chars = len(normalize_speakable_text(text))
    predicted = predict_duration_seconds(text, calibration)
    ratio = predicted / target_seconds if target_seconds else None
    status = _status(ratio, profile) if ratio is not None else "estimate_only"
    target_words = (
        round(calibration.words_per_minute * target_seconds / 60)
        if target_seconds
        else None
    )
    sections: list[dict[str, Any]] = []
    declared_total = sum(
        int(
            block.get("duracao_segundos", 0)
            if isinstance(block, dict)
            else block.duracao_segundos
        )
        for block in blocks
    )
    for index, block in enumerate(blocks):
        duration = int(
            block.get("duracao_segundos", 0)
            if isinstance(block, dict)
            else block.duracao_segundos
        )
        content = (
            block.get("conteudo", "") if isinstance(block, dict) else block.conteudo
        )
        section_text = normalize_speakable_text(str(content))
        section_target = (
            round(target_seconds * duration / declared_total)
            if target_seconds and declared_total > 0
            else None
        )
        section_predicted = predict_duration_seconds(section_text, calibration)
        section_ratio = section_predicted / section_target if section_target else None
        section_target_words = (
            round(calibration.words_per_minute * section_target / 60)
            if section_target
            else None
        )
        sections.append(
            {
                "index": index,
                "type": block.get("tipo") if isinstance(block, dict) else block.tipo,
                "target_duration_seconds": section_target,
                "target_words": section_target_words,
                "min_words": round(
                    section_target_words
                    * (1 - profile.duracao.acceptable_tolerance_ratio)
                )
                if section_target_words
                else None,
                "max_words": round(
                    section_target_words
                    * (1 + profile.duracao.acceptable_tolerance_ratio)
                )
                if section_target_words
                else None,
                "actual_words": count_words(section_text),
                "predicted_duration_seconds": section_predicted,
                "ratio": round(section_ratio, 4) if section_ratio is not None else None,
                "status": _status(section_ratio, profile)
                if section_ratio is not None
                else "estimate_only",
            }
        )
    revision_required = status not in {"excellent", "acceptable", "estimate_only"}
    payload = {
        "version": DURATION_CONTRACT_VERSION,
        "speakable_text_version": SPEAKABLE_TEXT_VERSION,
        "target_duration_seconds": target_seconds,
        "predicted_duration_seconds": predicted,
        "actual_narration_duration_seconds": None,
        "delta_seconds": round(predicted - target_seconds, 3)
        if target_seconds
        else None,
        "ratio": round(ratio, 4) if ratio is not None else None,
        "status": status,
        "revision_required": revision_required,
        "speakable_words": words,
        "speakable_chars": chars,
        "target_words": target_words,
        "min_words": round(
            target_words * (1 - profile.duracao.acceptable_tolerance_ratio)
        )
        if target_words
        else None,
        "max_words": round(
            target_words * (1 + profile.duracao.acceptable_tolerance_ratio)
        )
        if target_words
        else None,
        "calibration": asdict(calibration),
        "sections": sections,
    }
    payload["identity"] = _identity(payload)
    return payload


def evaluate_editorial_quality(blocks: Sequence[Any]) -> dict[str, Any]:
    text = speakable_text_from_blocks(blocks)
    lowered = text.casefold()
    first = normalize_speakable_text(text)[:250].casefold()
    sentences = [item.strip() for item in _SENTENCE_RE.split(text) if item.strip()]
    long_sentences = [count_words(item) for item in sentences if count_words(item) > 38]
    sentence_lengths = [count_words(item) for item in sentences]
    paragraphs = [
        normalize_speakable_text(item)
        for item in re.split(r"\n\s*\n", text)
        if normalize_speakable_text(item)
    ]
    paragraph_openings = [
        " ".join(_WORD_RE.findall(item.casefold())[:3]) for item in paragraphs
    ]
    repeated_paragraph_openings = sorted(
        {
            opening
            for opening in paragraph_openings
            if opening and paragraph_openings.count(opening) >= 2
        }
    )[:20]
    words = [word.casefold() for word in _WORD_RE.findall(text)]
    ngrams: dict[tuple[str, ...], int] = {}
    for index in range(max(0, len(words) - 5)):
        gram = tuple(words[index : index + 6])
        ngrams[gram] = ngrams.get(gram, 0) + 1
    repeated = [" ".join(gram) for gram, count in ngrams.items() if count >= 2][:20]
    issues: list[str] = []
    missing_purpose = 0
    missing_beats = 0
    unverified_claims = 0
    for block in blocks:
        value = block if isinstance(block, dict) else vars(block)
        if not str(value.get("purpose") or "").strip():
            missing_purpose += 1
        if not value.get("beats"):
            missing_beats += 1
        for claim in value.get("claims") or []:
            claim_value = claim if isinstance(claim, dict) else vars(claim)
            tier = claim_value.get("evidence_tier")
            if getattr(tier, "value", tier) == "unverified":
                unverified_claims += 1
    if any(pattern in first for pattern in _GENERIC_HOOKS):
        issues.append("generic_hook")
    if repeated:
        issues.append("repeated_phrases")
    if long_sentences:
        issues.append("overlong_spoken_sentences")
    if missing_purpose:
        issues.append("missing_section_purpose")
    if missing_beats:
        issues.append("missing_editorial_beats")
    if unverified_claims:
        issues.append("unverified_claims")
    grandiosity = [item for item in _GRANDIOSITY_SIGNALS if item in lowered]
    robotic_transitions = [
        item for item in _ROBOTIC_TRANSITION_SIGNALS if item in lowered
    ]
    if grandiosity:
        issues.append("grandiosity_signals")
    if robotic_transitions:
        issues.append("robotic_transition_signals")
    if repeated_paragraph_openings:
        issues.append("repeated_paragraph_openings")
    return {
        "version": EDITORIAL_VALIDATOR_VERSION,
        "generic_hook": "generic_hook" in issues,
        "repeated_ngrams": repeated,
        "long_sentence_word_counts": long_sentences,
        "sentence_count": len(sentences),
        "sentence_length_distribution": {
            "median": round(statistics.median(sentence_lengths), 2)
            if sentence_lengths
            else 0,
            "p90": sorted(sentence_lengths)[
                min(len(sentence_lengths) - 1, int(len(sentence_lengths) * 0.9))
            ]
            if sentence_lengths
            else 0,
            "long_sentence_ratio": round(len(long_sentences) / len(sentence_lengths), 4)
            if sentence_lengths
            else 0,
        },
        "repeated_paragraph_openings": repeated_paragraph_openings,
        "grandiosity_signals": grandiosity,
        "robotic_transition_signals": robotic_transitions,
        "missing_section_purpose_count": missing_purpose,
        "missing_editorial_beats_count": missing_beats,
        "unverified_claim_count": unverified_claims,
        "issues": issues,
        "identity": _identity(
            {"version": EDITORIAL_VALIDATOR_VERSION, "text": lowered, "issues": issues}
        ),
    }


duration_calibration_client = DurationCalibrationClient()
