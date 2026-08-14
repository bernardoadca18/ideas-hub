import { useState, useEffect } from 'react';
import { api, Roteiro } from '../api/client';

export default function Roteiros() {
  const [roteiros, setRoteiros] = useState<Roteiro[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Filter state
  const [statusFilter, setStatusFilter] = useState<string>('');

  // Selected roteiro for detail view
  const [selectedRoteiro, setSelectedRoteiro] = useState<Roteiro | null>(null);

  useEffect(() => {
    loadData();
  }, [statusFilter]);

  async function loadData() {
    try {
      setLoading(true);
      const roteirosData = await api.getRoteiros(statusFilter ? { status: statusFilter } : undefined);
      setRoteiros(roteirosData);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Erro ao carregar dados');
    } finally {
      setLoading(false);
    }
  }

  async function handleAprovar(id: string) {
    try {
      await api.aprovarRoteiro(id);
      alert('Roteiro aprovado!');
      loadData();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Erro ao aprovar roteiro');
    }
  }

  async function handleRejeitar(id: string) {
    try {
      await api.rejeitarRoteiro(id);
      alert('Roteiro rejeitado. A ideia voltou para status aprovada.');
      loadData();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Erro ao rejeitar roteiro');
    }
  }

  function getStatusColor(status: string) {
    switch (status) {
      case 'rascunho': return '#9ca3af';
      case 'aprovado': return '#10b981';
      case 'rejeitado': return '#ef4444';
      default: return '#9ca3af';
    }
  }

  function formatDuration(seconds: number) {
    const minutes = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${minutes}:${secs.toString().padStart(2, '0')}`;
  }

  if (loading) return <div className="loading">Carregando...</div>;
  if (error) return <div className="error">{error}</div>;

  return (
    <div className="page">
      <div className="page-header">
        <h1>Roteiros</h1>
      </div>

      <div className="filters">
        <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}>
          <option value="">Todos os status</option>
          <option value="rascunho">Rascunho</option>
          <option value="aprovado">Aprovado</option>
          <option value="rejeitado">Rejeitado</option>
        </select>
      </div>

      {selectedRoteiro && (
        <div className="modal-overlay" onClick={() => setSelectedRoteiro(null)}>
          <div className="modal modal-large" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h2>{selectedRoteiro.estrutura.titulo}</h2>
              <button onClick={() => setSelectedRoteiro(null)} className="btn-close">×</button>
            </div>
            <div className="modal-body">
              <div className="roteiro-info">
                <span className="status-badge" style={{ backgroundColor: getStatusColor(selectedRoteiro.status) }}>
                  {selectedRoteiro.status}
                </span>
                <span>Versão: {selectedRoteiro.versao}</span>
                <span>Duração: {formatDuration(selectedRoteiro.estrutura.duracao_total_segundos)}</span>
                <span>Blocos: {selectedRoteiro.estrutura.blocos.length}</span>
              </div>

              <div className="blocos-list">
                {selectedRoteiro.estrutura.blocos.map((bloco, index) => (
                  <div key={index} className="bloco-card">
                    <div className="bloco-header">
                      <h4>{bloco.tipo}</h4>
                      <span>{formatDuration(bloco.duracao_segundos)}</span>
                    </div>
                    <div className="bloco-conteudo">
                      <p>{bloco.conteudo}</p>
                    </div>
                    {bloco.dicas_visual && (
                      <div className="bloco-dica">
                        <strong>Visual:</strong> {bloco.dicas_visual}
                      </div>
                    )}
                    {bloco.dicas_audio && (
                      <div className="bloco-dica">
                        <strong>Áudio:</strong> {bloco.dicas_audio}
                      </div>
                    )}
                  </div>
                ))}
              </div>

              {selectedRoteiro.estrutura.tags.length > 0 && (
                <div className="roteiro-tags">
                  <strong>Tags:</strong>
                  {selectedRoteiro.estrutura.tags.map((tag, i) => (
                    <span key={i} className="tag">{tag}</span>
                  ))}
                </div>
              )}

              {selectedRoteiro.estrutura.referencias && selectedRoteiro.estrutura.referencias.length > 0 && (
                <div className="roteiro-referencias">
                  <strong>Referências:</strong>
                  <ul>
                    {selectedRoteiro.estrutura.referencias.map((ref, i) => (
                      <li key={i}>{ref}</li>
                    ))}
                  </ul>
                </div>
              )}

              {selectedRoteiro.estrutura.justificativa_llm && (
                <div className="roteiro-justificativa">
                  <strong>Justificativa:</strong> {selectedRoteiro.estrutura.justificativa_llm}
                </div>
              )}
            </div>
            {selectedRoteiro.status === 'rascunho' && (
              <div className="modal-footer">
                <button onClick={() => handleRejeitar(selectedRoteiro.id)} className="btn btn-danger">
                  ✗ Rejeitar
                </button>
                <button onClick={() => handleAprovar(selectedRoteiro.id)} className="btn btn-success">
                  ✓ Aprovar Roteiro
                </button>
              </div>
            )}
          </div>
        </div>
      )}

      <div className="list">
        {roteiros.length === 0 ? (
          <div className="empty-state">Nenhum roteiro encontrado</div>
        ) : (
          roteiros.map((roteiro) => (
            <div key={roteiro.id} className="card">
              <div className="card-header">
                <h3 className="card-title">{roteiro.estrutura.titulo}</h3>
                <span
                  className="status-badge"
                  style={{ backgroundColor: getStatusColor(roteiro.status) }}
                >
                  {roteiro.status}
                </span>
              </div>
              <div className="card-meta">
                <span>Versão: {roteiro.versao}</span>
                <span>Duração: {formatDuration(roteiro.estrutura.duracao_total_segundos)}</span>
                <span>Blocos: {roteiro.estrutura.blocos.length}</span>
                <span>Ideia: {roteiro.ideia_id.slice(0, 8)}...</span>
              </div>
              <div className="card-actions">
                <button onClick={() => setSelectedRoteiro(roteiro)} className="btn btn-sm btn-secondary">
                  👁️ Ver Detalhes
                </button>
                {roteiro.status === 'rascunho' && (
                  <>
                    <button onClick={() => handleAprovar(roteiro.id)} className="btn btn-sm btn-success">
                      ✓ Aprovar
                    </button>
                    <button onClick={() => handleRejeitar(roteiro.id)} className="btn btn-sm btn-danger">
                      ✗ Rejeitar
                    </button>
                  </>
                )}
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
}
