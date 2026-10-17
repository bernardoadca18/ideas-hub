/**
 * Media Indexer API client for Ideas Hub.
 * Provides typed access to Media Indexer endpoints for Phase 3 integration.
 */

const MEDIA_INDEXER_BASE =
  import.meta.env?.VITE_MEDIA_INDEXER_URL || "http://localhost:8001";

// Media Indexer Types (matching backend schemas)

export interface MediaProject {
  id: string;
  name: string;
  description: string | null;
  created_at: string;
}

export interface MediaNote {
  id: string;
  order: number;
  raw: string;
  start_seconds: number | null;
  end_seconds: number | null;
  description: string | null;
  tags: string[] | null;
}

export interface MediaSessionSummary {
  id: string;
  label: string;
  status: string;
  notes_filename: string | null;
  created_at: string;
}

export interface MediaSession {
  id: string;
  label: string;
  status: string;
  notes_filename: string | null;
  raw_notes: string | null;
  notes: MediaNote[];
  created_at: string;
}

export interface TemporalIndex {
  id: string;
  session_id: string;
  transcription_id: string;
  visual_index_id: string;
  status: string;
  configuration_fingerprint: string;
  created_at: string;
}

export interface TimelineTranscriptRef {
  id: string;
  sequence: number;
  start_seconds: number;
  end_seconds: number;
}

export interface TimelineSceneRef {
  id: string;
  sequence: number;
  start_seconds: number;
  end_seconds: number;
}

export interface TimelineFrameRef {
  id: string;
  kind: string;
  timestamp_seconds: number;
  storage_uri: string;
  mime_type: string;
  width: number | null;
  height: number | null;
  metadata: Record<string, unknown> | null;
}

export interface TimelineEvidence {
  transcript_segments: TimelineTranscriptRef[];
  scenes: TimelineSceneRef[];
  frames: TimelineFrameRef[];
}

export interface TimelineItem {
  temporal_segment_id: string;
  sequence: number;
  start_seconds: number;
  end_seconds: number;
  duration_seconds: number;
  text: string;
  metadata: Record<string, unknown> | null;
  silent: boolean;
  evidence: TimelineEvidence;
  matched_note_ids: string[];
}

export interface TimelineSelectedAlignment {
  candidate_alignment_id: string;
  retrieval_candidate_id: string;
  retrieval_rank: number;
  start_seconds: number;
  end_seconds: number;
  confidence: number;
  reasoning_summary: string | null;
  temporal_segment_ids: string[];
}

export interface TimelineNote {
  id: string;
  order: number;
  raw: string;
  start_seconds: number | null;
  end_seconds: number | null;
  description: string | null;
  tags: string[] | null;
  alignment_status: string;
  selected_alignment: TimelineSelectedAlignment | null;
}

export interface TimelineRange {
  start_seconds: number | null;
  end_seconds: number | null;
  semantics: string;
}

export interface SemanticTimeline {
  provenance: {
    project_id: string;
    session_id: string;
    media_id: string;
    temporal_index_id: string;
  };
  range: TimelineRange;
  items: TimelineItem[];
  notes: TimelineNote[];
  total: number;
  offset: number;
  limit: number;
}

export interface SearchResult {
  session_id: string;
  media_id: string;
  start_seconds: number;
  end_seconds: number;
  duration_seconds: number;
  score: number;
  rank: number;
  session_label: string;
  media_filename: string;
  temporal_index_id: string;
  retrieval_candidate_id: string | null;
  transcript_preview: string | null;
  matched_note_ids: string[];
  provenance: Record<string, unknown>;
}

async function fetchJSON<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${MEDIA_INDEXER_BASE}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...options?.headers,
    },
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`Media Indexer Error ${res.status}: ${text}`);
  }
  return res.json();
}

export const mediaIndexerApi = {
  // Projects
  listProjects: (offset = 0, limit = 50) =>
    fetchJSON<MediaProject[]>(`/projects?offset=${offset}&limit=${limit}`),

  getProject: (id: string) => fetchJSON<MediaProject>(`/projects/${id}`),

  // Sessions
  listSessions: (projectId: string) =>
    fetchJSON<MediaSessionSummary[]>(`/projects/${projectId}/sessions`),

  getSession: (sessionId: string) =>
    fetchJSON<MediaSession>(`/sessions/${sessionId}`),

  // Temporal Indexes
  listTemporalIndexes: (sessionId: string) =>
    fetchJSON<TemporalIndex[]>(`/sessions/${sessionId}/temporal-indexes`),

  // Semantic Timeline
  getSemanticTimeline: (
    sessionId: string,
    params: {
      temporal_index_id: string;
      alignment_run_id?: string;
      start_seconds?: number;
      end_seconds?: number;
      offset?: number;
      limit?: number;
    },
  ) => {
    const searchParams = new URLSearchParams();
    searchParams.set("temporal_index_id", params.temporal_index_id);
    if (params.alignment_run_id)
      searchParams.set("alignment_run_id", params.alignment_run_id);
    if (params.start_seconds !== undefined)
      searchParams.set("start_seconds", String(params.start_seconds));
    if (params.end_seconds !== undefined)
      searchParams.set("end_seconds", String(params.end_seconds));
    if (params.offset !== undefined)
      searchParams.set("offset", String(params.offset));
    if (params.limit !== undefined)
      searchParams.set("limit", String(params.limit));
    return fetchJSON<SemanticTimeline>(
      `/sessions/${sessionId}/semantic-timeline?${searchParams}`,
    );
  },

  // Search
  searchProject: (projectId: string, query: string, limit = 20) =>
    fetchJSON<{ results: SearchResult[] }>(
      `/media-search/projects/${projectId}`,
      {
        method: "POST",
        body: JSON.stringify({ query, max_results: limit }),
      },
    ).then((r) => r.results),

  searchSession: (sessionId: string, query: string, limit = 20) =>
    fetchJSON<{ results: SearchResult[] }>(
      `/media-search/sessions/${sessionId}`,
      {
        method: "POST",
        body: JSON.stringify({ query, max_results: limit }),
      },
    ).then((r) => r.results),
};
