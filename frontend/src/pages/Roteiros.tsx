import { useEffect, useState } from 'react';
import { api, Roteiro, ScriptEditRevision } from '../api/client';

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

export default function Roteiros() {
  const [roteiros, setRoteiros] = useState<Roteiro[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [statusFilter, setStatusFilter] = useState('');
  const [selected, setSelected] = useState<Roteiro | null>(null);
  const [editDraft, setEditDraft] = useState<ScriptEditRevision | null>(null);
  const [feedback, setFeedback] = useState('');
  const [regenerating, setRegenerating] = useState(false);

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

  async function approve(script: Roteiro) {
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
    if (!selected || !feedback.trim()) return;
    setRegenerating(true);
    try {
      const created = await api.regenerarRoteiroComFeedback(selected.id, feedback);
      setSelected(created);
      setFeedback('');
      await loadData();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Erro ao regenerar roteiro');
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

  return (
    <div className="page">
      <div className="page-header"><h1>Roteiros</h1></div>
      {error && <div className="error">{error} <button onClick={() => setError(null)}>Fechar</button></div>}
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
                  <span>{formatDuration(selected.estrutura.duracao_total_segundos)}</span>
                  <span>{selected.estrutura.blocos.length} blocos</span>
                  <span>Origem: {selected.revision_kind}</span>
                </div>
                <div className="script-provenance">
                  <strong>Contexto do autor usado nesta versão</strong>
                  <p>{selected.author_briefing_snapshot || 'Nenhum contexto fornecido.'}</p>
                  <code>{selected.author_briefing_identity || 'snapshot histórico indisponível'}</code>
                  {selected.author_briefing_changed_since_creation === true && <span className="context-changed">O contexto atual da ideia mudou desde esta versão.</span>}
                </div>
                <div className="blocos-list">
                  {selected.estrutura.blocos.map((block, index) => (
                    <div key={index} className="bloco-card">
                      <div className="bloco-header"><h4>{block.tipo}</h4><span>{formatDuration(block.duracao_segundos)}</span></div>
                      <div className="bloco-conteudo"><p>{block.conteudo}</p></div>
                      {block.dicas_visual && <div className="bloco-dica"><strong>Visual:</strong> {block.dicas_visual}</div>}
                      {block.dicas_audio && <div className="bloco-dica"><strong>Áudio:</strong> {block.dicas_audio}</div>}
                      {(block.visual_queries?.length || 0) > 0 && <div className="bloco-dica"><strong>VisualQueries:</strong> {block.visual_queries?.length} preservadas com provenance.</div>}
                    </div>
                  ))}
                </div>
                <div className="revision-actions">
                  <button className="btn btn-secondary" onClick={() => beginEdit(selected)}>Editar como nova versão</button>
                  <form onSubmit={regenerate} className="feedback-form">
                    <label htmlFor="revision-feedback"><strong>Regenerar com feedback</strong></label>
                    <textarea id="revision-feedback" rows={3} value={feedback} onChange={(e) => setFeedback(e.target.value)} placeholder="Ex.: A introdução está longa; mantenha o trecho sobre Z e não afirme Y." />
                    <button className="btn btn-primary" disabled={regenerating || !feedback.trim()} type="submit">{regenerating ? 'Regenerando…' : 'Criar nova versão'}</button>
                  </form>
                </div>
                {selected.status === 'rascunho' && <div className="modal-footer">{selectedIsLatest ? <><button onClick={() => reject(selected)} className="btn btn-danger">Rejeitar</button><button onClick={() => approve(selected)} className="btn btn-success">Aprovar versão</button></> : <span className="form-help">Somente o draft mais recente pode ser aprovado ou rejeitado.</span>}</div>}
              </>
            )}
          </div>
        </div>
      )}

      <div className="list">
        {roteiros.length === 0 ? <div className="empty-state">Nenhum roteiro encontrado</div> : roteiros.map((script) => (
          <div key={script.id} className="card">
            <div className="card-header"><h3 className="card-title">{script.estrutura.titulo}</h3><span className="status-badge" style={{ backgroundColor: statusColor(script.status) }}>{script.status}</span></div>
            <div className="card-meta"><span>Versão: {script.versao}</span><span>Origem: {script.revision_kind}</span><span>Duração: {formatDuration(script.estrutura.duracao_total_segundos)}</span><span>Ideia: {script.ideia_id.slice(0, 8)}…</span></div>
            <div className="card-actions"><button onClick={() => { setSelected(script); setFeedback(''); }} className="btn btn-sm btn-secondary">Revisar detalhes</button>{script.status === 'rascunho' && script.versao === latestVersionByIdea.get(script.ideia_id) && <><button onClick={() => approve(script)} className="btn btn-sm btn-success">Aprovar</button><button onClick={() => reject(script)} className="btn btn-sm btn-danger">Rejeitar</button></>}</div>
          </div>
        ))}
      </div>
    </div>
  );
}
