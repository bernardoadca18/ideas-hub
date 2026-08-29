const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000';
// API Client
class ApiClient {
    constructor(baseUrl) {
        Object.defineProperty(this, "baseUrl", {
            enumerable: true,
            configurable: true,
            writable: true,
            value: void 0
        });
        this.baseUrl = baseUrl;
    }
    async request(path, options) {
        const response = await fetch(`${this.baseUrl}${path}`, {
            headers: {
                'Content-Type': 'application/json',
                ...options?.headers,
            },
            ...options,
        });
        if (!response.ok) {
            const error = await response.text();
            throw new Error(`API Error ${response.status}: ${error}`);
        }
        if (response.status === 204) {
            return undefined;
        }
        return response.json();
    }
    // Nichos
    async getNichos() {
        return this.request('/nichos/');
    }
    async createNicho(data) {
        return this.request('/nichos/', {
            method: 'POST',
            body: JSON.stringify(data),
        });
    }
    // Ideias
    async getIdeias(params) {
        const searchParams = new URLSearchParams();
        if (params?.status)
            searchParams.set('status', params.status);
        if (params?.nicho_id)
            searchParams.set('nicho_id', params.nicho_id);
        const query = searchParams.toString();
        return this.request(`/ideias/${query ? `?${query}` : ''}`);
    }
    async createIdeia(data) {
        return this.request('/ideias/', {
            method: 'POST',
            body: JSON.stringify(data),
        });
    }
    async updateIdeia(id, data) {
        return this.request(`/ideias/${id}`, {
            method: 'PUT',
            body: JSON.stringify(data),
        });
    }
    async aprovarIdeia(id) {
        return this.request(`/ideias/${id}/aprovar`, { method: 'PATCH' });
    }
    async rejeitarIdeia(id) {
        return this.request(`/ideias/${id}/rejeitar`, { method: 'PATCH' });
    }
    async gerarRoteiro(ideiaId) {
        return this.request(`/ideias/${ideiaId}/roteiro`, { method: 'POST' });
    }
    // Trends
    async getTrends(params) {
        const searchParams = new URLSearchParams();
        if (params?.status)
            searchParams.set('status', params.status);
        if (params?.nicho_id)
            searchParams.set('nicho_id', params.nicho_id);
        const query = searchParams.toString();
        return this.request(`/trends/${query ? `?${query}` : ''}`);
    }
    async coletarTrends(nichoId, termosAdicionais) {
        return this.request('/trends/coletar', {
            method: 'POST',
            body: JSON.stringify({ nicho_id: nichoId, termos_adicionais: termosAdicionais }),
        });
    }
    async aprovarTrend(id) {
        return this.request(`/trends/${id}/aprovar`, { method: 'PATCH' });
    }
    async rejeitarTrend(id) {
        return this.request(`/trends/${id}/rejeitar`, { method: 'PATCH' });
    }
    async gerarIdeiasFromTrend(trendId, numIdeias) {
        const params = numIdeias ? `?num_ideias=${numIdeias}` : '';
        return this.request(`/trends/${trendId}/gerar-ideias${params}`, { method: 'POST' });
    }
    // Roteiros
    async getRoteiros(params) {
        const searchParams = new URLSearchParams();
        if (params?.status)
            searchParams.set('status', params.status);
        const query = searchParams.toString();
        return this.request(`/roteiros/${query ? `?${query}` : ''}`);
    }
    async getRoteiro(id) {
        return this.request(`/roteiros/${id}`);
    }
    async aprovarRoteiro(id) {
        return this.request(`/roteiros/${id}/aprovar`, { method: 'PATCH' });
    }
    async rejeitarRoteiro(id) {
        return this.request(`/roteiros/${id}/rejeitar`, { method: 'PATCH' });
    }
    async editarRoteiroComoRevisao(id, data) {
        return this.request(`/roteiros/${id}/revisoes/editar`, {
            method: 'POST',
            body: JSON.stringify(data),
        });
    }
    async regenerarRoteiroComFeedback(id, feedback) {
        return this.request(`/roteiros/${id}/revisoes/regenerar`, {
            method: 'POST',
            body: JSON.stringify({ feedback }),
        });
    }
}
export const api = new ApiClient(API_BASE);
