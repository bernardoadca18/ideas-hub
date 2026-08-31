import { useEffect, useRef, useState } from 'react';
import { api, DurationMode, GenerationPreview, GenerationRun, Ideia, Nicho, ProductionProfile } from '../api/client';

export default function Ideias() {
  const [ideias, setIdeias] = useState<Ideia[]>([]);
  const [nichos, setNichos] = useState<Nicho[]>([]);
  const [profiles, setProfiles] = useState<ProductionProfile[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Form state
  const [showForm, setShowForm] = useState(false);
  const [titulo, setTitulo] = useState('');
  const [descricao, setDescricao] = useState('');
  const [authorBriefing, setAuthorBriefing] = useState('');
  const [targetMinutes, setTargetMinutes] = useState('');
  const [durationMode, setDurationMode] = useState<DurationMode>('profile_default');
  const [nichoId, setNichoId] = useState('');
  const [editingBriefing, setEditingBriefing] = useState<Ideia | null>(null);
  const [briefingDraft, setBriefingDraft] = useState('');
  const [generationRuns, setGenerationRuns] = useState<Record<string, GenerationRun>>({});
  const [generationPreview, setGenerationPreview] = useState<GenerationPreview | null>(null);
  const pollControllers = useRef(new Map<string, AbortController>());

  // Filter state
  const [statusFilter, setStatusFilter] = useState<string>('');

  // Collect trends modal
  const [showTrendsModal, setShowTrendsModal] = useState(false);
  const [selectedNichoForTrends, setSelectedNichoForTrends] = useState('');
  const [termosAdicionais, setTermosAdicionais] = useState('');
  const [collecting, setCollecting] = useState(false);

  useEffect(() => {
    loadData();
  }, [statusFilter]);

  useEffect(() => () => {
    pollControllers.current.forEach((controller) => controller.abort());
  }, []);

  async function loadData() {
    try {
      setLoading(true);
      const [ideiasData, nichosData, profilesData, recentRuns] = await Promise.all([
        api.getIdeias(statusFilter ? { status: statusFilter } : undefined),
        api.getNichos(),
        api.getProductionProfiles(),
        api.getGenerationRuns(),
      ]);
      setIdeias(ideiasData);
      setNichos(nichosData);
      setProfiles(profilesData);
      const latestByIdea: Record<string, GenerationRun> = {};
      recentRuns.forEach((run) => {
        if (!latestByIdea[run.ideia_id]) latestByIdea[run.ideia_id] = run;
      });
      setGenerationRuns(latestByIdea);
      Object.values(latestByIdea).forEach((run) => {
        if (!['completed', 'failed', 'cancelled'].includes(run.status) && !pollControllers.current.has(run.id)) {
          void pollGeneration(run.ideia_id, run.id);
        }
      });
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Erro ao carregar dados');
    } finally {
      setLoading(false);
    }
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    try {
      await api.createIdeia({
        titulo,
        descricao: descricao || undefined,
        author_briefing: authorBriefing || undefined,
        duration_mode: durationMode,
        target_duration_seconds: durationMode === 'explicit_target' ? Math.round(Number(targetMinutes) * 60) : undefined,
        nicho_id: nichoId || undefined,
      });
      setTitulo('');
      setDescricao('');
      setAuthorBriefing('');
      setTargetMinutes('');
      setDurationMode('profile_default');
      setNichoId('');
      setShowForm(false);
      loadData();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Erro ao criar ideia');
    }
  }

  async function previewPlan() {
    if (!selectedProfile) return;
    try {
      setGenerationPreview(await api.getGenerationPreview({
        production_profile: selectedProfile.id,
        duration_mode: durationMode,
        target_duration_seconds: durationMode === 'explicit_target' ? Math.round(Number(targetMinutes) * 60) : undefined,
        evidence_chars: descricao.length + authorBriefing.length,
      }));
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Não foi possível calcular o plano editorial');
    }
  }

  async function handleSaveBriefing(e: React.FormEvent) {
    e.preventDefault();
    if (!editingBriefing) return;
    try {
      await api.updateIdeia(editingBriefing.id, {
        author_briefing: briefingDraft === '' ? null : briefingDraft,
      });
      setEditingBriefing(null);
      setBriefingDraft('');
      await loadData();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Erro ao salvar contexto do autor');
    }
  }

  async function handleAprovar(id: string) {
    try {
      await api.aprovarIdeia(id);
      loadData();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Erro ao aprovar ideia');
    }
  }

  async function handleRejeitar(id: string) {
    try {
      await api.rejeitarIdeia(id);
      loadData();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Erro ao rejeitar ideia');
    }
  }

  async function handleGerarRoteiro(id: string) {
    try {
      const run = await api.startGenerationRun(id, crypto.randomUUID());
      setGenerationRuns((current) => ({ ...current, [id]: run }));
      void pollGeneration(id, run.id);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Erro ao gerar roteiro');
    }
  }

  async function pollGeneration(ideaId: string, runId: string) {
    const previous = pollControllers.current.get(runId);
    previous?.abort();
    const controller = new AbortController();
    pollControllers.current.set(runId, controller);
    let delayMs = 1500;
    while (!controller.signal.aborted) {
      try {
        const run = await api.getGenerationRun(runId, controller.signal);
        setGenerationRuns((current) => ({ ...current, [ideaId]: run }));
        if (['completed', 'failed', 'cancelled'].includes(run.status)) {
          pollControllers.current.delete(runId);
          await loadData();
          return;
        }
        delayMs = 1500;
      } catch (err) {
        if (controller.signal.aborted) return;
        delayMs = Math.min(delayMs * 2, 10000);
        setError(err instanceof Error ? err.message : 'Falha ao consultar progresso da geração');
      }
      await new Promise((resolve) => window.setTimeout(resolve, delayMs));
    }
  }

  const selectedNiche = nichos.find((item) => item.id === nichoId);
  const selectedProfile = profiles.find((item) => item.id === (selectedNiche?.perfil_producao || 'faceless_general'));

  async function handleColetarTrends(e: React.FormEvent) {
    e.preventDefault();
    if (!selectedNichoForTrends) return;

    try {
      setCollecting(true);
      const termos = termosAdicionais ? termosAdicionais.split(',').map(t => t.trim()).filter(Boolean) : undefined;
      const result = await api.coletarTrends(selectedNichoForTrends, termos);
      alert(`Coletadas ${result.total_coletado} trends!`);
      setShowTrendsModal(false);
      setSelectedNichoForTrends('');
      setTermosAdicionais('');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Erro ao coletar trends');
    } finally {
      setCollecting(false);
    }
  }

  function getStatusColor(status: string) {
    switch (status) {
      case 'rascunho': return '#9ca3af';
      case 'aprovada': return '#10b981';
      case 'rejeitada': return '#ef4444';
      case 'em_roteiro': return '#f59e0b';
      case 'roteirizada': return '#3b82f6';
      default: return '#9ca3af';
    }
  }

  if (loading) return <div className="loading">Carregando...</div>;
  if (error) return <div className="error">{error}</div>;

  return (
    <div className="page">
      <div className="page-header">
        <h1>Ideias</h1>
        <div className="actions">
          <button onClick={() => setShowTrendsModal(true)} className="btn btn-secondary">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"></path>
            </svg>
            Buscar Trends
          </button>
          <button onClick={() => setShowForm(true)} className="btn btn-primary">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M12 5v14M5 12h14"></path>
            </svg>
            Nova Ideia
          </button>
        </div>
      </div>

      <div className="filters">
        <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}>
          <option value="">Todos os status</option>
          <option value="rascunho">Rascunho</option>
          <option value="aprovada">Aprovada</option>
          <option value="rejeitada">Rejeitada</option>
          <option value="em_roteiro">Em Roteiro</option>
          <option value="roteirizada">Roteirizada</option>
        </select>
      </div>

      {showForm && (
        <div className="modal-overlay" onClick={() => setShowForm(false)}>
          <div className="modal" onClick={(e) => e.stopPropagation()}>
            <h2>Nova Ideia</h2>
            <form onSubmit={handleSubmit}>
              <div className="form-group">
                <label>Título *</label>
                <input
                  type="text"
                  value={titulo}
                  onChange={(e) => setTitulo(e.target.value)}
                  required
                  maxLength={300}
                />
              </div>
              <div className="form-group">
                <label>Descrição da ideia</label>
                <textarea
                  value={descricao}
                  onChange={(e) => setDescricao(e.target.value)}
                  rows={3}
                />
              </div>
              <details className="advanced-field">
                <summary>Planejamento editorial avançado (opcional)</summary>
                <div className="form-group">
                  <label>Contexto do autor</label>
                  <textarea
                    value={authorBriefing}
                    onChange={(e) => setAuthorBriefing(e.target.value)}
                    rows={6}
                    placeholder="Sua tese, opinião, restrições editoriais e pontos que o roteirista não deve esquecer."
                  />
                  <small>Este texto não é a descrição e não será reescrito pelo Curador.</small>
                </div>
                <div className="form-group">
                  <label>Modo de duração</label>
                  <select value={durationMode} onChange={(e) => setDurationMode(e.target.value as DurationMode)}>
                    <option value="profile_default">Padrão do perfil{selectedProfile?.duration_policy.default_target_seconds ? ` (${selectedProfile.duration_policy.default_target_seconds / 60} min)` : ''}</option>
                    <option value="explicit_target">Duração escolhida</option>
                    {selectedProfile?.duration_policy.content_driven_allowed && <option value="content_driven">Content-driven (sem target fixo)</option>}
                  </select>
                  <small>Content-driven é uma escolha explícita; ausência de target não o ativa silenciosamente.</small>
                </div>
                {durationMode === 'explicit_target' && <div className="form-group">
                  <label>Duração editorial alvo (minutos)</label>
                  <input type="number" min="1" max="480" step="1" list="duration-presets" value={targetMinutes} onChange={(e) => setTargetMinutes(e.target.value)} required />
                  <datalist id="duration-presets">{[5, 8, 10, 12, 15, 20, 30, 45, 60, 90, 120, 180].map((minutes) => <option key={minutes} value={minutes} />)}</datalist>
                  <small>Contrato de conteúdo; nunca altera velocidade, pausas ou TTS.</small>
                </div>}
                <button type="button" className="btn btn-secondary" onClick={() => void previewPlan()} disabled={durationMode === 'explicit_target' && !targetMinutes}>
                  Pré-visualizar plano
                </button>
                {generationPreview && <div className="script-provenance">
                  <strong>Estratégia: {generationPreview.strategy}</strong>
                  <p>{generationPreview.target_words ?? 'sem budget fixo'} palavras · {generationPreview.chapter_count} capítulos · {generationPreview.section_count} seções · ~{generationPreview.estimated_llm_calls} chamadas</p>
                  {generationPreview.content_capacity.status === 'probably_insufficient' && <p className="context-changed">Evidência atual provavelmente insuficiente para sustentar o target sem filler. Amplie a pesquisa/contexto antes da geração.</p>}
                  <small>Estimativa determinística; nenhuma chamada editorial ao LLM foi feita.</small>
                </div>}
              </details>
              <div className="form-group">
                <label>Nicho</label>
                <select value={nichoId} onChange={(e) => {
                  const nextNicheId = e.target.value;
                  const nextNiche = nichos.find((item) => item.id === nextNicheId);
                  const nextProfile = profiles.find((item) => item.id === (nextNiche?.perfil_producao || 'faceless_general'));
                  setNichoId(nextNicheId);
                  setDurationMode(nextProfile?.duration_policy.default_target_seconds ? 'profile_default' : 'content_driven');
                  setTargetMinutes('');
                }}>
                  <option value="">Selecione um nicho</option>
                  {nichos.map((nicho) => (
                    <option key={nicho.id} value={nicho.id}>
                      {nicho.nome}
                    </option>
                  ))}
                </select>
              </div>
              <div className="form-actions">
                <button type="button" onClick={() => setShowForm(false)} className="btn btn-secondary">
                  Cancelar
                </button>
                <button type="submit" className="btn btn-primary">
                  Criar
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {editingBriefing && (
        <div className="modal-overlay" onClick={() => setEditingBriefing(null)}>
          <div className="modal modal-large" onClick={(e) => e.stopPropagation()}>
            <h2>Editar contexto do autor</h2>
            <p className="form-help">
              Intenção e posição editorial para o roteirista. Não use este campo como descrição
              factual; roteiros já gerados mantêm o snapshot anterior.
            </p>
            <form onSubmit={handleSaveBriefing}>
              <div className="form-group">
                <label>Contexto do autor para “{editingBriefing.titulo}”</label>
                <textarea
                  value={briefingDraft}
                  onChange={(e) => setBriefingDraft(e.target.value)}
                  rows={10}
                />
              </div>
              <div className="form-actions">
                <button type="button" className="btn btn-secondary" onClick={() => setEditingBriefing(null)}>Cancelar</button>
                <button type="submit" className="btn btn-primary">Salvar contexto</button>
              </div>
            </form>
          </div>
        </div>
      )}

      {showTrendsModal && (
        <div className="modal-overlay" onClick={() => setShowTrendsModal(false)}>
          <div className="modal" onClick={(e) => e.stopPropagation()}>
            <h2>Coletar Trends</h2>
            <form onSubmit={handleColetarTrends}>
              <div className="form-group">
                <label>Nicho *</label>
                <select
                  value={selectedNichoForTrends}
                  onChange={(e) => setSelectedNichoForTrends(e.target.value)}
                  required
                >
                  <option value="">Selecione um nicho</option>
                  {nichos.map((nicho) => (
                    <option key={nicho.id} value={nicho.id}>
                      {nicho.nome}
                    </option>
                  ))}
                </select>
              </div>
              <div className="form-group">
                <label>Termos Adicionais (separados por vírgula)</label>
                <input
                  type="text"
                  value={termosAdicionais}
                  onChange={(e) => setTermosAdicionais(e.target.value)}
                  placeholder="ex: inteligência artificial, tecnologia"
                />
              </div>
              <div className="form-actions">
                <button type="button" onClick={() => setShowTrendsModal(false)} className="btn btn-secondary">
                  Cancelar
                </button>
                <button type="submit" className="btn btn-primary" disabled={collecting}>
                  {collecting ? 'Coletando...' : 'Coletar'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      <div className="list">
        {ideias.length === 0 ? (
          <div className="empty-state">Nenhuma ideia encontrada</div>
        ) : (
          ideias.map((ideia) => (
            <div key={ideia.id} className="card">
              <div className="card-header">
                <h3 className="card-title">{ideia.titulo}</h3>
                <span
                  className="status-badge"
                  style={{ backgroundColor: getStatusColor(ideia.status) }}
                >
                  {ideia.status}
                </span>
              </div>
              {ideia.descricao_breve && (
                <div className="idea-description"><strong>Descrição</strong><p className="card-description">{ideia.descricao_breve}</p></div>
              )}
              {ideia.author_briefing && (
                <div className="author-briefing-panel">
                  <strong>Contexto do autor</strong>
                  <p>{ideia.author_briefing}</p>
                </div>
              )}
              <div className="card-meta">
                <span>Origem: {ideia.origem}</span>
                <span>Duração: {ideia.duration_mode === 'content_driven' ? 'content-driven' : ideia.target_duration_seconds ? `${Math.round(ideia.target_duration_seconds / 60)} min` : 'histórico não resolvido'}</span>
                {ideia.duration_target_source && <span>Fonte: {ideia.duration_target_source}</span>}
                <span>Criado: {new Date(ideia.criado_em).toLocaleDateString()}</span>
              </div>
              {generationRuns[ideia.id] && <div className="script-provenance">
                <strong>Geração: {generationRuns[ideia.id].phase}</strong>
                <p>{generationRuns[ideia.id].completed_sections} / {generationRuns[ideia.id].total_sections} seções · estratégia {generationRuns[ideia.id].generation_strategy}</p>
                {generationRuns[ideia.id].error_message && <span className="context-changed">{generationRuns[ideia.id].error_message}</span>}
              </div>}
              <div className="card-actions">
                <button
                  onClick={() => { setEditingBriefing(ideia); setBriefingDraft(ideia.author_briefing || ''); }}
                  className="btn btn-sm btn-secondary"
                >
                  Editar contexto do autor
                </button>
                {ideia.status === 'rascunho' && (
                  <>
                    <button onClick={() => handleAprovar(ideia.id)} className="btn btn-sm btn-success">
                      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                        <path d="M5 13l4 4L19 7"></path>
                      </svg>
                      Aprovar
                    </button>
                    <button onClick={() => handleRejeitar(ideia.id)} className="btn btn-sm btn-danger">
                      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                        <path d="M6 18L18 6M6 6l12 12"></path>
                      </svg>
                      Rejeitar
                    </button>
                  </>
                )}
                {ideia.status === 'aprovada' && (
                  <button disabled={Boolean(generationRuns[ideia.id] && !['completed', 'failed', 'cancelled'].includes(generationRuns[ideia.id].status))} onClick={() => handleGerarRoteiro(ideia.id)} className="btn btn-sm btn-primary">
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                      <path d="M12 19l7-7 3 3-7 7-3-3z"></path>
                      <path d="M18 13l-1.5-7.5L2 2l3.5 14.5L13 18l5-5z"></path>
                      <path d="M2 2l7.586 7.586"></path>
                      <circle cx="11" cy="11" r="2"></circle>
                    </svg>
                    Gerar Roteiro
                  </button>
                )}
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
}
