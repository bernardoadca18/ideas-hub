import { jsx as _jsx, jsxs as _jsxs, Fragment as _Fragment } from "react/jsx-runtime";
import { useState, useEffect } from 'react';
import { api } from '../api/client';
export default function Trends() {
    const [trends, setTrends] = useState([]);
    const [nichos, setNichos] = useState([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);
    // Filter state
    const [statusFilter, setStatusFilter] = useState('pendente');
    const [nichoFilter, setNichoFilter] = useState('');
    // Batch actions
    const [selectedTrends, setSelectedTrends] = useState(new Set());
    const [processing, setProcessing] = useState(false);
    // Generate ideas modal
    const [showGenerateModal, setShowGenerateModal] = useState(false);
    const [selectedTrendForIdeas, setSelectedTrendForIdeas] = useState(null);
    const [numIdeias, setNumIdeias] = useState(3);
    const [generating, setGenerating] = useState(false);
    useEffect(() => {
        loadData();
    }, [statusFilter, nichoFilter]);
    async function loadData() {
        try {
            setLoading(true);
            const [trendsData, nichosData] = await Promise.all([
                api.getTrends(statusFilter || nichoFilter
                    ? { status: statusFilter || undefined, nicho_id: nichoFilter || undefined }
                    : undefined),
                api.getNichos(),
            ]);
            setTrends(trendsData);
            setNichos(nichosData);
            setSelectedTrends(new Set());
            setError(null);
        }
        catch (err) {
            setError(err instanceof Error ? err.message : 'Erro ao carregar dados');
        }
        finally {
            setLoading(false);
        }
    }
    function toggleSelect(id) {
        const newSelected = new Set(selectedTrends);
        if (newSelected.has(id)) {
            newSelected.delete(id);
        }
        else {
            newSelected.add(id);
        }
        setSelectedTrends(newSelected);
    }
    function selectAll() {
        if (selectedTrends.size === trends.length) {
            setSelectedTrends(new Set());
        }
        else {
            setSelectedTrends(new Set(trends.map(t => t.id)));
        }
    }
    async function handleBatchApprove() {
        if (selectedTrends.size === 0)
            return;
        try {
            setProcessing(true);
            const promises = Array.from(selectedTrends).map(id => api.aprovarTrend(id));
            await Promise.all(promises);
            setSelectedTrends(new Set());
            loadData();
        }
        catch (err) {
            setError(err instanceof Error ? err.message : 'Erro ao aprovar trends');
        }
        finally {
            setProcessing(false);
        }
    }
    async function handleBatchReject() {
        if (selectedTrends.size === 0)
            return;
        try {
            setProcessing(true);
            const promises = Array.from(selectedTrends).map(id => api.rejeitarTrend(id));
            await Promise.all(promises);
            setSelectedTrends(new Set());
            loadData();
        }
        catch (err) {
            setError(err instanceof Error ? err.message : 'Erro ao rejeitar trends');
        }
        finally {
            setProcessing(false);
        }
    }
    async function handleAprovar(id) {
        try {
            await api.aprovarTrend(id);
            loadData();
        }
        catch (err) {
            setError(err instanceof Error ? err.message : 'Erro ao aprovar trend');
        }
    }
    async function handleRejeitar(id) {
        try {
            await api.rejeitarTrend(id);
            loadData();
        }
        catch (err) {
            setError(err instanceof Error ? err.message : 'Erro ao rejeitar trend');
        }
    }
    function openGenerateModal(trend) {
        setSelectedTrendForIdeas(trend);
        setNumIdeias(3);
        setShowGenerateModal(true);
    }
    async function handleGenerateIdeas(e) {
        e.preventDefault();
        if (!selectedTrendForIdeas)
            return;
        try {
            setGenerating(true);
            const result = await api.gerarIdeiasFromTrend(selectedTrendForIdeas.id, numIdeias);
            alert(`Geradas ${result.ideias_geradas} ideias!`);
            setShowGenerateModal(false);
            setSelectedTrendForIdeas(null);
            loadData();
        }
        catch (err) {
            setError(err instanceof Error ? err.message : 'Erro ao gerar ideias');
        }
        finally {
            setGenerating(false);
        }
    }
    function getStatusColor(status) {
        switch (status) {
            case 'pendente': return '#f59e0b';
            case 'aprovada': return '#10b981';
            case 'rejeitada': return '#ef4444';
            default: return '#9ca3af';
        }
    }
    if (loading)
        return _jsx("div", { className: "loading", children: "Carregando..." });
    if (error)
        return _jsx("div", { className: "error", children: error });
    return (_jsxs("div", { className: "page", children: [_jsx("div", { className: "page-header", children: _jsx("h1", { children: "Trends" }) }), _jsxs("div", { className: "filters", children: [_jsxs("select", { value: statusFilter, onChange: (e) => setStatusFilter(e.target.value), children: [_jsx("option", { value: "", children: "Todos os status" }), _jsx("option", { value: "pendente", children: "Pendente" }), _jsx("option", { value: "aprovada", children: "Aprovada" }), _jsx("option", { value: "rejeitada", children: "Rejeitada" })] }), _jsxs("select", { value: nichoFilter, onChange: (e) => setNichoFilter(e.target.value), children: [_jsx("option", { value: "", children: "Todos os nichos" }), nichos.map((nicho) => (_jsx("option", { value: nicho.id, children: nicho.nome }, nicho.id)))] })] }), selectedTrends.size > 0 && (_jsxs("div", { className: "batch-actions", children: [_jsxs("span", { children: [selectedTrends.size, " selecionados"] }), _jsxs("button", { onClick: handleBatchApprove, className: "btn btn-sm btn-success", disabled: processing, children: [_jsx("svg", { width: "14", height: "14", viewBox: "0 0 24 24", fill: "none", stroke: "currentColor", strokeWidth: "2", children: _jsx("path", { d: "M5 13l4 4L19 7" }) }), "Aprovar Selecionados"] }), _jsxs("button", { onClick: handleBatchReject, className: "btn btn-sm btn-danger", disabled: processing, children: [_jsx("svg", { width: "14", height: "14", viewBox: "0 0 24 24", fill: "none", stroke: "currentColor", strokeWidth: "2", children: _jsx("path", { d: "M6 18L18 6M6 6l12 12" }) }), "Rejeitar Selecionados"] })] })), showGenerateModal && selectedTrendForIdeas && (_jsx("div", { className: "modal-overlay", onClick: () => setShowGenerateModal(false), children: _jsxs("div", { className: "modal", onClick: (e) => e.stopPropagation(), children: [_jsx("h2", { children: "Gerar Ideias" }), _jsxs("p", { children: ["Trend: ", _jsx("strong", { children: selectedTrendForIdeas.termo_bruto })] }), _jsxs("form", { onSubmit: handleGenerateIdeas, children: [_jsxs("div", { className: "form-group", children: [_jsx("label", { children: "N\u00FAmero de Ideias" }), _jsx("input", { type: "number", value: numIdeias, onChange: (e) => setNumIdeias(parseInt(e.target.value) || 3), min: 1, max: 10 })] }), _jsxs("div", { className: "form-actions", children: [_jsx("button", { type: "button", onClick: () => setShowGenerateModal(false), className: "btn btn-secondary", children: "Cancelar" }), _jsx("button", { type: "submit", className: "btn btn-primary", disabled: generating, children: generating ? 'Gerando...' : 'Gerar' })] })] })] }) })), _jsx("div", { className: "list", children: trends.length === 0 ? (_jsx("div", { className: "empty-state", children: "Nenhuma trend encontrada" })) : (_jsxs(_Fragment, { children: [_jsxs("div", { className: "list-header", children: [_jsx("input", { type: "checkbox", checked: selectedTrends.size === trends.length && trends.length > 0, onChange: selectAll }), _jsx("span", { children: "Selecionar todos" })] }), trends.map((trend) => (_jsxs("div", { className: "card", children: [_jsxs("div", { className: "card-row", children: [_jsx("input", { type: "checkbox", checked: selectedTrends.has(trend.id), onChange: () => toggleSelect(trend.id) }), _jsxs("div", { className: "card-content", children: [_jsxs("div", { className: "card-header", children: [_jsx("h3", { className: "card-title", children: trend.termo_bruto }), _jsx("span", { className: "status-badge", style: { backgroundColor: getStatusColor(trend.status) }, children: trend.status })] }), _jsxs("div", { className: "card-meta", children: [_jsxs("span", { children: ["Fonte: ", trend.fonte] }), trend.payload_raw?.title != null && (_jsxs("span", { children: ["T\u00EDtulo: ", String(trend.payload_raw.title)] })), _jsxs("span", { children: ["Criado: ", new Date(trend.criado_em).toLocaleDateString()] })] })] })] }), _jsxs("div", { className: "card-actions", children: [trend.status === 'pendente' && (_jsxs(_Fragment, { children: [_jsxs("button", { onClick: () => handleAprovar(trend.id), className: "btn btn-sm btn-success", children: [_jsx("svg", { width: "14", height: "14", viewBox: "0 0 24 24", fill: "none", stroke: "currentColor", strokeWidth: "2", children: _jsx("path", { d: "M5 13l4 4L19 7" }) }), "Aprovar"] }), _jsxs("button", { onClick: () => handleRejeitar(trend.id), className: "btn btn-sm btn-danger", children: [_jsx("svg", { width: "14", height: "14", viewBox: "0 0 24 24", fill: "none", stroke: "currentColor", strokeWidth: "2", children: _jsx("path", { d: "M6 18L18 6M6 6l12 12" }) }), "Rejeitar"] })] })), trend.status === 'aprovada' && (_jsxs("button", { onClick: () => openGenerateModal(trend), className: "btn btn-sm btn-primary", children: [_jsx("svg", { width: "16", height: "16", viewBox: "0 0 24 24", fill: "none", stroke: "currentColor", strokeWidth: "2", children: _jsx("path", { d: "M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" }) }), "Gerar Ideias"] }))] })] }, trend.id)))] })) })] }));
}
