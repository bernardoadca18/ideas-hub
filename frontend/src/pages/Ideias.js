import { jsx as _jsx, jsxs as _jsxs, Fragment as _Fragment } from "react/jsx-runtime";
import { useState, useEffect } from 'react';
import { api } from '../api/client';
export default function Ideias() {
    const [ideias, setIdeias] = useState([]);
    const [nichos, setNichos] = useState([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);
    // Form state
    const [showForm, setShowForm] = useState(false);
    const [titulo, setTitulo] = useState('');
    const [descricao, setDescricao] = useState('');
    const [nichoId, setNichoId] = useState('');
    // Filter state
    const [statusFilter, setStatusFilter] = useState('');
    // Collect trends modal
    const [showTrendsModal, setShowTrendsModal] = useState(false);
    const [selectedNichoForTrends, setSelectedNichoForTrends] = useState('');
    const [termosAdicionais, setTermosAdicionais] = useState('');
    const [collecting, setCollecting] = useState(false);
    useEffect(() => {
        loadData();
    }, [statusFilter]);
    async function loadData() {
        try {
            setLoading(true);
            const [ideiasData, nichosData] = await Promise.all([
                api.getIdeias(statusFilter ? { status: statusFilter } : undefined),
                api.getNichos(),
            ]);
            setIdeias(ideiasData);
            setNichos(nichosData);
            setError(null);
        }
        catch (err) {
            setError(err instanceof Error ? err.message : 'Erro ao carregar dados');
        }
        finally {
            setLoading(false);
        }
    }
    async function handleSubmit(e) {
        e.preventDefault();
        try {
            await api.createIdeia({
                titulo,
                descricao: descricao || undefined,
                nicho_id: nichoId || undefined,
            });
            setTitulo('');
            setDescricao('');
            setNichoId('');
            setShowForm(false);
            loadData();
        }
        catch (err) {
            setError(err instanceof Error ? err.message : 'Erro ao criar ideia');
        }
    }
    async function handleAprovar(id) {
        try {
            await api.aprovarIdeia(id);
            loadData();
        }
        catch (err) {
            setError(err instanceof Error ? err.message : 'Erro ao aprovar ideia');
        }
    }
    async function handleRejeitar(id) {
        try {
            await api.rejeitarIdeia(id);
            loadData();
        }
        catch (err) {
            setError(err instanceof Error ? err.message : 'Erro ao rejeitar ideia');
        }
    }
    async function handleGerarRoteiro(id) {
        try {
            await api.gerarRoteiro(id);
            alert('Roteiro gerado com sucesso!');
            loadData();
        }
        catch (err) {
            setError(err instanceof Error ? err.message : 'Erro ao gerar roteiro');
        }
    }
    async function handleColetarTrends(e) {
        e.preventDefault();
        if (!selectedNichoForTrends)
            return;
        try {
            setCollecting(true);
            const termos = termosAdicionais ? termosAdicionais.split(',').map(t => t.trim()).filter(Boolean) : undefined;
            const result = await api.coletarTrends(selectedNichoForTrends, termos);
            alert(`Coletadas ${result.total_coletado} trends!`);
            setShowTrendsModal(false);
            setSelectedNichoForTrends('');
            setTermosAdicionais('');
        }
        catch (err) {
            setError(err instanceof Error ? err.message : 'Erro ao coletar trends');
        }
        finally {
            setCollecting(false);
        }
    }
    function getStatusColor(status) {
        switch (status) {
            case 'rascunho': return '#9ca3af';
            case 'aprovada': return '#10b981';
            case 'rejeitada': return '#ef4444';
            case 'em_roteiro': return '#f59e0b';
            case 'roteirizada': return '#3b82f6';
            default: return '#9ca3af';
        }
    }
    if (loading)
        return _jsx("div", { className: "loading", children: "Carregando..." });
    if (error)
        return _jsx("div", { className: "error", children: error });
    return (_jsxs("div", { className: "page", children: [_jsxs("div", { className: "page-header", children: [_jsx("h1", { children: "Ideias" }), _jsxs("div", { className: "actions", children: [_jsxs("button", { onClick: () => setShowTrendsModal(true), className: "btn btn-secondary", children: [_jsx("svg", { width: "16", height: "16", viewBox: "0 0 24 24", fill: "none", stroke: "currentColor", strokeWidth: "2", children: _jsx("path", { d: "M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" }) }), "Buscar Trends"] }), _jsxs("button", { onClick: () => setShowForm(true), className: "btn btn-primary", children: [_jsx("svg", { width: "16", height: "16", viewBox: "0 0 24 24", fill: "none", stroke: "currentColor", strokeWidth: "2", children: _jsx("path", { d: "M12 5v14M5 12h14" }) }), "Nova Ideia"] })] })] }), _jsx("div", { className: "filters", children: _jsxs("select", { value: statusFilter, onChange: (e) => setStatusFilter(e.target.value), children: [_jsx("option", { value: "", children: "Todos os status" }), _jsx("option", { value: "rascunho", children: "Rascunho" }), _jsx("option", { value: "aprovada", children: "Aprovada" }), _jsx("option", { value: "rejeitada", children: "Rejeitada" }), _jsx("option", { value: "em_roteiro", children: "Em Roteiro" }), _jsx("option", { value: "roteirizada", children: "Roteirizada" })] }) }), showForm && (_jsx("div", { className: "modal-overlay", onClick: () => setShowForm(false), children: _jsxs("div", { className: "modal", onClick: (e) => e.stopPropagation(), children: [_jsx("h2", { children: "Nova Ideia" }), _jsxs("form", { onSubmit: handleSubmit, children: [_jsxs("div", { className: "form-group", children: [_jsx("label", { children: "T\u00EDtulo *" }), _jsx("input", { type: "text", value: titulo, onChange: (e) => setTitulo(e.target.value), required: true, maxLength: 300 })] }), _jsxs("div", { className: "form-group", children: [_jsx("label", { children: "Descri\u00E7\u00E3o" }), _jsx("textarea", { value: descricao, onChange: (e) => setDescricao(e.target.value), rows: 3 })] }), _jsxs("div", { className: "form-group", children: [_jsx("label", { children: "Nicho" }), _jsxs("select", { value: nichoId, onChange: (e) => setNichoId(e.target.value), children: [_jsx("option", { value: "", children: "Selecione um nicho" }), nichos.map((nicho) => (_jsx("option", { value: nicho.id, children: nicho.nome }, nicho.id)))] })] }), _jsxs("div", { className: "form-actions", children: [_jsx("button", { type: "button", onClick: () => setShowForm(false), className: "btn btn-secondary", children: "Cancelar" }), _jsx("button", { type: "submit", className: "btn btn-primary", children: "Criar" })] })] })] }) })), showTrendsModal && (_jsx("div", { className: "modal-overlay", onClick: () => setShowTrendsModal(false), children: _jsxs("div", { className: "modal", onClick: (e) => e.stopPropagation(), children: [_jsx("h2", { children: "Coletar Trends" }), _jsxs("form", { onSubmit: handleColetarTrends, children: [_jsxs("div", { className: "form-group", children: [_jsx("label", { children: "Nicho *" }), _jsxs("select", { value: selectedNichoForTrends, onChange: (e) => setSelectedNichoForTrends(e.target.value), required: true, children: [_jsx("option", { value: "", children: "Selecione um nicho" }), nichos.map((nicho) => (_jsx("option", { value: nicho.id, children: nicho.nome }, nicho.id)))] })] }), _jsxs("div", { className: "form-group", children: [_jsx("label", { children: "Termos Adicionais (separados por v\u00EDrgula)" }), _jsx("input", { type: "text", value: termosAdicionais, onChange: (e) => setTermosAdicionais(e.target.value), placeholder: "ex: intelig\u00EAncia artificial, tecnologia" })] }), _jsxs("div", { className: "form-actions", children: [_jsx("button", { type: "button", onClick: () => setShowTrendsModal(false), className: "btn btn-secondary", children: "Cancelar" }), _jsx("button", { type: "submit", className: "btn btn-primary", disabled: collecting, children: collecting ? 'Coletando...' : 'Coletar' })] })] })] }) })), _jsx("div", { className: "list", children: ideias.length === 0 ? (_jsx("div", { className: "empty-state", children: "Nenhuma ideia encontrada" })) : (ideias.map((ideia) => (_jsxs("div", { className: "card", children: [_jsxs("div", { className: "card-header", children: [_jsx("h3", { className: "card-title", children: ideia.titulo }), _jsx("span", { className: "status-badge", style: { backgroundColor: getStatusColor(ideia.status) }, children: ideia.status })] }), ideia.descricao_breve && (_jsx("p", { className: "card-description", children: ideia.descricao_breve })), _jsxs("div", { className: "card-meta", children: [_jsxs("span", { children: ["Origem: ", ideia.origem] }), _jsxs("span", { children: ["Criado: ", new Date(ideia.criado_em).toLocaleDateString()] })] }), _jsxs("div", { className: "card-actions", children: [ideia.status === 'rascunho' && (_jsxs(_Fragment, { children: [_jsxs("button", { onClick: () => handleAprovar(ideia.id), className: "btn btn-sm btn-success", children: [_jsx("svg", { width: "14", height: "14", viewBox: "0 0 24 24", fill: "none", stroke: "currentColor", strokeWidth: "2", children: _jsx("path", { d: "M5 13l4 4L19 7" }) }), "Aprovar"] }), _jsxs("button", { onClick: () => handleRejeitar(ideia.id), className: "btn btn-sm btn-danger", children: [_jsx("svg", { width: "14", height: "14", viewBox: "0 0 24 24", fill: "none", stroke: "currentColor", strokeWidth: "2", children: _jsx("path", { d: "M6 18L18 6M6 6l12 12" }) }), "Rejeitar"] })] })), ideia.status === 'aprovada' && (_jsxs("button", { onClick: () => handleGerarRoteiro(ideia.id), className: "btn btn-sm btn-primary", children: [_jsxs("svg", { width: "16", height: "16", viewBox: "0 0 24 24", fill: "none", stroke: "currentColor", strokeWidth: "2", children: [_jsx("path", { d: "M12 19l7-7 3 3-7 7-3-3z" }), _jsx("path", { d: "M18 13l-1.5-7.5L2 2l3.5 14.5L13 18l5-5z" }), _jsx("path", { d: "M2 2l7.586 7.586" }), _jsx("circle", { cx: "11", cy: "11", r: "2" })] }), "Gerar Roteiro"] }))] })] }, ideia.id)))) })] }));
}
