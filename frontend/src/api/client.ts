const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000';

// Types
export interface Nicho {
  id: string;
  slug: string;
  nome: string;
  descricao?: string;
  prompt_ideacao: string;
  prompt_roteiro: string;
  ativo: boolean;
}

export interface Ideia {
  id: string;
  nicho_id?: string;
  origem: string;
  titulo: string;
  descricao_breve?: string;
  status: string;
  eh_continuacao_de?: string;
  numero_parte?: number;
  fonte_trend_id?: string;
  justificativa_llm?: string;
  criado_em: string;
  atualizado_em: string;
}

export interface Trend {
  id: string;
  nicho_id?: string;
  termo_bruto: string;
  termo_normalizado?: string;
  fonte: string;
  status: string;
  payload_raw?: Record<string, unknown>;
  criado_em: string;
}

export interface Roteiro {
  id: string;
  ideia_id: string;
  versao: number;
  estrutura: {
    titulo: string;
    duracao_total_segundos: number;
    blocos: BlocoNarrativo[];
    tags: string[];
    referencias?: string[];
    justificativa_llm?: string;
  };
  status: string;
  criado_em: string;
  atualizado_em: string;
}

export interface BlocoNarrativo {
  tipo: string;
  duracao_segundos: number;
  conteudo: string;
  dicas_visual?: string;
  dicas_audio?: string;
}

// API Client
class ApiClient {
  private baseUrl: string;

  constructor(baseUrl: string) {
    this.baseUrl = baseUrl;
  }

  private async request<T>(path: string, options?: RequestInit): Promise<T> {
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
      return undefined as T;
    }

    return response.json();
  }

  // Nichos
  async getNichos(): Promise<Nicho[]> {
    return this.request<Nicho[]>('/nichos/');
  }

  async createNicho(data: Partial<Nicho>): Promise<Nicho> {
    return this.request<Nicho>('/nichos/', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  // Ideias
  async getIdeias(params?: { status?: string; nicho_id?: string }): Promise<Ideia[]> {
    const searchParams = new URLSearchParams();
    if (params?.status) searchParams.set('status', params.status);
    if (params?.nicho_id) searchParams.set('nicho_id', params.nicho_id);
    const query = searchParams.toString();
    return this.request<Ideia[]>(`/ideias/${query ? `?${query}` : ''}`);
  }

  async createIdeia(data: { titulo: string; descricao?: string; nicho_id?: string }): Promise<Ideia> {
    return this.request<Ideia>('/ideias/', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  async aprovarIdeia(id: string): Promise<Ideia> {
    return this.request<Ideia>(`/ideias/${id}/aprovar`, { method: 'PATCH' });
  }

  async rejeitarIdeia(id: string): Promise<Ideia> {
    return this.request<Ideia>(`/ideias/${id}/rejeitar`, { method: 'PATCH' });
  }

  async gerarRoteiro(ideiaId: string): Promise<{ roteiro_id: string; titulo: string }> {
    return this.request(`/ideias/${ideiaId}/roteiro`, { method: 'POST' });
  }

  // Trends
  async getTrends(params?: { status?: string; nicho_id?: string }): Promise<Trend[]> {
    const searchParams = new URLSearchParams();
    if (params?.status) searchParams.set('status', params.status);
    if (params?.nicho_id) searchParams.set('nicho_id', params.nicho_id);
    const query = searchParams.toString();
    return this.request<Trend[]>(`/trends/${query ? `?${query}` : ''}`);
  }

  async coletarTrends(nichoId: string, termosAdicionais?: string[]): Promise<{ total_coletado: number }> {
    return this.request('/trends/coletar', {
      method: 'POST',
      body: JSON.stringify({ nicho_id: nichoId, termos_adicionais: termosAdicionais }),
    });
  }

  async aprovarTrend(id: string): Promise<Trend> {
    return this.request<Trend>(`/trends/${id}/aprovar`, { method: 'PATCH' });
  }

  async rejeitarTrend(id: string): Promise<Trend> {
    return this.request<Trend>(`/trends/${id}/rejeitar`, { method: 'PATCH' });
  }

  async gerarIdeiasFromTrend(trendId: string, numIdeias?: number): Promise<{ ideias_geradas: number }> {
    const params = numIdeias ? `?num_ideias=${numIdeias}` : '';
    return this.request(`/trends/${trendId}/gerar-ideias${params}`, { method: 'POST' });
  }

  // Roteiros
  async getRoteiros(params?: { status?: string }): Promise<Roteiro[]> {
    const searchParams = new URLSearchParams();
    if (params?.status) searchParams.set('status', params.status);
    const query = searchParams.toString();
    return this.request<Roteiro[]>(`/roteiros/${query ? `?${query}` : ''}`);
  }

  async getRoteiro(id: string): Promise<Roteiro> {
    return this.request<Roteiro>(`/roteiros/${id}`);
  }

  async aprovarRoteiro(id: string): Promise<Roteiro> {
    return this.request<Roteiro>(`/roteiros/${id}/aprovar`, { method: 'PATCH' });
  }

  async rejeitarRoteiro(id: string): Promise<Roteiro> {
    return this.request<Roteiro>(`/roteiros/${id}/rejeitar`, { method: 'PATCH' });
  }
}

export const api = new ApiClient(API_BASE);
