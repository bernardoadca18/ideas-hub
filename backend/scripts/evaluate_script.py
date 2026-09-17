"""Inspect a production script without calling an LLM or TTS service."""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
from typing import Any

from app.production_profiles import get_profile
from app.schemas.roteiro import RoteiroEstrutura
from app.services.duration_contract import (
    DurationCalibration,
    duration_calibration_client,
    evaluate_duration,
    evaluate_editorial_quality,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Evaluate duration/editorial diagnostics for a script JSON file."
    )
    parser.add_argument("script", type=Path, help="JSON containing a script structure")
    parser.add_argument("--target-seconds", type=int)
    parser.add_argument("--profile", default="faceless_general")
    parser.add_argument(
        "--offline",
        action="store_true",
        help="Use the configured versioned fallback calibration; make no HTTP request.",
    )
    return parser.parse_args()


def _load_script(path: Path) -> RoteiroEstrutura:
    payload: Any = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, dict) and "estrutura" in payload:
        payload = payload["estrutura"]
    return RoteiroEstrutura.model_validate(payload)


async def main() -> int:
    args = parse_args()
    profile = get_profile(args.profile)
    structure = _load_script(args.script)
    calibration = (
        DurationCalibration.fallback_for(
            production_profile=profile.id,
            content_locale=structure.content_locale,
        )
        if args.offline
        else await duration_calibration_client.get(
            profile.id, structure.content_locale
        )
    )
    result = {
        "duration_contract": evaluate_duration(
            structure.blocos,
            target_seconds=args.target_seconds,
            calibration=calibration,
            profile=profile,
        ),
        "editorial_quality": evaluate_editorial_quality(structure.blocos),
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 2 if result["duration_contract"]["revision_required"] else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
