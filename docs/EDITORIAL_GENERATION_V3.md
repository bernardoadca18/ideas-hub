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

`editorial_generation_strategy_v2` chooses a bounded strategy from configured thresholds:

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
External search is query-bounded and deduplicated. Whether it is required is a versioned
`SourcePolicy` decision owned by the production profile. Search snippets are explicitly untrusted
data, never system instructions. Python classifies source trust by configured domain policy, then
extracts small source-local claims and builds the canonical, host-owned claim ledger. Source trust
and claim epistemic status are separate: even a reliable source may report a rumor, and an official
visual observation does not confirm a mechanic.

The canonical ledger intentionally keeps provenance-valid low-value observations. Before planning,
the host applies a narrow, topic-aware projection: search-result metadata and isolated community
preferences are withheld when they do not answer the editorial topic, but remain in the ledger and
become eligible for coverage/reception/community topics. This selection and its reasons are persisted
in planning provenance. It makes no LLM call and does not reinterpret claims.

Source authority remains independent from epistemic status. Profiles can classify official domains,
reputable secondary publishers and path-specific exceptions; a reliable secondary statement cannot
be promoted to `confirmed` merely because the publisher is reputable. Platform identity is not publisher identity: YouTube is
official only when the runtime has an explicit configured publisher path/account. An ordinary watch
URL remains community-classified rather than being guessed from its title.

The planner may select existing claim IDs for deterministic sections; it cannot mint claims.
Deterministic validation rejects unknown sources, unknown claims, incoherent source/claim links and
arbitrary evidence substitution. The post-write section audit, not the plan, records actual claim
usage and actual beat coverage. `author_briefing` remains editorial opinion, not factual proof.

Content capacity is advisory and visible before generation. It warns when the available evidence
is unlikely to sustain the selected target; it does not invent depth or automatically lower the
operator's target.

## LLM policy and prompts

The provider-neutral 9Router client owns connection pooling, context limits, native JSON Schema
with a controlled plain-JSON fallback, usage/latency provenance and bounded retries. Only network
errors, timeouts, 408, 429 and transient 5xx are retried. 400/401/403/422 are terminal. Structured
output recovery is finite: strict validation, narrow field-specific lossless normalization, one
shape-only repair, and (only for a multi-section planning batch) reuse of the existing batch split
when that repair is truncated. Empty output, malformed roots, missing semantics, unknown host IDs
and invalid singleton output after recovery remain terminal. Partial truncated JSON is not used.
Repair reserves role-local output headroom for providers where hidden reasoning and visible JSON
share the same output budget; the business layer does not select a provider.
The planning normalizer currently has one field-specific coercion:
`must_not_repeat: "instruction"` becomes the semantically identical one-item list. It does not
truncate text or coerce unrelated fields.

Routes are semantic combos, not provider names: `neovids-fast`, `neovids-standard`,
`neovids-strong` and `neovids-vision`. Policies are:

- `flash_only`: standard route for every editorial phase;
- `standard`: task routing without strong escalation by default;
- `hybrid`: strong planning/critic, standard section writer;
- `strong`: strong route throughout.

Embeddings are a separate infrastructure boundary: Ideas Hub calls the configured
Ollama `/api/embed` endpoint directly with `mxbai-embed-large:latest` and rejects
any response that is not exactly 1024-dimensional. Embedding calls do not pass
through `LLMGateway` or 9Router.

Repeated local budget failure may deterministically escalate when a distinct strong route exists;
the reason is persisted. Provider capability remains a property of the configured combo because decomposition,
local budgets and targeted revision do most of the reliability work.

Prompt precedence is: material factual safety, human revision direction, automatic diagnostics,
deterministic duration requirements and style guidance. The host owns claims, section licensing,
provenance, artifact scope and word deficits. Planners and auditors receive the shared quality
charter; the writer receives one spoken-PT-BR style policy rather than a duplicate copy of the
charter, plus a compact material-safety guardrail instead of the full audit policy. Section claims
appear once through their realization contracts rather than being duplicated as a second raw claim
list. Revision prompts use a compact projection of the complete durable `RevisionBrief`, so
human feedback, parent prose, diagnostics and exact deficits remain available without restating
the same issue through several fields. Factual audit feedback is projected into viewer-safe repair
language before it reaches the writer; the original diagnostic remains durable. External content is
delimited as data. Fragmented V3 calls use `editorial_prompt_composition_v9`; legacy workflows retain
`prompt_composition_v2`. Important identities are
`editorial_generation_strategy_v2`, `editorial_generation_plan_v1`,
`fragmented_editorial_planning_v1` and `editorial_prompt_composition_v9`.

After each section reaches capacity and word validation, a bounded structured critic audits the
full prose for factuality, unsupported specificity, uncertainty, spoken PT-BR, hook, continuity and
redundancy. Factual review is materiality-first: reasonable explanation or paraphrase can pass;
specific unsupported technical detail receives a warning or revision; new mechanisms, causal claims,
dates or capabilities require revision; and direct contradictions, fabricated official facts or
rumor promoted to confirmation remain blocking. Missing audit bookkeeping is not itself proof that
the prose is wrong. A targeted section revision may run within the existing revision limit. Continuity is
built from the audited output summary, actual claims and actual beats rather than planned metadata.
The staged global critic sees full prose; hierarchical long-form first produces chapter-local
audits and then a compact global pass. Global criticism is diagnostic: there is no automatic global
rewrite. The production-first path persists usable prose with review warnings, and the human
reviewer decides whether to approve it or start an explicit versioned revision. A section can still
receive at most one bounded local revision.

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
