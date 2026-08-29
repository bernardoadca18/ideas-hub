import { jsx as _jsx, jsxs as _jsxs, Fragment as _Fragment } from "react/jsx-runtime";
import { useEffect, useState } from 'react';
import { api } from '../api/client';
function formatDuration(seconds) {
    const minutes = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${minutes}:${secs.toString().padStart(2, '0')}`;
}
function statusColor(status) {
    if (status === 'aprovado')
        return '#10b981';
    if (status === 'rejeitado')
        return '#ef4444';
    return '#6b7280';
}
export default function Roteiros() {
    const [roteiros, setRoteiros] = useState([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);
    const [statusFilter, setStatusFilter] = useState('');
    const [selected, setSelected] = useState(null);
    const [editDraft, setEditDraft] = useState(null);
    const [feedback, setFeedback] = useState('');
    const [regenerating, setRegenerating] = useState(false);
    useEffect(() => { void loadData(); }, [statusFilter]);
    async function loadData() {
        try {
            setLoading(true);
            setRoteiros(await api.getRoteiros(statusFilter ? { status: statusFilter } : undefined));
            setError(null);
        }
        catch (err) {
            setError(err instanceof Error ? err.message : 'Erro ao carregar roteiros');
        }
        finally {
            setLoading(false);
        }
    }
    async function approve(script) {
        try {
            await api.aprovarRoteiro(script.id);
            setSelected(null);
            await loadData();
        }
        catch (err) {
            setError(err instanceof Error ? err.message : 'Erro ao aprovar roteiro');
        }
    }
    async function reject(script) {
        try {
            await api.rejeitarRoteiro(script.id);
            setSelected(null);
            await loadData();
        }
        catch (err) {
            setError(err instanceof Error ? err.message : 'Erro ao rejeitar roteiro');
        }
    }
    function beginEdit(script) {
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
    async function saveEdit(e) {
        e.preventDefault();
        if (!selected || !editDraft)
            return;
        try {
            const created = await api.editarRoteiroComoRevisao(selected.id, editDraft);
            setSelected(created);
            setEditDraft(null);
            await loadData();
        }
        catch (err) {
            setError(err instanceof Error ? err.message : 'Erro ao criar revisão');
        }
    }
    async function regenerate(e) {
        e.preventDefault();
        if (!selected || !feedback.trim())
            return;
        setRegenerating(true);
        try {
            const created = await api.regenerarRoteiroComFeedback(selected.id, feedback);
            setSelected(created);
            setFeedback('');
            await loadData();
        }
        catch (err) {
            setError(err instanceof Error ? err.message : 'Erro ao regenerar roteiro');
        }
        finally {
            setRegenerating(false);
        }
    }
    function updateBlock(index, field, value) {
        if (!editDraft)
            return;
        const blocks = editDraft.blocos.map((block, current) => current === index ? { ...block, [field]: value } : block);
        setEditDraft({ ...editDraft, blocos: blocks });
    }
    if (loading)
        return _jsx("div", { className: "loading", children: "Carregando..." });
    const latestVersionByIdea = new Map();
    for (const script of roteiros) {
        latestVersionByIdea.set(script.ideia_id, Math.max(latestVersionByIdea.get(script.ideia_id) || 0, script.versao));
    }
    const selectedIsLatest = selected
        ? selected.versao === latestVersionByIdea.get(selected.ideia_id)
        : false;
    return (_jsxs("div", { className: "page", children: [_jsx("div", { className: "page-header", children: _jsx("h1", { children: "Roteiros" }) }), error && _jsxs("div", { className: "error", children: [error, " ", _jsx("button", { onClick: () => setError(null), children: "Fechar" })] }), _jsx("div", { className: "filters", children: _jsxs("select", { value: statusFilter, onChange: (e) => setStatusFilter(e.target.value), children: [_jsx("option", { value: "", children: "Todos os status" }), _jsx("option", { value: "rascunho", children: "Rascunho" }), _jsx("option", { value: "aprovado", children: "Aprovado" }), _jsx("option", { value: "rejeitado", children: "Rejeitado" })] }) }), selected && (_jsx("div", { className: "modal-overlay", onClick: () => { setSelected(null); setEditDraft(null); }, children: _jsxs("div", { className: "modal modal-large", onClick: (e) => e.stopPropagation(), children: [_jsxs("div", { className: "modal-header", children: [_jsx("h2", { children: editDraft ? 'Nova revisão humana' : selected.estrutura.titulo }), _jsx("button", { onClick: () => { setSelected(null); setEditDraft(null); }, className: "btn-close", children: "\u00D7" })] }), editDraft ? (_jsxs("form", { onSubmit: saveEdit, children: [_jsx("p", { className: "form-help", children: "A revis\u00E3o cria uma nova vers\u00E3o. IDs, timestamps e provenance de VisualQueries s\u00E3o preservados e n\u00E3o s\u00E3o edit\u00E1veis aqui." }), _jsxs("div", { className: "form-group", children: [_jsx("label", { children: "T\u00EDtulo" }), _jsx("input", { value: editDraft.titulo, onChange: (e) => setEditDraft({ ...editDraft, titulo: e.target.value }), required: true })] }), editDraft.blocos.map((block, index) => (_jsxs("fieldset", { className: "script-edit-block", children: [_jsxs("legend", { children: ["Bloco ", index + 1] }), _jsxs("div", { className: "form-group", children: [_jsx("label", { children: "Tipo editorial" }), _jsx("input", { value: block.tipo, onChange: (e) => updateBlock(index, 'tipo', e.target.value), required: true })] }), _jsxs("div", { className: "form-group", children: [_jsx("label", { children: "Dura\u00E7\u00E3o estimada (segundos)" }), _jsx("input", { type: "number", min: 1, value: block.duracao_segundos, onChange: (e) => updateBlock(index, 'duracao_segundos', Number(e.target.value)), required: true })] }), _jsxs("div", { className: "form-group", children: [_jsx("label", { children: "Narra\u00E7\u00E3o" }), _jsx("textarea", { rows: 8, value: block.conteudo, onChange: (e) => updateBlock(index, 'conteudo', e.target.value), required: true })] }), _jsxs("div", { className: "form-group", children: [_jsx("label", { children: "Dicas visuais" }), _jsx("textarea", { rows: 3, value: block.dicas_visual || '', onChange: (e) => updateBlock(index, 'dicas_visual', e.target.value) })] }), _jsxs("div", { className: "form-group", children: [_jsx("label", { children: "Dicas de \u00E1udio" }), _jsx("textarea", { rows: 3, value: block.dicas_audio || '', onChange: (e) => updateBlock(index, 'dicas_audio', e.target.value) })] }), _jsxs("small", { children: [selected.estrutura.blocos[index].visual_queries?.length || 0, " VisualQueries preservadas sem altera\u00E7\u00E3o."] })] }, index))), _jsxs("div", { className: "form-group", children: [_jsx("label", { children: "Resumo da edi\u00E7\u00E3o (opcional)" }), _jsx("textarea", { rows: 3, value: editDraft.edit_summary || '', onChange: (e) => setEditDraft({ ...editDraft, edit_summary: e.target.value }) })] }), _jsxs("div", { className: "form-actions", children: [_jsx("button", { type: "button", className: "btn btn-secondary", onClick: () => setEditDraft(null), children: "Cancelar" }), _jsx("button", { className: "btn btn-primary", type: "submit", children: "Salvar como nova vers\u00E3o" })] })] })) : (_jsxs(_Fragment, { children: [_jsxs("div", { className: "roteiro-info", children: [_jsx("span", { className: "status-badge", style: { backgroundColor: statusColor(selected.status) }, children: selected.status }), _jsxs("span", { children: ["Vers\u00E3o ", selected.versao] }), _jsx("span", { children: formatDuration(selected.estrutura.duracao_total_segundos) }), _jsxs("span", { children: [selected.estrutura.blocos.length, " blocos"] }), _jsxs("span", { children: ["Origem: ", selected.revision_kind] })] }), _jsxs("div", { className: "script-provenance", children: [_jsx("strong", { children: "Contexto do autor usado nesta vers\u00E3o" }), _jsx("p", { children: selected.author_briefing_snapshot || 'Nenhum contexto fornecido.' }), _jsx("code", { children: selected.author_briefing_identity || 'snapshot histórico indisponível' }), selected.author_briefing_changed_since_creation === true && _jsx("span", { className: "context-changed", children: "O contexto atual da ideia mudou desde esta vers\u00E3o." })] }), _jsx("div", { className: "blocos-list", children: selected.estrutura.blocos.map((block, index) => (_jsxs("div", { className: "bloco-card", children: [_jsxs("div", { className: "bloco-header", children: [_jsx("h4", { children: block.tipo }), _jsx("span", { children: formatDuration(block.duracao_segundos) })] }), _jsx("div", { className: "bloco-conteudo", children: _jsx("p", { children: block.conteudo }) }), block.dicas_visual && _jsxs("div", { className: "bloco-dica", children: [_jsx("strong", { children: "Visual:" }), " ", block.dicas_visual] }), block.dicas_audio && _jsxs("div", { className: "bloco-dica", children: [_jsx("strong", { children: "\u00C1udio:" }), " ", block.dicas_audio] }), (block.visual_queries?.length || 0) > 0 && _jsxs("div", { className: "bloco-dica", children: [_jsx("strong", { children: "VisualQueries:" }), " ", block.visual_queries?.length, " preservadas com provenance."] })] }, index))) }), _jsxs("div", { className: "revision-actions", children: [_jsx("button", { className: "btn btn-secondary", onClick: () => beginEdit(selected), children: "Editar como nova vers\u00E3o" }), _jsxs("form", { onSubmit: regenerate, className: "feedback-form", children: [_jsx("label", { htmlFor: "revision-feedback", children: _jsx("strong", { children: "Regenerar com feedback" }) }), _jsx("textarea", { id: "revision-feedback", rows: 3, value: feedback, onChange: (e) => setFeedback(e.target.value), placeholder: "Ex.: A introdu\u00E7\u00E3o est\u00E1 longa; mantenha o trecho sobre Z e n\u00E3o afirme Y." }), _jsx("button", { className: "btn btn-primary", disabled: regenerating || !feedback.trim(), type: "submit", children: regenerating ? 'Regenerando…' : 'Criar nova versão' })] })] }), selected.status === 'rascunho' && _jsx("div", { className: "modal-footer", children: selectedIsLatest ? _jsxs(_Fragment, { children: [_jsx("button", { onClick: () => reject(selected), className: "btn btn-danger", children: "Rejeitar" }), _jsx("button", { onClick: () => approve(selected), className: "btn btn-success", children: "Aprovar vers\u00E3o" })] }) : _jsx("span", { className: "form-help", children: "Somente o draft mais recente pode ser aprovado ou rejeitado." }) })] }))] }) })), _jsx("div", { className: "list", children: roteiros.length === 0 ? _jsx("div", { className: "empty-state", children: "Nenhum roteiro encontrado" }) : roteiros.map((script) => (_jsxs("div", { className: "card", children: [_jsxs("div", { className: "card-header", children: [_jsx("h3", { className: "card-title", children: script.estrutura.titulo }), _jsx("span", { className: "status-badge", style: { backgroundColor: statusColor(script.status) }, children: script.status })] }), _jsxs("div", { className: "card-meta", children: [_jsxs("span", { children: ["Vers\u00E3o: ", script.versao] }), _jsxs("span", { children: ["Origem: ", script.revision_kind] }), _jsxs("span", { children: ["Dura\u00E7\u00E3o: ", formatDuration(script.estrutura.duracao_total_segundos)] }), _jsxs("span", { children: ["Ideia: ", script.ideia_id.slice(0, 8), "\u2026"] })] }), _jsxs("div", { className: "card-actions", children: [_jsx("button", { onClick: () => { setSelected(script); setFeedback(''); }, className: "btn btn-sm btn-secondary", children: "Revisar detalhes" }), script.status === 'rascunho' && script.versao === latestVersionByIdea.get(script.ideia_id) && _jsxs(_Fragment, { children: [_jsx("button", { onClick: () => approve(script), className: "btn btn-sm btn-success", children: "Aprovar" }), _jsx("button", { onClick: () => reject(script), className: "btn btn-sm btn-danger", children: "Rejeitar" })] })] })] }, script.id))) })] }));
}
