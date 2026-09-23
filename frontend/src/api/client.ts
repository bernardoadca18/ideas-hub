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
  perfil_producao: string;
}

export type DurationMode = 'explicit_target' | 'profile_default' | 'content_driven';

export interface ProductionProfile {
  capabilities: {
    delivery_mode: 'rendered_video' | 'manual_edit_package';
    visual_mode: 'none' | 'semantic_match' | 'background_fill' | 'storyboard';
    requires_media_scope: boolean;
    caption_policy: 'burned_in' | 'none';
    render_profile: string | null;
    version: string;
  };
  id: string;
  name: string;
  description: string;
  duration_policy: {
    preferred_min_seconds: number | null;
    preferred_max_seconds: number | null;
    default_target_seconds: number | null;
    content_driven_allowed: boolean;
    max_practical_duration_seconds: number;
  };
  generation_strategy: string;
  research_strategy: string;
  model_routing_policy: string;
  long_form_supported: boolean;
}

export interface GenerationRun {
  id: string;
  ideia_id: string;
  roteiro_id?: string;
  parent_roteiro_id?: string;
  generation_intent: string;
  revision_feedback?: string;
  status: string;
  phase: string;
  generation_strategy: string;
  production_profile: string;
  duration_mode: DurationMode;
  duration_target_source: string;
  target_duration_seconds: number | null;
  target_words: number | null;
  total_sections: number;
  completed_sections: number;
  plan: Record<string, unknown>;
  call_usage: Record<string, unknown>;
  error_category?: string;
  error_message?: string;
}

export interface GenerationPreview {
  duration_intent: { mode: DurationMode; source: string; target_seconds: number | null };
  strategy: string;
  strategy_version: string;
  strategy_identity: string;
  target_words: number | null;
  chapter_count: number;
  section_count: number;
  estimated_llm_calls: number;
  calibration_identity: string;
  content_capacity: {
    status: string;
    estimated_supported_words: number;
    target_words: number | null;
    ratio: number | null;
    advisory_only: boolean;
  };
}

export type ContentLocale = 'pt-BR' | 'en-US';

export interface Ideia {
  content_locale: ContentLocale;
  id: string;
  nicho_id?: string;
  origem: string;
  titulo: string;
  descricao_breve?: string;
  author_briefing?: string;
  target_duration_seconds?: number;
  duration_mode?: DurationMode;
  duration_target_source?: string;
  author_briefing_identity: string;
  perfil_producao?: string;
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
    content_locale?: ContentLocale;
    titulo: string;
    duracao_total_segundos: number;
    blocos: BlocoNarrativo[];
    tags: string[];
    referencias?: string[];
    justificativa_llm?: string;
    prompt_trace?: Record<string, unknown>;
    duration_contract?: DurationContract;
    editorial_quality?: Record<string, unknown>;
    editorial_review?: EditorialReview;
    evidence_provenance?: EvidenceProvenance;
    section_audits?: Record<string, SectionAudit | null>;
    global_critic?: { summary?: string; issues?: EditorialIssue[] };
    generation_run_id?: string;
    media_context?: { media_project_id: string; media_session_ids: string[] };
    visual_readiness?: Record<string, unknown>;
    manual_import?: {
      schema_version: 'neovids_manual_script_v1';
      source_filename: string;
      normalized_payload_sha256: string;
      source: 'manual_file_import';
    };
    manual_draft?: {
      adapter_version: 'plain_text_manual_draft_v1';
      source: 'manual_plain_text';
      original_text_sha256: string;
      original_char_count: number;
    };
  };
  status: string;
  author_briefing_snapshot?: string;
  author_briefing_identity?: string;
  author_briefing_changed_since_creation?: boolean;
  parent_roteiro_id?: string;
  revision_kind: string;
  revision_feedback?: string;
  criado_em: string;
  atualizado_em: string;
}

export interface EditorialIssue {
  section_key?: string;
  category: string;
  severity: 'warning' | 'revision_required' | 'blocking';
  actionable_feedback: string;
  claim_ref?: string;
  excerpt?: string;
}

export interface SectionAudit {
  revision_required?: boolean;
  issues?: EditorialIssue[];
  actual_claim_refs?: string[];
  actual_beats_covered?: string[];
  actual_summary?: string;
}

export interface EditorialReview {
  audit_status: string;
  editorial_status: string;
  factuality_status: string;
  approval_blocked: boolean;
  global_summary?: string;
  global_issues?: EditorialIssue[];
  section_issues?: Record<string, EditorialIssue[]>;
  unsupported_claim_count?: number;
}

export interface EvidenceProvenance {
  version?: string;
  generation_run_id?: string;
  sources?: Array<{
    source_id?: string;
    title?: string;
    url?: string;
    domain?: string;
    source_trust?: string;
  }>;
  claim_ledger?: Array<{
    id: string;
    summary: string;
    source_trust?: string;
    claim_status?: string;
    confidence?: number;
    source_refs?: string[];
    qualification?: string;
  }>;
  section_claim_usage?: Record<string, string[]>;
}

