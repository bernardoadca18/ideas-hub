# Editorial duration contract

Ideas Hub separates three values:

- `target_duration_seconds`: author/profile intent;
- `predicted_duration_seconds`: deterministic estimate for the current speakable text;
- `actual_narration_duration_seconds`: factual accepted-TTS telemetry owned by Orchestrator.

Only each narrative block's `conteudo` is speakable. Titles, headings, VisualQueries,
`dicas_visual`, `dicas_audio`, claims and `audio_intent` are metadata and never enter the
duration count. The extractor contract is `speakable_text_blocks_v1`.

## Calibration and approval

Ideas Hub reads the versioned `accepted_take_speaking_rate_v1` snapshot from Orchestrator.
It never calls Qwen. If telemetry is unavailable, a configured and identity-bearing fallback
is used. Estimation combines calibrated words/minute and characters/second; snapshots record
sample count, source window, profile dimensions and identity.

`script_duration_contract_v1` derives total and per-section word budgets. A severe mismatch
such as a 12-minute target with roughly six minutes of speakable text is
`far_below_target`, requires revision and cannot be approved. The bounded reviser receives
the exact deficit and weak sections. It may add evidence, examples, contrast, context,
implications and payoff; filler and repeated recap are prohibited.

## Editorial structure and evidence

The system keeps the existing Curador, Roteirista and game-analysis specialization; no new
agent was introduced. Prompt composition is `script_prompt_composition_v2`; script workflows
are `roteiro_padrao_v2` and `roteiro_analise_jogos_v2`. A script may record lightweight:

- section purpose and beats;
- claims with evidence tier, source identity and confidence;
- structured music/audio intent without an asset path;
- deterministic hook, repetition and spoken-sentence diagnostics.

Evidence tiers distinguish official confirmation/observation, reliable secondary sources,
authenticated leaks, inference, speculation, unverified material, gameplay notes and author
opinion. Human notes remain authoritative for gameplay events; no model may invent timestamps.
The LLM critic is advisory. Deterministic duration validation owns the approval gate.

Run the CPU-only evaluation harness with:

```bash
PYTHONPATH=backend .venv/bin/pytest -q backend/tests/test_duration_contract.py
```
