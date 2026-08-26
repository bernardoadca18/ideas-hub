import { jsx as _jsx, jsxs as _jsxs, Fragment as _Fragment } from "react/jsx-runtime";
import { useState, useEffect } from 'react';
import { api } from '../api/client';
export default function Roteiros() {
    const [roteiros, setRoteiros] = useState([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);
    // Filter state
    const [statusFilter, setStatusFilter] = useState('');
    // Selected roteiro for detail view
    const [selectedRoteiro, setSelectedRoteiro] = useState(null);
    useEffect(() => {
        loadData();
    }, [statusFilter]);
    async function loadData() {
        try {
            setLoading(true);
            const roteirosData = await api.getRoteiros(statusFilter ? { status: statusFilter } : undefined);
            setRoteiros(roteirosData);
            setError(null);
        }
        catch (err) {
            setError(err instanceof Error ? err.message : 'Erro ao carregar dados');
        }
        finally {
            setLoading(false);
        }
    }
    async function handleAprovar(id) {
        try {
            await api.aprovarRoteiro(id);
            alert('Roteiro aprovado!');
            loadData();
        }
        catch (err) {
            setError(err instanceof Error ? err.message : 'Erro ao aprovar roteiro');
        }
    }
    async function handleRejeitar(id) {
        try {
            await api.rejeitarRoteiro(id);
            alert('Roteiro rejeitado. A ideia voltou para status aprovada.');
            loadData();
        }
        catch (err) {
            setError(err instanceof Error ? err.message : 'Erro ao rejeitar roteiro');
        }
    }
    function getStatusColor(status) {
        switch (status) {
            case 'rascunho': return '#9ca3af';
            case 'aprovado': return '#10b981';
            case 'rejeitado': return '#ef4444';
            default: return '#9ca3af';
        }
    }
    function formatDuration(seconds) {
        const minutes = Math.floor(seconds / 60);
        const secs = seconds % 60;
        return `${minutes}:${secs.toString().padStart(2, '0')}`;
    }
    if (loading)
        return _jsx("div", { className: "loading", children: "Carregando..." });
    if (error)
        return _jsx("div", { className: "error", children: error });
    return (_jsxs("div", { className: "page", children: [_jsx("div", { className: "page-header", children: _jsx("h1", { children: "Roteiros" }) }), _jsx("div", { className: "filters", children: _jsxs("select", { value: statusFilter, onChange: (e) => setStatusFilter(e.target.value), children: [_jsx("option", { value: "", children: "Todos os status" }), _jsx("option", { value: "rascunho", children: "Rascunho" }), _jsx("option", { value: "aprovado", children: "Aprovado" }), _jsx("option", { value: "rejeitado", children: "Rejeitado" })] }) }), selectedRoteiro && (_jsx("div", { className: "modal-overlay", onClick: () => setSelectedRoteiro(null), children: _jsxs("div", { className: "modal modal-large", onClick: (e) => e.stopPropagation(), children: [_jsxs("div", { className: "modal-header", children: [_jsx("h2", { children: selectedRoteiro.estrutura.titulo }), _jsx("button", { onClick: () => setSelectedRoteiro(null), className: "btn-close", children: "\u00D7" })] }), _jsxs("div", { className: "modal-body", children: [_jsxs("div", { className: "roteiro-info", children: [_jsx("span", { className: "status-badge", style: { backgroundColor: getStatusColor(selectedRoteiro.status) }, children: selectedRoteiro.status }), _jsxs("span", { children: ["Vers\u00E3o: ", selectedRoteiro.versao] }), _jsxs("span", { children: ["Dura\u00E7\u00E3o: ", formatDuration(selectedRoteiro.estrutura.duracao_total_segundos)] }), _jsxs("span", { children: ["Blocos: ", selectedRoteiro.estrutura.blocos.length] })] }), _jsx("div", { className: "blocos-list", children: selectedRoteiro.estrutura.blocos.map((bloco, index) => (_jsxs("div", { className: "bloco-card", children: [_jsxs("div", { className: "bloco-header", children: [_jsx("h4", { children: bloco.tipo }), _jsx("span", { children: formatDuration(bloco.duracao_segundos) })] }), _jsx("div", { className: "bloco-conteudo", children: _jsx("p", { children: bloco.conteudo }) }), bloco.dicas_visual && (_jsxs("div", { className: "bloco-dica", children: [_jsx("strong", { children: "Visual:" }), " ", bloco.dicas_visual] })), bloco.dicas_audio && (_jsxs("div", { className: "bloco-dica", children: [_jsx("strong", { children: "\u00C1udio:" }), " ", bloco.dicas_audio] }))] }, index))) }), selectedRoteiro.estrutura.tags.length > 0 && (_jsxs("div", { className: "roteiro-tags", children: [_jsx("strong", { children: "Tags:" }), selectedRoteiro.estrutura.tags.map((tag, i) => (_jsx("span", { className: "tag", children: tag }, i)))] })), selectedRoteiro.estrutura.referencias && selectedRoteiro.estrutura.referencias.length > 0 && (_jsxs("div", { className: "roteiro-referencias", children: [_jsx("strong", { children: "Refer\u00EAncias:" }), _jsx("ul", { children: selectedRoteiro.estrutura.referencias.map((ref, i) => (_jsx("li", { children: ref }, i))) })] })), selectedRoteiro.estrutura.justificativa_llm && (_jsxs("div", { className: "roteiro-justificativa", children: [_jsx("strong", { children: "Justificativa:" }), " ", selectedRoteiro.estrutura.justificativa_llm] }))] }), selectedRoteiro.status === 'rascunho' && (_jsxs("div", { className: "modal-footer", children: [_jsxs("button", { onClick: () => handleRejeitar(selectedRoteiro.id), className: "btn btn-danger", children: [_jsx("svg", { width: "16", height: "16", viewBox: "0 0 24 24", fill: "none", stroke: "currentColor", strokeWidth: "2", children: _jsx("path", { d: "M6 18L18 6M6 6l12 12" }) }), "Rejeitar"] }), _jsxs("button", { onClick: () => handleAprovar(selectedRoteiro.id), className: "btn btn-success", children: [_jsx("svg", { width: "16", height: "16", viewBox: "0 0 24 24", fill: "none", stroke: "currentColor", strokeWidth: "2", children: _jsx("path", { d: "M5 13l4 4L19 7" }) }), "Aprovar Roteiro"] })] }))] }) })), _jsx("div", { className: "list", children: roteiros.length === 0 ? (_jsx("div", { className: "empty-state", children: "Nenhum roteiro encontrado" })) : (roteiros.map((roteiro) => (_jsxs("div", { className: "card", children: [_jsxs("div", { className: "card-header", children: [_jsx("h3", { className: "card-title", children: roteiro.estrutura.titulo }), _jsx("span", { className: "status-badge", style: { backgroundColor: getStatusColor(roteiro.status) }, children: roteiro.status })] }), _jsxs("div", { className: "card-meta", children: [_jsxs("span", { children: ["Vers\u00E3o: ", roteiro.versao] }), _jsxs("span", { children: ["Dura\u00E7\u00E3o: ", formatDuration(roteiro.estrutura.duracao_total_segundos)] }), _jsxs("span", { children: ["Blocos: ", roteiro.estrutura.blocos.length] }), _jsxs("span", { children: ["Ideia: ", roteiro.ideia_id.slice(0, 8), "..."] })] }), _jsxs("div", { className: "card-actions", children: [_jsxs("button", { onClick: () => setSelectedRoteiro(roteiro), className: "btn btn-sm btn-secondary", children: [_jsxs("svg", { width: "16", height: "16", viewBox: "0 0 24 24", fill: "none", stroke: "currentColor", strokeWidth: "2", children: [_jsx("path", { d: "M15 12a3 3 0 11-6 0 3 3 0 016 0z" }), _jsx("path", { d: "M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z" })] }), "Ver Detalhes"] }), roteiro.status === 'rascunho' && (_jsxs(_Fragment, { children: [_jsxs("button", { onClick: () => handleAprovar(roteiro.id), className: "btn btn-sm btn-success", children: [_jsx("svg", { width: "14", height: "14", viewBox: "0 0 24 24", fill: "none", stroke: "currentColor", strokeWidth: "2", children: _jsx("path", { d: "M5 13l4 4L19 7" }) }), "Aprovar"] }), _jsxs("button", { onClick: () => handleRejeitar(roteiro.id), className: "btn btn-sm btn-danger", children: [_jsx("svg", { width: "14", height: "14", viewBox: "0 0 24 24", fill: "none", stroke: "currentColor", strokeWidth: "2", children: _jsx("path", { d: "M6 18L18 6M6 6l12 12" }) }), "Rejeitar"] })] }))] })] }, roteiro.id)))) })] }));
}