export interface BlocoNarrativo {
  tipo: string;
  duracao_segundos: number;
  conteudo: string;
  dicas_visual?: string;
  dicas_audio?: string;
  visual_queries?: Array<Record<string, unknown>>;
  purpose?: string;
  beats?: Array<Record<string, unknown>>;
  planned_beats?: Array<Record<string, unknown>>;
  claims?: Array<Record<string, unknown>>;
  audio_intent?: Record<string, unknown>;
}

export interface DurationContract {
  target_duration_seconds: number | null;
  predicted_duration_seconds: number;
  actual_narration_duration_seconds: number | null;
  delta_seconds: number | null;
  ratio: number | null;
  status: string;
  revision_required: boolean;
  speakable_words: number;
  speakable_chars: number;
  target_words: number | null;
  calibration: { identity: string; fallback: boolean; sample_count: number };
  sections: Array<{
    index: number;
    type: string;
    target_duration_seconds: number | null;
    target_words: number | null;
    actual_words: number;
    predicted_duration_seconds: number;
    status: string;
  }>;
}

export interface ScriptEditRevision {
  titulo: string;
  blocos: Array<Pick<BlocoNarrativo, 'tipo' | 'duracao_segundos' | 'conteudo' | 'dicas_visual' | 'dicas_audio'>>;
  tags: string[];
  referencias?: string[];
  edit_summary?: string;
}

export interface ManualScriptDocumentV1 {
  schema: 'neovids_manual_script_v1';
  title: string;
  blocks: Array<{
    type: string;
    text: string;
    duration_seconds?: number;
  }>;
  tags?: string[];
  references?: string[];
  media?: {
    project_id: string;
    session_ids?: string[];
  };
}

export interface ManualScriptImportPreview {
  importable: boolean;
  schema_version: 'neovids_manual_script_v1';
  idea: {
    id: string;
    title: string;
    niche?: string;
    production_profile: string;
    target_duration_seconds: number | null;
    duration_mode: string;
  };
  normalized: {
    title: string;
    block_count: number;
    word_count: number;
    duration_total_seconds: number;
    normalized_payload_sha256: string;
    blocks: Array<{
      index: number;
      type: string;
      word_count: number;
      duration_seconds: number;
      duration_source: 'provided' | 'estimated';
    }>;
  };
  duration: DurationContract;
  media_scope: {
    provided: boolean;
    project_id: string | null;
    session_ids: string[];
    scope: 'not_provided' | 'whole_project' | 'selected_sessions';
  };
  visual: {
    status: string;
    message: string;
    current_readiness: Record<string, unknown>;
  };
  production_readiness: {
    expected_status_after_import: string;
    diagnostic: Record<string, unknown>;
  };
  warnings: string[];
  errors: string[];
}

export interface ManualScriptImportResult {
  created: boolean;
  duplicate: boolean;
  normalized_payload_sha256: string;
  draft: Roteiro;
  current_revision: Roteiro;
  media_binding_applied: boolean;
}

export interface ManualDraftImprovementRunResult {
  created: boolean;
  duplicate: boolean;
  draft: Roteiro;
  run: GenerationRun;
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
      const raw = await response.text();
      let detail = raw;
      try {
        const parsed: unknown = JSON.parse(raw);
        if (
          typeof parsed === 'object' &&
          parsed !== null &&
          'detail' in parsed &&
          typeof parsed.detail === 'string'
        ) {
          detail = parsed.detail;
        }
      } catch {
        // Preserve non-JSON backend responses verbatim.
      }
      throw new Error(`API Error ${response.status}: ${detail}`);
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

