import { useEffect, useState } from 'react';
import {
  api,
  ContentLocale,
  GenerationRun,
  Ideia,
  ManualScriptDocumentV1,
  ManualScriptImportPreview,
  Roteiro,
  ScriptEditRevision,
} from '../api/client';

function formatDuration(seconds: number) {
  const minutes = Math.floor(seconds / 60);
  const secs = seconds % 60;
  return `${minutes}:${secs.toString().padStart(2, '0')}`;
}

function statusColor(status: string) {
  if (status === 'aprovado') return '#10b981';
  if (status === 'rejeitado') return '#ef4444';
  return '#6b7280';
}

function durationStatusColor(status?: string) {
  if (status === 'excellent' || status === 'acceptable' || status === 'estimate_only') return '#10b981';
  if (status === 'below_target' || status === 'above_target') return '#f59e0b';
  return '#ef4444';
}

function auditStatusColor(status?: string) {
  if (status === 'pass' || status === 'completed') return '#10b981';
  if (status === 'warn') return '#f59e0b';
  if (status === 'blocking' || status === 'needs_revision') return '#ef4444';
  return '#6b7280';
}

function hasEditorialBlockers(script: Roteiro) {
  return script.estrutura.editorial_review?.approval_blocked === true;
}

function hasReviewWarnings(script: Roteiro): boolean {
  const review = script.estrutura.editorial_review;
  if (!review) return false;
  // Check for high factual risk or needs_review states in sections
  const sections = script.estrutura.blocos || [];
  return sections.some((block: any) =>
    block.review_state === 'high_factual_risk' ||
    block.review_state === 'needs_review' ||
    (block.section_audit?.issues?.length > 0)
  );
}

