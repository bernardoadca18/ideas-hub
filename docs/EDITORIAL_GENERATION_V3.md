# Editorial generation v3

This document records the production contract introduced on 2026-08-30. It extends, rather
than replaces, `script_duration_contract_v1`.

## Duration intent

Every new idea resolves one explicit mode before generation:

- `explicit_target`: an operator-selected target; source is `user`;
- `profile_default`: the versioned profile target; source is `profile`;
- `content_driven`: deliberately open-ended; source is `content`.

Historical rows remain nullable and are reported as `historical_unresolved`. They are never
silently reinterpreted. A target is an editorial content contract. It is not repaired with TTS
speed, silence, time stretch, or filler. The calibration snapshot supplied by Orchestrator
turns target seconds into total and per-section word budgets.

The GTA regression fixture (945 speakable words, labels totaling about 11m30s) predicts about
6m23s and is `far_below_target` when the resolved target is 12 minutes. With no deliberate
target, it is only an estimate; the UI no longer reaches that state accidentally for profiles
that define a default.

## Generation strategies

`editorial_generation_strategy_v1` chooses a bounded strategy from configured thresholds:

- `single_pass`: small work, represented by one durable section;
- `staged`: an editorial plan followed by independently validated sections;
- `hierarchical_long_form`: chapters, five-minute-scale sections, compact continuity state and
  section-local evidence.

All strategies use the durable generation-run state machine. Long-form never expects a single
response to contain hours of narration. The worker checkpoints research, the plan and every
completed section. Resume keeps completed sections and only requeues the failed section.
Calls, sections and revisions have hard configured bounds. Duplicate HTTP submissions use an
idempotency key, and a row lock prevents two active runs for one idea.

States are `queued/running/completed/failed/cancelled`; phases are
`research/planning/writing/validating/assembling`. The browser polls serially with cancellation
and bounded backoff. Recent runs are reloadable from the API.

## Evidence and factuality

Human gameplay notes are authoritative evidence for observed gameplay. They are fragmented and
indexed with stable source IDs; no LLM may create timestamps, UUIDs, actions or dialogue.
External search is optional, query-bounded and deduplicated. Search snippets are explicitly
untrusted data with `unknown_unverified` source quality, never system instructions.

The planner emits a typed claim ledger with evidence tiers and source references. Deterministic
validation rejects duplicate claim IDs, unknown sources and section output that cites a claim
outside the approved ledger. `author_briefing` remains editorial opinion, not factual proof.

Content capacity is advisory and visible before generation. It warns when the available evidence
is unlikely to sustain the selected target; it does not invent depth or automatically lower the
operator's target.

## LLM policy and prompts

The provider-neutral LiteLLM gateway owns connection pooling, context limits, native JSON Schema
with a controlled plain-JSON fallback, usage/latency provenance and bounded retries. Only network
errors, timeouts, 408, 429 and transient 5xx are retried. 400/401/403/422 are terminal. A bounded
repair call may repair serialization/schema shape but must preserve content and claims.

Routes are aliases, not provider names: `fast`, `standard`, and optional `strong`. Policies are:

- `flash_only`: standard route for every editorial phase;
- `standard`: task routing without strong escalation by default;
- `hybrid`: strong planning/critic, standard section writer;
- `strong`: strong route throughout.

Repeated local budget failure may deterministically escalate when a distinct strong route exists;
the reason is persisted. Gemini Flash remains viable as the standard route because decomposition,
local budgets and targeted revision do most of the reliability work.

Prompt precedence is: global safety/factuality, production profile, workflow, bounded evidence,
author briefing, deterministic section plan, targeted revision feedback. External content is
delimited as data. Important identities are `prompt_composition_v2`,
`editorial_generation_strategy_v1`, `editorial_generation_plan_v1` and
`hierarchical_script_composition_v1`.

## Operations

Apply migration `0005_editorial_runs` before starting the generation worker. Do not run it against
a live database without the normal backup/change window. New Docker volumes execute
`001_init.sql` and then `002_alembic_baseline.sql`, which records the historical `0001` marker;
subsequent migrations can therefore advance normally. For an existing database, first require
`alembic current` to report its real revision. Never stamp an existing database blindly.

```bash
cd /home/bernardo/workspaces/neovids/ideas-hub/backend
.venv/bin/alembic current
.venv/bin/alembic upgrade head
cd ..
docker compose up -d --build backend generation-worker frontend
```

Previewing a plan performs no LLM call. Live model comparisons are opt-in and plan-only unless
`--run` is supplied:

```bash
PYTHONPATH=backend .venv/bin/python backend/scripts/benchmark_model_strategies.py \
  --idea-id '<IDEA_UUID>' --output artifacts/model-strategy-benchmark
```

Unit tests use fake gateways and never call an external provider.
