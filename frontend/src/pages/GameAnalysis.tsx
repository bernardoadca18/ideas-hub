import { useEffect, useRef, useState } from 'react';
import { api, ContentLocale, DurationMode, GenerationRun } from '../api/client';

export default function GameAnalysis() {
  const [contentLocale, setContentLocale] = useState<ContentLocale>('pt-BR');
  const [title, setTitle] = useState('');
  const [game, setGame] = useState('');
  const [notes, setNotes] = useState('');
  const [briefing, setBriefing] = useState('');
  const [durationMode, setDurationMode] = useState<DurationMode>('content_driven');
  const [minutes, setMinutes] = useState('90');
  const [modelStrategy, setModelStrategy] = useState<'flash_only' | 'standard' | 'hybrid' | 'strong'>('standard');
  const [run, setRun] = useState<GenerationRun | null>(null);
  const [error, setError] = useState<string | null>(null);
  const controller = useRef<AbortController | null>(null);

  useEffect(() => () => controller.current?.abort(), []);

  async function start(event: React.FormEvent) {
    event.preventDefault();
    try {
      const created = await api.startGameGeneration({
        content_locale: contentLocale,
        titulo_provisorio: title,
        nome_jogo: game || undefined,
        anotacoes: notes,
        author_briefing: briefing || undefined,
        duration_mode: durationMode,
        target_duration_seconds: durationMode === 'explicit_target' ? Number(minutes) * 60 : undefined,
        usar_grounding: false,
        idempotency_key: crypto.randomUUID(),
        model_strategy: modelStrategy,
      });
      setRun(created);
      setError(null);
      void poll(created.id);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Falha ao iniciar geração');
    }
  }

  async function poll(runId: string) {
    controller.current?.abort();
    const current = new AbortController();
    controller.current = current;
    let delay = 1500;
    while (!current.signal.aborted) {
      try {
        const next = await api.getGenerationRun(runId, current.signal);
        setRun(next);
        if (['completed', 'failed', 'cancelled'].includes(next.status)) return;
        delay = 1500;
      } catch (reason) {
        if (current.signal.aborted) return;
        setError(reason instanceof Error ? reason.message : 'Falha ao consultar progresso');
        delay = Math.min(delay * 2, 10000);
      }
      await new Promise((resolve) => window.setTimeout(resolve, delay));
    }
  }

  return <div className="page">
    <div className="page-header"><h1>Game Analysis</h1></div>
    <p className="form-help">As notas humanas são evidência autoritativa. Gerações longas usam dossier, seções retomáveis e nunca mantêm a requisição HTTP aberta.</p>
    {error && <div className="error">{error}</div>}
    <form onSubmit={start} className="card">
      <div className="form-group"><label>Título provisório</label><input required maxLength={300} value={title} onChange={(event) => setTitle(event.target.value)} /></div>
      <div className="form-group"><label>Jogo</label><input maxLength={200} value={game} onChange={(event) => setGame(event.target.value)} /></div>
      <div className="form-group"><label>Notas de gameplay</label><textarea required minLength={20} rows={14} value={notes} onChange={(event) => setNotes(event.target.value)} /></div>
      <div className="form-group"><label>Contexto do autor</label><textarea rows={5} value={briefing} onChange={(event) => setBriefing(event.target.value)} /></div>
      <div className="form-group"><label htmlFor="game-content-locale">Idioma</label><select id="game-content-locale" value={contentLocale} onChange={(event) => setContentLocale(event.target.value as ContentLocale)}><option value="pt-BR">Português (Brasil)</option><option value="en-US">English (US)</option></select></div>
      <div className="form-group"><label>Duração</label><select value={durationMode} onChange={(event) => setDurationMode(event.target.value as DurationMode)}><option value="content_driven">Content-driven</option><option value="explicit_target">Target explícito</option></select></div>
      {durationMode === 'explicit_target' && <div className="form-group"><label>Minutos</label><input type="number" min={5} max={480} value={minutes} onChange={(event) => setMinutes(event.target.value)} required /></div>}
      <div className="form-group"><label>Política de modelo</label><select value={modelStrategy} onChange={(event) => setModelStrategy(event.target.value as typeof modelStrategy)}><option value="standard">Standard</option><option value="flash_only">Flash-only</option><option value="hybrid">Strong planner/critic + standard writer</option><option value="strong">Strong em todas as fases</option></select></div>
      <button className="btn btn-primary" type="submit" disabled={Boolean(run && !['completed', 'failed', 'cancelled'].includes(run.status))}>Iniciar geração durável</button>
    </form>
    {run && <div className="script-provenance">
      <strong>{run.phase} · {run.status}</strong>
      <p>{run.completed_sections}/{run.total_sections} seções · {run.generation_strategy} · target {run.target_duration_seconds ? `${run.target_duration_seconds / 60} min` : 'content-driven'}</p>
      {run.error_message && <p className="context-changed">{run.error_message}</p>}
    </div>}
  </div>;
}
