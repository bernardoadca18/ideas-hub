import { useState, useEffect } from 'react';
import { api, Trend, Nicho } from '../api/client';

export default function Trends() {
  const [trends, setTrends] = useState<Trend[]>([]);
  const [nichos, setNichos] = useState<Nicho[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Filter state
  const [statusFilter, setStatusFilter] = useState<string>('pendente');
  const [nichoFilter, setNichoFilter] = useState<string>('');

  // Batch actions
  const [selectedTrends, setSelectedTrends] = useState<Set<string>>(new Set());
  const [processing, setProcessing] = useState(false);

  // Generate ideas modal
  const [showGenerateModal, setShowGenerateModal] = useState(false);
  const [selectedTrendForIdeas, setSelectedTrendForIdeas] = useState<Trend | null>(null);
  const [numIdeias, setNumIdeias] = useState(3);
  const [generating, setGenerating] = useState(false);

  useEffect(() => {
    loadData();
  }, [statusFilter, nichoFilter]);

  async function loadData() {
    try {
      setLoading(true);
      const [trendsData, nichosData] = await Promise.all([
        api.getTrends(
          statusFilter || nichoFilter
            ? { status: statusFilter || undefined, nicho_id: nichoFilter || undefined }
            : undefined
        ),
        api.getNichos(),
      ]);
      setTrends(trendsData);
      setNichos(nichosData);
      setSelectedTrends(new Set());
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Erro ao carregar dados');
    } finally {
      setLoading(false);
    }
  }

  function toggleSelect(id: string) {
    const newSelected = new Set(selectedTrends);
    if (newSelected.has(id)) {
      newSelected.delete(id);
    } else {
      newSelected.add(id);
    }
    setSelectedTrends(newSelected);
  }

  function selectAll() {
    if (selectedTrends.size === trends.length) {
      setSelectedTrends(new Set());
    } else {
      setSelectedTrends(new Set(trends.map(t => t.id)));
    }
  }

  async function handleBatchApprove() {
    if (selectedTrends.size === 0) return;

    try {
      setProcessing(true);
      const promises = Array.from(selectedTrends).map(id => api.aprovarTrend(id));
      await Promise.all(promises);
      setSelectedTrends(new Set());
      loadData();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Erro ao aprovar trends');
    } finally {
      setProcessing(false);
    }
  }

  async function handleBatchReject() {
    if (selectedTrends.size === 0) return;

    try {
      setProcessing(true);
      const promises = Array.from(selectedTrends).map(id => api.rejeitarTrend(id));
      await Promise.all(promises);
      setSelectedTrends(new Set());
      loadData();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Erro ao rejeitar trends');
    } finally {
      setProcessing(false);
    }
  }

  async function handleAprovar(id: string) {
    try {
      await api.aprovarTrend(id);
      loadData();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Erro ao aprovar trend');
    }
  }

  async function handleRejeitar(id: string) {
    try {
      await api.rejeitarTrend(id);
      loadData();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Erro ao rejeitar trend');
    }
  }

  function openGenerateModal(trend: Trend) {
    setSelectedTrendForIdeas(trend);
    setNumIdeias(3);
    setShowGenerateModal(true);
  }

  async function handleGenerateIdeas(e: React.FormEvent) {
    e.preventDefault();
    if (!selectedTrendForIdeas) return;

    try {
      setGenerating(true);
      const result = await api.gerarIdeiasFromTrend(selectedTrendForIdeas.id, numIdeias);
      alert(`Geradas ${result.ideias_geradas} ideias!`);
      setShowGenerateModal(false);
      setSelectedTrendForIdeas(null);
      loadData();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Erro ao gerar ideias');
    } finally {
      setGenerating(false);
    }
  }

  function getStatusColor(status: string) {
    switch (status) {
      case 'pendente': return '#f59e0b';
      case 'aprovada': return '#10b981';
      case 'rejeitada': return '#ef4444';
      default: return '#9ca3af';
    }
  }

  if (loading) return <div className="loading">Carregando...</div>;
  if (error) return <div className="error">{error}</div>;

  return (
    <div className="page">
      <div className="page-header">
        <h1>Trends</h1>
      </div>

      <div className="filters">
        <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}>
          <option value="">Todos os status</option>
          <option value="pendente">Pendente</option>
          <option value="aprovada">Aprovada</option>
          <option value="rejeitada">Rejeitada</option>
        </select>
        <select value={nichoFilter} onChange={(e) => setNichoFilter(e.target.value)}>
          <option value="">Todos os nichos</option>
          {nichos.map((nicho) => (
            <option key={nicho.id} value={nicho.id}>
              {nicho.nome}
            </option>
          ))}
        </select>
      </div>

      {selectedTrends.size > 0 && (
        <div className="batch-actions">
          <span>{selectedTrends.size} selecionados</span>
          <button
            onClick={handleBatchApprove}
            className="btn btn-sm btn-success"
            disabled={processing}
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M5 13l4 4L19 7"></path>
            </svg>
            Aprovar Selecionados
          </button>
          <button
            onClick={handleBatchReject}
            className="btn btn-sm btn-danger"
            disabled={processing}
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M6 18L18 6M6 6l12 12"></path>
            </svg>
            Rejeitar Selecionados
          </button>
        </div>
      )}

      {showGenerateModal && selectedTrendForIdeas && (
        <div className="modal-overlay" onClick={() => setShowGenerateModal(false)}>
          <div className="modal" onClick={(e) => e.stopPropagation()}>
            <h2>Gerar Ideias</h2>
            <p>Trend: <strong>{selectedTrendForIdeas.termo_bruto}</strong></p>
            <form onSubmit={handleGenerateIdeas}>
              <div className="form-group">
                <label>Número de Ideias</label>
                <input
                  type="number"
                  value={numIdeias}
                  onChange={(e) => setNumIdeias(parseInt(e.target.value) || 3)}
                  min={1}
                  max={10}
                />
              </div>
              <div className="form-actions">
                <button type="button" onClick={() => setShowGenerateModal(false)} className="btn btn-secondary">
                  Cancelar
                </button>
                <button type="submit" className="btn btn-primary" disabled={generating}>
                  {generating ? 'Gerando...' : 'Gerar'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      <div className="list">
        {trends.length === 0 ? (
          <div className="empty-state">Nenhuma trend encontrada</div>
        ) : (
          <>
            <div className="list-header">
              <input
                type="checkbox"
                checked={selectedTrends.size === trends.length && trends.length > 0}
                onChange={selectAll}
              />
              <span>Selecionar todos</span>
            </div>
            {trends.map((trend) => (
              <div key={trend.id} className="card">
                <div className="card-row">
                  <input
                    type="checkbox"
                    checked={selectedTrends.has(trend.id)}
                    onChange={() => toggleSelect(trend.id)}
                  />
                  <div className="card-content">
                    <div className="card-header">
                      <h3 className="card-title">{trend.termo_bruto}</h3>
                      <span
                        className="status-badge"
                        style={{ backgroundColor: getStatusColor(trend.status) }}
                      >
                        {trend.status}
                      </span>
                    </div>
                    <div className="card-meta">
                      <span>Fonte: {trend.fonte}</span>
                      {trend.payload_raw?.title && (
                        <span>Título: {String(trend.payload_raw.title)}</span>
                      )}
                      <span>Criado: {new Date(trend.criado_em).toLocaleDateString()}</span>
                    </div>
                  </div>
                </div>
                <div className="card-actions">
                  {trend.status === 'pendente' && (
                    <>
                      <button onClick={() => handleAprovar(trend.id)} className="btn btn-sm btn-success">
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                          <path d="M5 13l4 4L19 7"></path>
                        </svg>
                        Aprovar
                      </button>
                      <button onClick={() => handleRejeitar(trend.id)} className="btn btn-sm btn-danger">
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                          <path d="M6 18L18 6M6 6l12 12"></path>
                        </svg>
                        Rejeitar
                      </button>
                    </>
                  )}
                  {trend.status === 'aprovada' && (
                    <button onClick={() => openGenerateModal(trend)} className="btn btn-sm btn-primary">
                      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                        <path d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z"></path>
                      </svg>
                      Gerar Ideias
                    </button>
                  )}
                </div>
              </div>
            ))}
          </>
        )}
      </div>
    </div>
  );
}