export default function Roteiros() {
  const [roteiros, setRoteiros] = useState<Roteiro[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [statusFilter, setStatusFilter] = useState('');
  const [selected, setSelected] = useState<Roteiro | null>(null);
  const [editDraft, setEditDraft] = useState<ScriptEditRevision | null>(null);
  const [feedback, setFeedback] = useState('');
  const [regenerating, setRegenerating] = useState(false);
  const [revisionRun, setRevisionRun] = useState<GenerationRun | null>(null);

  const [showImportModal, setShowImportModal] = useState(false);
  const [importLocale, setImportLocale] = useState<ContentLocale>('pt-BR');
  const [importIdeaId, setImportIdeaId] = useState('');
  const [importFile, setImportFile] = useState<{
    filename: string;
    script: ManualScriptDocumentV1;
  } | null>(null);
  const [importPreview, setImportPreview] = useState<ManualScriptImportPreview | null>(null);
  const [importError, setImportError] = useState<string | null>(null);
  const [validatingImport, setValidatingImport] = useState(false);
  const [importingScript, setImportingScript] = useState(false);
  const [importNotice, setImportNotice] = useState<string | null>(null);

  // Manual script creation state
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [ideias, setIdeias] = useState<Ideia[]>([]);
  const [createDraft, setCreateDraft] = useState<{
    ideia_id: string;
    content_locale: ContentLocale;
    titulo: string;
    blocos: Array<{ tipo: string; duracao_segundos: number; conteudo: string; dicas_visual: string; dicas_audio: string }>;
    tags: string[];
    referencias: string;
  }>({
    ideia_id: '',
    content_locale: 'pt-BR',
    titulo: '',
    blocos: [{ tipo: 'introducao', duracao_segundos: 30, conteudo: '', dicas_visual: '', dicas_audio: '' }],
    tags: [],
    referencias: '',
  });
  const [creating, setCreating] = useState(false);

  useEffect(() => { void loadData(); }, [statusFilter]);

  async function loadData() {
    try {
      setLoading(true);
      setRoteiros(await api.getRoteiros(statusFilter ? { status: statusFilter } : undefined));
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Erro ao carregar roteiros');
    } finally {
      setLoading(false);
    }
  }

  async function loadIdeias() {
    try {
      setIdeias(await api.getIdeias());
    } catch (err) {
      console.error('Failed to load ideias:', err);
    }
  }

  function resetImport() {
    setImportIdeaId('');
    setImportLocale('pt-BR');
    setImportFile(null);
    setImportPreview(null);
    setImportError(null);
    setValidatingImport(false);
    setImportingScript(false);
  }

  async function selectImportFile(file?: File) {
    setImportPreview(null);
    setImportError(null);
    setImportFile(null);
    if (!file) return;
    if (!file.name.toLowerCase().endsWith('.json')) {
      setImportError('Selecione um arquivo .json.');
      return;
    }
    if (file.size > 1_000_000) {
      setImportError('O arquivo excede o limite de 1 MB.');
      return;
    }
    try {
      const parsed: unknown = JSON.parse(await file.text());
      if (typeof parsed !== 'object' || parsed === null || Array.isArray(parsed)) {
        throw new Error('O conteúdo JSON precisa ser um objeto.');
      }
      if ('content_locale' in parsed && (parsed.content_locale === 'pt-BR' || parsed.content_locale === 'en-US')) setImportLocale(parsed.content_locale);
      setImportFile({ filename: file.name, script: parsed as ManualScriptDocumentV1 });
    } catch (err) {
      setImportError(err instanceof Error ? err.message : 'JSON inválido.');
    }
  }

  async function validateImport() {
    setImportPreview(null);
    setImportError(null);
    if (!importIdeaId) {
      setImportError('Selecione uma Idea antes de validar.');
      return;
    }
    if (!importFile) {
      setImportError('Selecione um arquivo JSON válido.');
      return;
    }
    try {
      setValidatingImport(true);
      const preview = await api.previewManualScriptImport({
        ideia_id: importIdeaId,
        content_locale: importLocale,
        source_filename: importFile.filename,
        script: importFile.script,
      });
      setImportPreview(preview);
    } catch (err) {
      setImportError(err instanceof Error ? err.message : 'Falha ao validar o roteiro.');
    } finally {
      setValidatingImport(false);
    }
  }

  async function persistImport() {
    if (!importIdeaId || !importFile || !importPreview?.importable) return;
    setImportError(null);
    try {
      setImportingScript(true);
      const result = await api.importManualScript({
        ideia_id: importIdeaId,
        content_locale: importLocale,
        source_filename: importFile.filename,
        script: importFile.script,
      });
      setImportNotice(
        result.duplicate
          ? `Este conteúdo já havia sido importado. Versão atual: ${result.current_revision.versao}.`
          : `Roteiro manual importado. ${result.draft.revision_kind} v${result.draft.versao}${result.media_binding_applied ? ` → media_binding v${result.current_revision.versao}` : ''}.`,
      );
      setSelected(result.current_revision);
      setShowImportModal(false);
      resetImport();
      await loadData();
    } catch (err) {
      setImportError(err instanceof Error ? err.message : 'Falha ao importar o roteiro.');
    } finally {
      setImportingScript(false);
    }
  }

  async function handleCreateManual(e: React.FormEvent) {
    e.preventDefault();
    if (!createDraft.ideia_id || !createDraft.titulo.trim() || createDraft.blocos.length === 0) {
      setError('Preencha ideia, título e pelo menos um bloco');
      return;
    }
    try {
      setCreating(true);
      await api.createManualDraft({
        ideia_id: createDraft.ideia_id,
        content_locale: createDraft.content_locale,
        titulo: createDraft.titulo,
        blocos: createDraft.blocos.filter(b => b.conteudo.trim()),
        tags: createDraft.tags.filter(t => t.trim()),
        referencias: createDraft.referencias.trim() ? [createDraft.referencias.trim()] : undefined,
      });
      setShowCreateModal(false);
      setCreateDraft({
        ideia_id: '',
        content_locale: 'pt-BR',
        titulo: '',
        blocos: [{ tipo: 'introducao', duracao_segundos: 30, conteudo: '', dicas_visual: '', dicas_audio: '' }],
        tags: [],
        referencias: '',
      });
      loadData();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Erro ao criar roteiro');
    } finally {
      setCreating(false);
    }
  }

  function addBlock() {
    setCreateDraft(d => ({
      ...d,
      blocos: [...d.blocos, { tipo: 'desenvolvimento', duracao_segundos: 60, conteudo: '', dicas_visual: '', dicas_audio: '' }],
    }));
  }

  function removeBlock(index: number) {
    setCreateDraft(d => ({
      ...d,
      blocos: d.blocos.filter((_, i) => i !== index),
    }));
  }

  function updateCreateBlock(index: number, field: string, value: string | number) {
    setCreateDraft(d => ({
      ...d,
      blocos: d.blocos.map((b, i) => (i === index ? { ...b, [field]: value } : b)),
    }));
  }

  async function approve(script: Roteiro) {
    const latestVersion = latestVersionByIdea.get(script.ideia_id);
    if (
      latestVersion !== undefined
      && script.versao !== latestVersion
      && !window.confirm(
        `Esta não é a revisão mais recente. Versão escolhida: v${script.versao}. Versão mais recente: v${latestVersion}. Deseja aprovar esta revisão mesmo assim?`,
      )
    ) {
      return;
    }
    if (
      hasEditorialBlockers(script)
      && !window.confirm(
        'A revisão editorial marcou este roteiro com bloqueadores. Revise os apontamentos antes de decidir. Deseja aprovar mesmo assim?',
      )
    ) {
      return;
    }
    try {
      await api.aprovarRoteiro(script.id);
      setSelected(null);
      await loadData();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Erro ao aprovar roteiro');
    }
  }

  async function reject(script: Roteiro) {
    try {
      await api.rejeitarRoteiro(script.id);
      setSelected(null);
      await loadData();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Erro ao rejeitar roteiro');
    }
  }

  function beginEdit(script: Roteiro) {
    setEditDraft({
      titulo: script.estrutura.titulo,
      blocos: script.estrutura.blocos.map((block) => ({
        tipo: block.tipo,
        duracao_segundos: block.duracao_segundos,
        conteudo: block.conteudo,
        dicas_visual: block.dicas_visual,
        dicas_audio: block.dicas_audio,
      })),
      tags: [...script.estrutura.tags],
      referencias: script.estrutura.referencias ? [...script.estrutura.referencias] : undefined,
      edit_summary: '',
    });
  }

  async function saveEdit(e: React.FormEvent) {
    e.preventDefault();
    if (!selected || !editDraft) return;
    try {
      const created = await api.editarRoteiroComoRevisao(selected.id, editDraft);
      setSelected(created);
      setEditDraft(null);
      await loadData();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Erro ao criar revisão');
    }
  }

  async function regenerate(e: React.FormEvent) {
    e.preventDefault();
    if (!selected) return;
    setRegenerating(true);
    try {
      let run = await api.startRevisionGenerationRun(selected.id, feedback.trim() || undefined, crypto.randomUUID());
      setRevisionRun(run);
      let delayMs = 1500;
      while (!['completed', 'failed', 'cancelled'].includes(run.status)) {
        await new Promise((resolve) => window.setTimeout(resolve, delayMs));
        run = await api.getGenerationRun(run.id);
        setRevisionRun(run);
        delayMs = Math.min(delayMs * 1.25, 5000);
      }
      if (run.status !== 'completed' || !run.roteiro_id) {
        throw new Error(run.error_message || `A regeneração terminou com status ${run.status}`);
      }
      const created = await api.getRoteiro(run.roteiro_id);
      setSelected(created);
      setFeedback('');
      await loadData();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Erro ao regenerar roteiro');
    } finally {
      setRegenerating(false);
    }
  }

  async function reaudit(script: Roteiro) {
    setRegenerating(true);
    try {
      let run = await api.startRoteiroAudit(script.id, crypto.randomUUID());
      setRevisionRun(run);
      while (!['completed', 'failed', 'cancelled'].includes(run.status)) {
        await new Promise((resolve) => window.setTimeout(resolve, 1500));
        run = await api.getGenerationRun(run.id);
        setRevisionRun(run);
      }
      if (run.status !== 'completed' || !run.roteiro_id) {
        throw new Error(run.error_message || `O re-audit terminou com status ${run.status}`);
      }
      const created = await api.getRoteiro(run.roteiro_id);
      setSelected(created);
      await loadData();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Erro ao revalidar roteiro');
    } finally {
      setRegenerating(false);
    }
  }

  function updateBlock(index: number, field: keyof ScriptEditRevision['blocos'][number], value: string | number) {
    if (!editDraft) return;
    const blocks = editDraft.blocos.map((block, current) => current === index ? { ...block, [field]: value } : block);
    setEditDraft({ ...editDraft, blocos: blocks });
  }

  if (loading) return <div className="loading">Carregando...</div>;

  const latestVersionByIdea = new Map<string, number>();
  for (const script of roteiros) {
    latestVersionByIdea.set(
      script.ideia_id,
      Math.max(latestVersionByIdea.get(script.ideia_id) || 0, script.versao),
    );
  }
  const selectedIsLatest = selected
    ? selected.versao === latestVersionByIdea.get(selected.ideia_id)
    : false;
  const selectedParent = selected?.parent_roteiro_id
    ? roteiros.find((script) => script.id === selected.parent_roteiro_id)
    : undefined;

  return (
    <div className="page">
      <div className="page-header">
        <h1>Roteiros</h1>
        <div className="actions">
          <button
            className="btn btn-primary"
            onClick={() => { resetImport(); setShowImportModal(true); void loadIdeias(); }}
          >
            Importar roteiro
          </button>
          <button
            className="btn btn-secondary"
            onClick={() => { setShowCreateModal(true); void loadIdeias(); }}
          >
            + Criar manualmente
          </button>
        </div>
      </div>
      {error && <div className="error">{error} <button onClick={() => setError(null)}>Fechar</button></div>}
      {importNotice && <div className="success">{importNotice} <button onClick={() => setImportNotice(null)}>Fechar</button></div>}
      <div className="filters">
        <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}>
          <option value="">Todos os status</option>
          <option value="rascunho">Rascunho</option>
          <option value="aprovado">Aprovado</option>
          <option value="rejeitado">Rejeitado</option>
        </select>
      </div>

      {selected && (
        <div className="modal-overlay" onClick={() => { setSelected(null); setEditDraft(null); }}>
          <div className="modal modal-large" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h2>{editDraft ? 'Nova revisão humana' : selected.estrutura.titulo}</h2>
              <button onClick={() => { setSelected(null); setEditDraft(null); }} className="btn-close">×</button>
            </div>

            {editDraft ? (
              <form onSubmit={saveEdit}>
                <p className="form-help">A revisão cria uma nova versão. IDs, timestamps e provenance de VisualQueries são preservados e não são editáveis aqui.</p>
                <div className="form-group"><label>Título</label><input value={editDraft.titulo} onChange={(e) => setEditDraft({ ...editDraft, titulo: e.target.value })} required /></div>
                {editDraft.blocos.map((block, index) => (
                  <fieldset className="script-edit-block" key={index}>
                    <legend>Bloco {index + 1}</legend>
                    <div className="form-group"><label>Tipo editorial</label><input value={block.tipo} onChange={(e) => updateBlock(index, 'tipo', e.target.value)} required /></div>
                    <div className="form-group"><label>Duração estimada (segundos)</label><input type="number" min={1} value={block.duracao_segundos} onChange={(e) => updateBlock(index, 'duracao_segundos', Number(e.target.value))} required /></div>
                    <div className="form-group"><label>Narração</label><textarea rows={8} value={block.conteudo} onChange={(e) => updateBlock(index, 'conteudo', e.target.value)} required /></div>
                    <div className="form-group"><label>Dicas visuais</label><textarea rows={3} value={block.dicas_visual || ''} onChange={(e) => updateBlock(index, 'dicas_visual', e.target.value)} /></div>
                    <div className="form-group"><label>Dicas de áudio</label><textarea rows={3} value={block.dicas_audio || ''} onChange={(e) => updateBlock(index, 'dicas_audio', e.target.value)} /></div>
                    <small>{selected.estrutura.blocos[index].visual_queries?.length || 0} VisualQueries preservadas sem alteração.</small>
                  </fieldset>
                ))}
                <div className="form-group"><label>Resumo da edição (opcional)</label><textarea rows={3} value={editDraft.edit_summary || ''} onChange={(e) => setEditDraft({ ...editDraft, edit_summary: e.target.value })} /></div>
                <div className="form-actions"><button type="button" className="btn btn-secondary" onClick={() => setEditDraft(null)}>Cancelar</button><button className="btn btn-primary" type="submit">Salvar como nova versão</button></div>
              </form>
            ) : (
              <>
                <div className="roteiro-info">
                  <span className="status-badge" style={{ backgroundColor: statusColor(selected.status) }}>{selected.status}</span>
                  <span>Versão {selected.versao}</span>
                  <span>Target: {selected.estrutura.duration_contract?.target_duration_seconds ? formatDuration(selected.estrutura.duration_contract.target_duration_seconds) : 'não definido'}</span>
                  <span>Predicted: {formatDuration(Math.round(selected.estrutura.duration_contract?.predicted_duration_seconds || 0))}</span>
                  <span>{selected.estrutura.duration_contract?.speakable_words || 0} palavras narráveis</span>
                  <span>{selected.estrutura.blocos.length} blocos</span>
                  <span>Origem: {selected.revision_kind}</span>
                </div>
                {!selectedIsLatest && (
                  <div className="review-warnings-banner" style={{ marginTop: '1rem', padding: '0.75rem', backgroundColor: '#fef3c7', border: '1px solid #f59e0b', borderRadius: '4px' }}>
                    <strong>⚠ Esta não é a revisão mais recente.</strong>
                    <p style={{ margin: '0.5rem 0 0 0', fontSize: '0.9rem' }}>
                      Versão escolhida: v{selected.versao}. Versão mais recente: v{latestVersionByIdea.get(selected.ideia_id)}. Você ainda pode aprovar esta revisão explicitamente.
                    </p>
                  </div>
                )}
                {selected.estrutura.manual_draft && (
                  <div className="script-provenance">
                    <strong>Rascunho humano original</strong>
                    <p>Texto colado no Ideas Hub e preservado nesta revisão manual.</p>
                    <code>{selected.estrutura.manual_draft.original_text_sha256}</code>
                  </div>
                )}
                {selected.parent_roteiro_id && (
                  <div className="script-provenance">
                    <strong>Linhagem</strong>
                    <p>Esta versão foi criada a partir de {selectedParent ? `v${selectedParent.versao} · ${selectedParent.revision_kind}` : selected.parent_roteiro_id}.</p>
                    {selectedParent && (
                      <button
                        type="button"
                        className="btn btn-sm btn-secondary"
                        onClick={() => { setSelected(selectedParent); setFeedback(''); }}
                      >Abrir versão pai para comparar</button>
                    )}
                  </div>
                )}
                {selected.estrutura.duration_contract && (
                  <div className="script-provenance">
                    <strong style={{ color: durationStatusColor(selected.estrutura.duration_contract.status) }}>
                      Duração: {selected.estrutura.duration_contract.status.replace(/_/g, ' ').toUpperCase()}
                    </strong>
                    <p>
                      Delta previsto: {selected.estrutura.duration_contract.delta_seconds === null
                        ? '—'
                        : `${selected.estrutura.duration_contract.delta_seconds > 0 ? '+' : ''}${formatDuration(Math.abs(Math.round(selected.estrutura.duration_contract.delta_seconds)))}`}
                    </p>
                    <details>
                      <summary>Orçamento por seção</summary>
                      <ul>{selected.estrutura.duration_contract.sections.map((section) => (
                        <li key={section.index}>{section.type}: target {section.target_words || '—'} palavras · atual {section.actual_words} · predicted {formatDuration(Math.round(section.predicted_duration_seconds))} · {section.status}</li>
                      ))}</ul>
                    </details>
                  </div>
                )}
                <div className="script-provenance">
                  <strong style={{ color: auditStatusColor(selected.estrutura.editorial_review?.editorial_status) }}>
                    EDITORIAL: {(selected.estrutura.editorial_review?.editorial_status || 'unvalidated').replace(/_/g, ' ').toUpperCase()}
                  </strong>
                  {' · '}
                  <strong style={{ color: auditStatusColor(selected.estrutura.editorial_review?.factuality_status) }}>
                    FACTUALITY: {(selected.estrutura.editorial_review?.factuality_status || 'unvalidated').toUpperCase()}
                  </strong>
                  <p>{selected.estrutura.editorial_review?.global_summary || 'Este roteiro não possui auditoria Editorial V3 persistida.'}</p>
                  {selected.estrutura.editorial_review?.audit_status !== 'completed' && <p className="context-changed"><strong>AUDIT STALE / RE-AUDIT REQUIRED</strong></p>}
                  {(selected.estrutura.editorial_review?.global_issues?.length || 0) > 0 && (
                    <details open>
                      <summary>Issues globais ({selected.estrutura.editorial_review?.global_issues?.length})</summary>
                      <ul>{selected.estrutura.editorial_review?.global_issues?.map((issue, index) => (
                        <li key={`${issue.section_key || 'global'}-${issue.category}-${index}`}>
                          <strong>{issue.severity.toUpperCase()} · {issue.category}</strong>
                          {issue.section_key ? ` · ${issue.section_key}` : ''}: {issue.actionable_feedback}
                          {issue.excerpt && <blockquote>{issue.excerpt}</blockquote>}
                        </li>
                      ))}</ul>
                    </details>
                  )}
                  {(selected.estrutura.evidence_provenance?.sources?.length || 0) > 0 && (
                    <details>
                      <summary>Fontes ({selected.estrutura.evidence_provenance?.sources?.length})</summary>
                      <ul>{selected.estrutura.evidence_provenance?.sources?.map((source, index) => (
                        <li key={source.source_id || index}>
                          {source.url ? <a href={source.url} target="_blank" rel="noreferrer">{source.title || source.domain || source.url}</a> : (source.title || source.source_id)}
                          {' · '}{source.source_trust || 'unverified'}
                        </li>
                      ))}</ul>
                    </details>
                  )}
                  {(selected.estrutura.evidence_provenance?.claim_ledger?.length || 0) > 0 && (
                    <details>
                      <summary>Claims aprovados ({selected.estrutura.evidence_provenance?.claim_ledger?.length})</summary>
                      <ul>{selected.estrutura.evidence_provenance?.claim_ledger?.map((claim) => (
                        <li key={claim.id}><code>{claim.id}</code> · {claim.claim_status || 'unknown'} · {claim.source_trust || 'unverified'} — {claim.summary}</li>
                      ))}</ul>
                    </details>
                  )}
                </div>
                <div className="script-provenance">
                  <strong>Contexto do autor usado nesta versão</strong>
                  <p>{selected.author_briefing_snapshot || 'Nenhum contexto fornecido.'}</p>
                  <code>{selected.author_briefing_identity || 'snapshot histórico indisponível'}</code>
                  {selected.author_briefing_changed_since_creation === true && <span className="context-changed">O contexto atual da ideia mudou desde esta versão.</span>}
                </div>
                <div className="blocos-list">
                  {selected.estrutura.blocos.map((block, index) => (
                    <details key={index} className="bloco-card" open={selected.estrutura.blocos.length <= 10 || index === 0}>
                      <summary className="bloco-header"><h4>{block.tipo}</h4><span>{formatDuration(block.duracao_segundos)}</span></summary>
                      {block.purpose && <div className="bloco-dica"><strong>Propósito:</strong> {block.purpose}</div>}
                      {selected.estrutura.duration_contract?.sections[index] && <div className="bloco-dica">
                        <strong>Contrato:</strong> target {selected.estrutura.duration_contract.sections[index].target_words || '—'} palavras · atual {selected.estrutura.duration_contract.sections[index].actual_words} · predicted {formatDuration(Math.round(selected.estrutura.duration_contract.sections[index].predicted_duration_seconds))} · {selected.estrutura.duration_contract.sections[index].status}
                      </div>}
                      {(block.beats?.length || 0) > 0 && <details><summary>Beats editoriais ({block.beats?.length})</summary><pre>{JSON.stringify(block.beats, null, 2)}</pre></details>}
                      {(block.planned_beats?.length || 0) > 0 && <details><summary>Beats planejados ({block.planned_beats?.length})</summary><pre>{JSON.stringify(block.planned_beats, null, 2)}</pre></details>}
                      {selected.estrutura.section_audits?.[`section-${String(index + 1).padStart(3, '0')}`] && <details>
                        <summary>Auditoria da seção</summary>
                        <pre>{JSON.stringify(selected.estrutura.section_audits[`section-${String(index + 1).padStart(3, '0')}`], null, 2)}</pre>
                      </details>}
                      <div className="bloco-conteudo"><p>{block.conteudo}</p></div>
                      {block.dicas_visual && <div className="bloco-dica"><strong>Visual:</strong> {block.dicas_visual}</div>}
                      {block.dicas_audio && <div className="bloco-dica"><strong>Áudio:</strong> {block.dicas_audio}</div>}
                      {(block.visual_queries?.length || 0) > 0 && <div className="bloco-dica"><strong>VisualQueries:</strong> {block.visual_queries?.length} preservadas com provenance.</div>}
                    </details>
                  ))}
                </div>
                <div className="revision-actions">
                  <button className="btn btn-secondary" onClick={() => beginEdit(selected)}>Editar</button>
                  <form onSubmit={regenerate} className="feedback-form">
                    <label htmlFor="revision-feedback"><strong>Melhorar / Regenerar</strong></label>
                    <textarea id="revision-feedback" rows={3} value={feedback} onChange={(e) => setFeedback(e.target.value)} placeholder="Feedback adicional (opcional). Ex.: preserve a introdução e torne a seção 2 mais concreta." />
                    <p className="form-help">O sistema usará automaticamente os diagnósticos editoriais globais, as auditorias por seção e o contrato de duração atual.</p>
                    <button className="btn btn-primary" disabled={regenerating} type="submit">{regenerating ? 'Melhorando…' : 'Criar nova versão melhorada'}</button>
                    {revisionRun && regenerating && <span className="form-help">{revisionRun.phase} · {revisionRun.completed_sections}/{revisionRun.total_sections} seções</span>}
                  </form>
                  {selected.estrutura.editorial_review?.audit_status !== 'completed' && <button className="btn btn-primary" disabled={regenerating} onClick={() => void reaudit(selected)}>Revalidar texto atual</button>}
                  {hasReviewWarnings(selected) && (
                    <div className="review-warnings-banner" style={{ marginTop: '1rem', padding: '0.75rem', backgroundColor: '#fef3c7', border: '1px solid #f59e0b', borderRadius: '4px' }}>
                      <strong>⚠️ Avisos de revisão detectados</strong>
                      <p style={{ margin: '0.5rem 0 0 0', fontSize: '0.9rem' }}>
                        Este roteiro contém questões editoriais ou factuais que requerem atenção.
                        Revise os blocos marcados abaixo antes de decidir. A aprovação manual continua disponível.
                      </p>
                    </div>
                  )}
                  {hasEditorialBlockers(selected) && (
                    <div className="review-warnings-banner" style={{ marginTop: '1rem', padding: '0.75rem', backgroundColor: '#fef3c7', border: '1px solid #f59e0b', borderRadius: '4px' }}>
                      <strong>⚠ Revisão editorial encontrou bloqueadores.</strong>
                      <p style={{ margin: '0.5rem 0 0 0', fontSize: '0.9rem' }}>
                        Revise os apontamentos antes de decidir. A aprovação manual continua disponível.
                      </p>
                    </div>
                  )}
                </div>
                {selected.status === 'rascunho' && <div className="modal-footer">{selectedIsLatest && <button onClick={() => reject(selected)} className="btn btn-danger">Rejeitar</button>}<button onClick={() => approve(selected)} className="btn btn-success">Aprovar esta versão</button></div>}
              </>
            )}
          </div>
        </div>
      )}

      <div className="list">
        {roteiros.length === 0 ? <div className="empty-state">Nenhum roteiro encontrado</div> : roteiros.map((script) => (
          <div key={script.id} className="card">
            <div className="card-header"><h3 className="card-title">{script.estrutura.titulo}</h3><span className="status-badge" style={{ backgroundColor: statusColor(script.status) }}>{script.status}</span></div>
            <div className="card-meta"><span>Versão: {script.versao}</span><span>Origem: {script.revision_kind}</span><span>Target: {script.estrutura.duration_contract?.target_duration_seconds ? formatDuration(script.estrutura.duration_contract.target_duration_seconds) : '—'}</span><span>Predicted: {formatDuration(Math.round(script.estrutura.duration_contract?.predicted_duration_seconds || 0))}</span><span style={{ color: durationStatusColor(script.estrutura.duration_contract?.status) }}>{script.estrutura.duration_contract?.status || 'legacy/unvalidated'}</span><span style={{ color: auditStatusColor(script.estrutura.editorial_review?.editorial_status) }}>Editorial: {script.estrutura.editorial_review?.editorial_status || 'unvalidated'}</span><span style={{ color: auditStatusColor(script.estrutura.editorial_review?.factuality_status) }}>Factuality: {script.estrutura.editorial_review?.factuality_status || 'unvalidated'}</span><span>Ideia: {script.ideia_id.slice(0, 8)}…</span></div>
            <div className="card-actions"><button onClick={() => { setSelected(script); setFeedback(''); }} className="btn btn-sm btn-secondary">Revisar detalhes</button>{script.status === 'rascunho' && <><button onClick={() => approve(script)} className="btn btn-sm btn-success">Aprovar</button>{script.versao === latestVersionByIdea.get(script.ideia_id) && <button onClick={() => reject(script)} className="btn btn-sm btn-danger">Rejeitar</button>}</>}</div>
          </div>
        ))}
      </div>

      {showImportModal && (
        <div className="modal-overlay" onClick={() => { if (!importingScript) { setShowImportModal(false); resetImport(); } }}>
          <div className="modal modal-large" onClick={(event) => event.stopPropagation()}>
            <div className="modal-header">
              <h2>Importar roteiro</h2>
              <button
                className="btn-close"
                disabled={importingScript}
                onClick={() => { setShowImportModal(false); resetImport(); }}
              >×</button>
            </div>
            <p className="form-help">
              O arquivo entra como rascunho canônico. VisualQueries, aprovação e readiness continuam server-owned.
            </p>
            <div className="form-group">
              <label>Idea existente *</label>
              <select
                value={importIdeaId}
                onChange={(event) => {
                  setImportIdeaId(event.target.value);
                  setImportLocale(ideias.find(idea => idea.id === event.target.value)?.content_locale ?? 'pt-BR');
                  setImportPreview(null);
                  setImportError(null);
                }}
              >
                <option value="">Selecionar Idea...</option>
                {ideias.map((ideia) => (
                  <option key={ideia.id} value={ideia.id}>{ideia.titulo} ({ideia.status})</option>
                ))}
              </select>
            </div>
            <div className="form-group">
                <label>Idioma
                  <select value={importLocale} onChange={(e) => { setImportLocale(e.target.value as ContentLocale); setImportPreview(null); }}>
                    <option value="pt-BR">Português (Brasil)</option>
                    <option value="en-US">English (US)</option>
                  </select>
                </label>
              </div>
            <div className="form-group">
              <label>Arquivo neovids_manual_script_v1 *</label>
              <input
                type="file"
                accept="application/json,.json"
                onChange={(event) => void selectImportFile(event.target.files?.[0])}
              />
              <small>{importFile ? importFile.filename : 'Nenhum arquivo selecionado.'}</small>
            </div>
            {importError && <div className="error import-message">{importError}</div>}
            <div className="form-actions">
              <button
                type="button"
                className="btn btn-secondary"
                disabled={validatingImport || importingScript}
                onClick={() => { setShowImportModal(false); resetImport(); }}
              >Cancelar</button>
              <button
                type="button"
                className="btn btn-primary"
                disabled={validatingImport || importingScript || !importIdeaId || !importFile}
                onClick={() => void validateImport()}
              >{validatingImport ? 'Validando…' : 'Validar'}</button>
            </div>

            {importPreview && (
              <section className="manual-import-preview" aria-live="polite">
                <h3>Preview determinístico</h3>
                <dl className="preview-grid">
                  <div><dt>Schema</dt><dd>{importPreview.schema_version} · PASS</dd></div>
                  <div><dt>Idea</dt><dd>{importPreview.idea.title}</dd></div>
                  <div><dt>Production Profile</dt><dd>{importPreview.idea.production_profile}</dd></div>
                  <div><dt>Título</dt><dd>{importPreview.normalized.title}</dd></div>
                  <div><dt>Blocos</dt><dd>{importPreview.normalized.block_count}</dd></div>
                  <div><dt>Cenas</dt><dd>{importPreview.normalized.scene_count ?? 0}</dd></div>
                  <div><dt>Idioma</dt><dd>{importPreview.normalized.content_locale}</dd></div>
                  <div><dt>Palavras</dt><dd>{importPreview.normalized.word_count}</dd></div>
                  <div><dt>Duração editorial</dt><dd>{formatDuration(importPreview.normalized.duration_total_seconds)}</dd></div>
                  <div><dt>Target</dt><dd>{importPreview.idea.target_duration_seconds ? formatDuration(importPreview.idea.target_duration_seconds) : 'content-driven'}</dd></div>
                  <div><dt>Media scope</dt><dd>{importPreview.media_scope.scope.replace(/_/g, ' ')}</dd></div>
                  <div><dt>Visual Readiness</dt><dd>{importPreview.visual.status}</dd></div>
                  <div><dt>Approval</dt><dd>PENDING</dd></div>
                  <div><dt>Production Readiness</dt><dd>{importPreview.production_readiness.expected_status_after_import.toUpperCase()}</dd></div>
                </dl>
                <details>
                  <summary>Duração por bloco</summary>
                  <ul>{importPreview.normalized.blocks.map((block) => (
                    <li key={block.index}>{block.type}: {block.word_count} palavras · {formatDuration(block.duration_seconds)} · {block.duration_source}</li>
                  ))}</ul>
                </details>
                <p className="form-help">{importPreview.visual.message}</p>
                {importPreview.warnings.length > 0 && (
                  <div className="import-warnings"><strong>Warnings</strong><ul>{importPreview.warnings.map((warning) => <li key={warning}>{warning}</li>)}</ul></div>
                )}
                {importPreview.errors.length > 0 && (
                  <div className="error"><ul>{importPreview.errors.map((item) => <li key={item}>{item}</li>)}</ul></div>
                )}
                <div className="form-actions">
                  <button
                    type="button"
                    className="btn btn-success"
                    disabled={!importPreview.importable || importingScript || importPreview.errors.length > 0}
                    onClick={() => void persistImport()}
                  >{importingScript ? 'Importando…' : 'Importar'}</button>
                </div>
              </section>
            )}
          </div>
        </div>
      )}

      {showCreateModal && (
        <div className="modal-overlay" onClick={() => setShowCreateModal(false)}>
          <div className="modal modal-large" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h2>Criar Roteiro Manual</h2>
            </div>
            <form onSubmit={handleCreateManual}>
              <div className="form-group">
                <label>Ideia vinculada *</label>
                <select
                  value={createDraft.ideia_id}
                  onChange={(e) => setCreateDraft(d => ({ ...d, ideia_id: e.target.value, content_locale: ideias.find(idea => idea.id === e.target.value)?.content_locale ?? 'pt-BR' }))}
                  required
                >
                  <option value="">Selecionar ideia...</option>
                  {ideias.map(ideia => (
                    <option key={ideia.id} value={ideia.id}>
                      {ideia.titulo} ({ideia.status})
                    </option>
                  ))}
                </select>
                <small className="form-help">A ideia deve existir previamente. O roteiro será criado como rascunho versionado.</small>
              </div>

              <div className="form-group">
                <label>Idioma
                  <select value={createDraft.content_locale} onChange={(e) => setCreateDraft(d => ({ ...d, content_locale: e.target.value as ContentLocale }))}>
                    <option value="pt-BR">Português (Brasil)</option>
                    <option value="en-US">English (US)</option>
                  </select>
                </label>
              </div>
              <div className="form-group">
                <label>Título do roteiro *</label>
                <input
                  type="text"
                  value={createDraft.titulo}
                  onChange={(e) => setCreateDraft(d => ({ ...d, titulo: e.target.value }))}
                  required
                  maxLength={300}
                  placeholder="Título do roteiro..."
                />
              </div>

              <div className="form-group">
                <label>Blocos (narrativa) *</label>
                <small className="form-help">A prosa é preservada exatamente como escrita. Duração total: {createDraft.blocos.reduce((s, b) => s + b.duracao_segundos, 0)}s ({Math.round(createDraft.blocos.reduce((s, b) => s + b.duracao_segundos, 0) / 60)} min).</small>
                {createDraft.blocos.map((bloco, i) => (
                  <div key={i} className="block-edit" style={{ border: '1px solid #333', borderRadius: '6px', padding: '12px', marginBottom: '12px' }}>
                    <div style={{ display: 'flex', gap: '8px', marginBottom: '8px' }}>
                      <select
                        value={bloco.tipo}
                        onChange={(e) => updateCreateBlock(i, 'tipo', e.target.value)}
                      >
                        <option value="introducao">Introdução</option>
                        <option value="desenvolvimento">Desenvolvimento</option>
                        <option value="conclusao">Conclusão</option>
                        <option value="gancho">Gancho</option>
                        <option value="cta">Call to Action</option>
                      </select>
                      <input
                        type="number"
                        value={bloco.duracao_segundos}
                        onChange={(e) => updateCreateBlock(i, 'duracao_segundos', Number(e.target.value))}
                        min={1}
                        max={7200}
                        style={{ width: '100px' }}
                      />
                      <span>s</span>
                      {createDraft.blocos.length > 1 && (
                        <button type="button" className="btn btn-sm btn-danger" onClick={() => removeBlock(i)}>Remover</button>
                      )}
                    </div>
                    <textarea
                      value={bloco.conteudo}
                      onChange={(e) => updateCreateBlock(i, 'conteudo', e.target.value)}
                      rows={4}
                      placeholder="Conteúdo narrativo (prosa preservada)..."
                      required
                      maxLength={100000}
                      style={{ width: '100%' }}
                    />
                    <div style={{ display: 'flex', gap: '8px', marginTop: '8px' }}>
                      <input
                        type="text"
                        value={bloco.dicas_visual}
                        onChange={(e) => updateCreateBlock(i, 'dicas_visual', e.target.value)}
                        placeholder="Dicas visuais (opcional)"
                        style={{ flex: 1 }}
                      />
                      <input
                        type="text"
                        value={bloco.dicas_audio}
                        onChange={(e) => updateCreateBlock(i, 'dicas_audio', e.target.value)}
                        placeholder="Dicas de áudio (opcional)"
                        style={{ flex: 1 }}
                      />
                    </div>
                  </div>
                ))}
                <button type="button" className="btn btn-sm btn-secondary" onClick={addBlock}>+ Adicionar bloco</button>
              </div>

              <div className="form-group">
                <label>Tags (separadas por vírgula)</label>
                <input
                  type="text"
                  value={createDraft.tags.join(', ')}
                  onChange={(e) => setCreateDraft(d => ({ ...d, tags: e.target.value.split(',').map(t => t.trim()).filter(Boolean) }))}
                  placeholder="tag1, tag2, tag3"
                />
              </div>

              <div className="form-group">
                <label>Referências</label>
                <input
                  type="text"
                  value={createDraft.referencias}
                  onChange={(e) => setCreateDraft(d => ({ ...d, referencias: e.target.value }))}
                  placeholder="URL ou referência (opcional)"
                />
              </div>

              <div className="modal-footer">
                <button type="button" className="btn btn-secondary" onClick={() => setShowCreateModal(false)}>Cancelar</button>
                <button type="submit" className="btn btn-primary" disabled={creating}>
                  {creating ? 'Criando...' : 'Criar rascunho'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