  async getProductionProfiles(): Promise<ProductionProfile[]> {
    return this.request<ProductionProfile[]>('/editorial/production-profiles');
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

  async createIdeia(data: { content_locale?: ContentLocale; titulo: string; descricao?: string; author_briefing?: string; duration_mode: DurationMode; target_duration_seconds?: number; nicho_id?: string }): Promise<Ideia> {
    return this.request<Ideia>('/ideias/', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  async updateIdeia(id: string, data: { author_briefing?: string | null; duration_mode?: DurationMode; target_duration_seconds?: number | null }): Promise<Ideia> {
    return this.request<Ideia>(`/ideias/${id}`, {
      method: 'PUT',
      body: JSON.stringify(data),
    });
  }

  async aprovarIdeia(id: string): Promise<Ideia> {
    return this.request<Ideia>(`/ideias/${id}/aprovar`, { method: 'PATCH' });
  }

  async rejeitarIdeia(id: string): Promise<Ideia> {
    return this.request<Ideia>(`/ideias/${id}/rejeitar`, { method: 'PATCH' });
  }

  async gerarRoteiro(ideiaId: string): Promise<GenerationRun> {
    return this.request<GenerationRun>(`/ideias/${ideiaId}/roteiro`, { method: 'POST' });
  }

  async startGenerationRun(ideiaId: string, idempotencyKey: string): Promise<GenerationRun> {
    return this.request<GenerationRun>(`/ideias/${ideiaId}/generation-runs`, {
      method: 'POST',
      body: JSON.stringify({ idempotency_key: idempotencyKey }),
    });
  }

  async startManualDraftImprovement(data: {
    ideia_id: string;
    draft_text: string;
    content_locale?: ContentLocale;
    feedback?: string;
    idempotency_key: string;
    model_strategy?: 'flash_only' | 'standard' | 'hybrid' | 'strong';
  }): Promise<ManualDraftImprovementRunResult> {
    return this.request<ManualDraftImprovementRunResult>(
      `/ideias/${data.ideia_id}/manual-draft-improvement-runs`,
      {
        method: 'POST',
        body: JSON.stringify({
          draft_text: data.draft_text,
          content_locale: data.content_locale,
          ...(data.feedback ? { feedback: data.feedback } : {}),
          idempotency_key: data.idempotency_key,
          model_strategy: data.model_strategy || 'standard',
        }),
      },
    );
  }

  async getGenerationRun(runId: string, signal?: AbortSignal): Promise<GenerationRun> {
    return this.request<GenerationRun>(`/generation-runs/${runId}`, { signal });
  }

  async getGenerationRuns(): Promise<GenerationRun[]> {
    return this.request<GenerationRun[]>('/generation-runs?limit=100');
  }

  async getGenerationPreview(data: {
    content_locale?: ContentLocale;
    production_profile: string;
    duration_mode: DurationMode;
    target_duration_seconds?: number;
    evidence_chars: number;
  }): Promise<GenerationPreview> {
    return this.request<GenerationPreview>('/editorial/generation-preview', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  async startGameGeneration(data: {
    content_locale?: ContentLocale;
    titulo_provisorio: string;
    anotacoes: string;
    nome_jogo?: string;
    author_briefing?: string;
    duration_mode: DurationMode;
    target_duration_seconds?: number;
    usar_grounding: boolean;
    idempotency_key: string;
    model_strategy: 'flash_only' | 'standard' | 'hybrid' | 'strong';
  }): Promise<GenerationRun> {
    return this.request<GenerationRun>('/editorial/game-analysis/generation-runs', {
      method: 'POST',
      body: JSON.stringify(data),
    });
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


  async editarRoteiroComoRevisao(id: string, data: ScriptEditRevision): Promise<Roteiro> {
    return this.request<Roteiro>(`/roteiros/${id}/revisoes/editar`, {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  async startRevisionGenerationRun(id: string, feedback: string | undefined, idempotencyKey: string): Promise<GenerationRun> {
    return this.request<GenerationRun>(`/roteiros/${id}/generation-runs`, {
      method: 'POST',
      body: JSON.stringify({ ...(feedback ? { feedback } : {}), idempotency_key: idempotencyKey }),
    });
  }

  async startRoteiroAudit(id: string, idempotencyKey: string): Promise<GenerationRun> {
    return this.request<GenerationRun>(`/roteiros/${id}/audit`, {
      method: 'POST',
      body: JSON.stringify({ idempotency_key: idempotencyKey }),
    });
  }

  async createManualDraft(data: {
    content_locale?: ContentLocale;
    ideia_id: string;
    titulo: string;
    blocos: Array<{
      tipo: string;
      duracao_segundos: number;
      conteudo: string;
      dicas_visual?: string;
      dicas_audio?: string;
    }>;
    tags?: string[];
    referencias?: string[];
  }): Promise<Roteiro> {
    const duracao_total_segundos = data.blocos.reduce((sum, b) => sum + b.duracao_segundos, 0);
    return this.request<Roteiro>('/roteiros/', {
      method: 'POST',
      body: JSON.stringify({
        ideia_id: data.ideia_id,
        estrutura: {
          content_locale: data.content_locale,
          titulo: data.titulo,
          duracao_total_segundos,
          blocos: data.blocos.map(b => ({
            tipo: b.tipo,
            duracao_segundos: b.duracao_segundos,
            conteudo: b.conteudo,
            dicas_visual: b.dicas_visual || null,
            dicas_audio: b.dicas_audio || null,
            visual_queries: [],
            purpose: null,
            beats: [],
            planned_beats: [],
            claims: [],
            audio_intent: null,
          })),
          tags: data.tags || [],
          referencias: data.referencias || null,
        },
      }),
    });
  }

  async previewManualScriptImport(data: {
    ideia_id: string;
    source_filename: string;
    content_locale?: ContentLocale;
    script: ManualScriptDocumentV1;
  }): Promise<ManualScriptImportPreview> {
    return this.request<ManualScriptImportPreview>('/roteiros/importar/preview', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  async importManualScript(data: {
    ideia_id: string;
    source_filename: string;
    content_locale?: ContentLocale;
    script: ManualScriptDocumentV1;
  }): Promise<ManualScriptImportResult> {
    return this.request<ManualScriptImportResult>('/roteiros/importar', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }
}

export const api = new ApiClient(API_BASE);
