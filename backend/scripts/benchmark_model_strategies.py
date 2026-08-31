#!/usr/bin/env python3
"""Opt-in comparison of Flash-only, hybrid and strong editorial model policies."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

import httpx

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


def _write_atomic(path: Path, payload: object) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    os.replace(temporary, path)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--idea-id", type=UUID, required=True)
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument(
        "--output", type=Path, default=Path("model-strategy-benchmarks")
    )
    parser.add_argument(
        "--strategies",
        nargs="+",
        choices=("flash_only", "hybrid", "strong"),
        default=["flash_only", "hybrid", "strong"],
    )
    parser.add_argument("--poll-seconds", type=float, default=3.0)
    parser.add_argument("--run", action="store_true")
    args = parser.parse_args()
    matrix_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid4().hex[:8]
    print(f"Idea: {args.idea_id}")
    print(f"Strategies: {', '.join(args.strategies)}")
    if not args.run:
        print(
            "PLAN ONLY: no API or LLM calls. Add --run to execute sequential durable runs."
        )
        return 0

    run_dir = args.output.resolve() / matrix_id
    run_dir.mkdir(parents=True, exist_ok=False)
    records: list[dict[str, object]] = []
    with httpx.Client(timeout=30.0, base_url=args.base_url.rstrip("/")) as client:
        for strategy in args.strategies:
            idempotency_key = f"model-benchmark:{matrix_id}:{strategy}"
            response = client.post(
                f"/ideias/{args.idea_id}/generation-runs",
                json={
                    "idempotency_key": idempotency_key,
                    "model_strategy": strategy,
                },
            )
            response.raise_for_status()
            run = response.json()
            print(f"{strategy}: run={run['id']} queued")
            while run["status"] not in {"completed", "failed", "cancelled"}:
                time.sleep(max(0.5, args.poll_seconds))
                response = client.get(f"/generation-runs/{run['id']}")
                response.raise_for_status()
                run = response.json()
                print(
                    f"{strategy}: {run['phase']} "
                    f"{run['completed_sections']}/{run['total_sections']}"
                )
            records.append(
                {
                    "strategy": strategy,
                    "run": run,
                    "metrics": {
                        "call_usage": run.get("call_usage"),
                        "target_words": run.get("target_words"),
                        "status": run.get("status"),
                        "failure_category": run.get("error_category"),
                    },
                }
            )
            if run["status"] != "completed":
                _write_atomic(
                    run_dir / "manifest.json",
                    {"matrix_id": matrix_id, "records": records},
                )
                print(
                    "Stopped: a strategy did not complete; earlier durable results were preserved."
                )
                return 2
    _write_atomic(
        run_dir / "manifest.json",
        {
            "matrix_id": matrix_id,
            "created_at": datetime.now(UTC).isoformat(),
            "idea_id": str(args.idea_id),
            "purpose": "manual editorial model-policy comparison",
            "automatic_winner": False,
            "records": records,
        },
    )
    (run_dir / "READING.csv").write_text(
        "strategy,script_version,factuality,hook,depth,redundancy,natural_ptbr,coherence,transitions,duration_adherence,filler,unsupported_claims,notes\n"
        + "\n".join(f"{item['strategy']},,,,,,,,,,,," for item in records)
        + "\n",
        encoding="utf-8",
    )
    print(f"Completed: {run_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
