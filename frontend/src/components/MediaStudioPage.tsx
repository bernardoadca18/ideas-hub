import "../studio-media.css";
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { FolderOpen, Film, Search, ChevronRight } from "lucide-react";
import {
  mediaIndexerApi,
  type MediaProject,
  type SearchResult,
  type TimelineItem,
  type TimelineNote,
} from "../api/mediaIndexerClient";

function time(seconds: number) {
  const value = Math.max(0, Math.floor(seconds));
  return `${Math.floor(value / 60)}:${String(value % 60).padStart(2, "0")}`;
}

function QueryError({ error, retry }: { error: unknown; retry: () => void }) {
  return (
    <div role="alert" className="error">
      <p>Não foi possível concluir a consulta à biblioteca. Tente novamente.</p>
      {error instanceof Error && (
        <details>
          <summary>Detalhes da falha</summary>
          <p>{error.message}</p>
        </details>
      )}
      <button className="btn btn-secondary" onClick={retry}>
        Tentar novamente
      </button>
    </div>
  );
}

function NoteCard({ note }: { note: TimelineNote }) {
  return (
    <article className="studio-media-item">
      <div className="studio-media-meta">
        Nota #{note.order}
        {note.start_seconds != null && (
          <>
            {" "}
            · {time(note.start_seconds)}
            {note.end_seconds != null && ` – ${time(note.end_seconds)}`}
          </>
        )}
      </div>
      <p className="studio-media-text">{note.raw}</p>
      {note.description && (
        <p className="card-description">{note.description}</p>
      )}
      {!!note.tags?.length && (
        <p className="studio-media-meta">{note.tags.join(" · ")}</p>
      )}
    </article>
  );
}

function SegmentCard({ item }: { item: TimelineItem }) {
  return (
    <article className="studio-media-item">
      <div className="studio-media-meta">
        {time(item.start_seconds)} – {time(item.end_seconds)} · trecho #
        {item.sequence}
      </div>
      <p className="studio-media-text">
        {item.silent ? "[silêncio]" : item.text}
      </p>
    </article>
  );
}

function SessionDetailView({
  sessionId,
  selection,
}: {
  sessionId: string;
  selection?: SearchResult;
}) {
  const [view, setView] = useState<"timeline" | "notes">("timeline");
  const sessionQuery = useQuery({
    queryKey: ["media-session", sessionId],
    queryFn: () => mediaIndexerApi.getSession(sessionId),
  });
  const indexesQuery = useQuery({
    queryKey: ["temporal-indexes", sessionId],
    queryFn: () => mediaIndexerApi.listTemporalIndexes(sessionId),
    enabled: sessionQuery.data?.status === "ready" && !selection,
  });
  const indexId =
    selection?.temporal_index_id ||
    indexesQuery.data?.find((index) => index.status === "completed")?.id;
  const timelineQuery = useQuery({
    queryKey: [
      "semantic-timeline",
      sessionId,
      indexId,
      selection?.start_seconds,
      selection?.end_seconds,
    ],
    queryFn: () =>
      mediaIndexerApi.getSemanticTimeline(sessionId, {
        temporal_index_id: indexId!,
        ...(selection
          ? {
              start_seconds: selection.start_seconds,
              end_seconds: selection.end_seconds,
            }
          : {}),
      }),
    enabled: sessionQuery.data?.status === "ready" && !!indexId,
  });
  if (sessionQuery.isLoading)
    return (
      <div role="status" className="loading">
        Carregando sessão…
      </div>
    );
  if (sessionQuery.error)
    return (
      <QueryError
        error={sessionQuery.error}
        retry={() => void sessionQuery.refetch()}
      />
    );
  const session = sessionQuery.data;
  if (!session)
    return <div className="empty-state">Sessão não encontrada.</div>;
  return (
    <div className="studio-media-stack">
      <section className="card">
        <p className="eyebrow">Sessão selecionada</p>
        <h2>{session.label}</h2>
        <div className="studio-media-meta">
          <span>
            Estado:{" "}
            {session.status === "ready"
              ? "Pronta"
              : session.status === "processing"
                ? "Em processamento"
                : session.status}
          </span>
          <span>
            Criada em {new Date(session.created_at).toLocaleString("pt-BR")}
          </span>
          <span>{session.notes.length} notas</span>
          {session.notes_filename && <span>{session.notes_filename}</span>}
        </div>
        {selection && (
          <div className="studio-media-range">
            <p>
              Intervalo selecionado · {time(selection.start_seconds)} –{" "}
              {time(selection.end_seconds)}
            </p>
            <details>
              <summary>Referência do resultado</summary>
              <code>{selection.temporal_index_id}</code>
            </details>
          </div>
        )}
      </section>
      {session.status !== "ready" ? (
        <div className="empty-state">
          A timeline estará disponível quando a sessão estiver pronta.
        </div>
      ) : (
        <>
          {indexesQuery.error ? (
            <QueryError
              error={indexesQuery.error}
              retry={() => void indexesQuery.refetch()}
            />
          ) : timelineQuery.error ? (
            <QueryError
              error={timelineQuery.error}
              retry={() => void timelineQuery.refetch()}
            />
          ) : indexesQuery.isLoading || timelineQuery.isLoading ? (
            <div role="status" className="loading">
              Carregando timeline…
            </div>
          ) : !indexId ? (
            <div className="empty-state">
              Nenhum índice temporal concluído disponível para esta sessão.
            </div>
          ) : timelineQuery.data ? (
            <section className="studio-media-stack">
              <div className="studio-media-toolbar">
                <p className="studio-media-meta">
                  {timelineQuery.data.items.length} trechos ·{" "}
                  {timelineQuery.data.notes.length} notas neste recorte
                </p>
                <div className="actions">
                  <button
                    className="btn btn-secondary"
                    aria-pressed={view === "timeline"}
                    onClick={() => setView("timeline")}
                  >
                    Timeline
                  </button>
                  <button
                    className="btn btn-secondary"
                    aria-pressed={view === "notes"}
                    onClick={() => setView("notes")}
                  >
                    Notas
                  </button>
                </div>
              </div>
              {view === "timeline" ? (
                timelineQuery.data.items.length ? (
                  timelineQuery.data.items.map((item) => (
                    <SegmentCard key={item.temporal_segment_id} item={item} />
                  ))
                ) : (
                  <div className="empty-state">
                    Nenhum trecho neste intervalo.
                  </div>
                )
              ) : timelineQuery.data.notes.length ? (
                timelineQuery.data.notes.map((note) => (
                  <NoteCard key={note.id} note={note} />
                ))
              ) : (
                <div className="empty-state">Nenhuma nota neste recorte.</div>
              )}
            </section>
          ) : null}
        </>
      )}
    </div>
  );
}

function ProjectDetailView({ project }: { project: MediaProject }) {
  const sessionsQuery = useQuery({
    queryKey: ["media-sessions", project.id],
    queryFn: () => mediaIndexerApi.listSessions(project.id),
  });
  const [selectedSession, setSelectedSession] = useState<string | null>(null);
  if (selectedSession)
    return (
      <div className="studio-media-stack">
        <button
          className="btn btn-secondary studio-media-back"
          onClick={() => setSelectedSession(null)}
        >
          ← Voltar às sessões de {project.name}
        </button>
        <SessionDetailView key={selectedSession} sessionId={selectedSession} />
      </div>
    );
  return (
    <section className="studio-media-stack">
      <header>
        <p className="eyebrow">Projeto selecionado</p>
        <h2>{project.name}</h2>
        {project.description && (
          <p className="page-description">{project.description}</p>
        )}
      </header>
      {sessionsQuery.isLoading ? (
        <div role="status" className="loading">
          Carregando sessões…
        </div>
      ) : sessionsQuery.error ? (
        <QueryError
          error={sessionsQuery.error}
          retry={() => void sessionsQuery.refetch()}
        />
      ) : sessionsQuery.data?.length ? (
        sessionsQuery.data.map((session) => (
          <button
            key={session.id}
            onClick={() => setSelectedSession(session.id)}
            className="studio-media-item studio-media-session"
          >
            <Film size={20} aria-hidden="true" />
            <span>
              <strong>{session.label}</strong>
              <small>
                {new Date(session.created_at).toLocaleString("pt-BR")}
                {session.notes_filename && ` · ${session.notes_filename}`}
              </small>
            </span>
            <span className="studio-media-meta">
              {session.status === "ready"
                ? "Pronta"
                : session.status === "processing"
                  ? "Em processamento"
                  : session.status}
            </span>
            <ChevronRight size={16} aria-hidden="true" />
          </button>
        ))
      ) : (
        <div className="empty-state">Nenhuma sessão neste projeto.</div>
      )}
    </section>
  );
}

export function MediaStudioPage() {
  const [selectedProjectId, setSelectedProjectId] = useState<string | null>(
    null,
  );
  const [selectedResult, setSelectedResult] = useState<SearchResult | null>(
    null,
  );
  const [query, setQuery] = useState("");
  const [projectId, setProjectId] = useState("");
  const [submitted, setSubmitted] = useState<{
    query: string;
    projectId: string;
  } | null>(null);
  const projectsQuery = useQuery({
    queryKey: ["media-projects"],
    queryFn: () => mediaIndexerApi.listProjects(),
  });
  const searchQuery = useQuery({
    queryKey: ["media-search", submitted?.projectId, submitted?.query],
    queryFn: () =>
      mediaIndexerApi.searchProject(submitted!.projectId, submitted!.query),
    enabled: !!submitted,
  });
  const selectedProject = projectsQuery.data?.find(
    (project) => project.id === selectedProjectId,
  );
  if (selectedResult)
    return (
      <div className="studio-media-stack">
        <button
          className="btn btn-secondary studio-media-back"
          onClick={() => setSelectedResult(null)}
        >
          ← Voltar aos resultados
        </button>
        <SessionDetailView
          key={selectedResult.session_id}
          sessionId={selectedResult.session_id}
          selection={selectedResult}
        />
      </div>
    );
  if (selectedProject)
    return (
      <div className="studio-media-stack">
        <button
          className="btn btn-secondary studio-media-back"
          onClick={() => setSelectedProjectId(null)}
        >
          ← Voltar aos projetos
        </button>
        <ProjectDetailView key={selectedProject.id} project={selectedProject} />
      </div>
    );
  return (
    <div className="studio-media studio-media-stack">
      <header>
        <p className="eyebrow">Biblioteca editorial</p>
        <h1>Studio de mídia</h1>
        <p className="page-description">
          Explore sessões ou encontre trechos dentro de um projeto. Os
          resultados preservam o índice e o intervalo da busca.
        </p>
      </header>
      <form
        className="studio-media-search"
        onSubmit={(event) => {
          event.preventDefault();
          const text = query.trim();
          if (!projectId || text.length < 3) return;
          if (submitted?.query === text && submitted.projectId === projectId)
            void searchQuery.refetch();
          else setSubmitted({ query: text, projectId });
        }}
      >
        <label>
          Projeto da busca
          <select
            value={projectId}
            onChange={(event) => setProjectId(event.target.value)}
            required
          >
            <option value="">Selecione um projeto…</option>
            {projectsQuery.data?.map((project) => (
              <option key={project.id} value={project.id}>
                {project.name}
              </option>
            ))}
          </select>
        </label>
        <label>
          Descreva o trecho
          <input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            type="search"
            placeholder="Ex.: uma paisagem ao entardecer…"
            minLength={3}
            maxLength={2000}
            required
          />
        </label>
        <button
          className="btn btn-primary"
          disabled={
            !projectId || query.trim().length < 3 || searchQuery.isFetching
          }
        >
          <Search size={16} aria-hidden="true" />
          {searchQuery.isFetching ? "Buscando…" : "Buscar trechos"}
        </button>
      </form>
      {projectsQuery.error && (
        <QueryError
          error={projectsQuery.error}
          retry={() => void projectsQuery.refetch()}
        />
      )}
      {submitted && (
        <section className="studio-media-stack">
          <div className="studio-media-toolbar">
            <h2>Resultados para “{submitted.query}”</h2>
            <button
              className="btn btn-secondary"
              onClick={() => {
                setSubmitted(null);
                setQuery("");
              }}
            >
              Voltar à biblioteca
            </button>
          </div>
          {searchQuery.isFetching && (
            <p role="status" className="studio-media-meta">
              Consultando o projeto selecionado…
            </p>
          )}
          {searchQuery.error ? (
            <QueryError
              error={searchQuery.error}
              retry={() => void searchQuery.refetch()}
            />
          ) : searchQuery.data ? (
            searchQuery.data.length ? (
              searchQuery.data.map((result) => (
                <article
                  className="studio-media-item"
                  key={`${result.session_id}:${result.temporal_index_id}:${result.rank}`}
                >
                  <h3>{result.session_label || result.media_filename}</h3>
                  <p className="studio-media-meta">
                    {time(result.start_seconds)} – {time(result.end_seconds)} ·{" "}
                    {(result.score * 100).toFixed(1)}% de similaridade
                  </p>
                  <p className="studio-media-text">
                    {result.transcript_preview ||
                      "Este trecho não possui prévia de transcrição."}
                  </p>
                  <button
                    className="btn btn-secondary"
                    onClick={() => setSelectedResult(result)}
                  >
                    Abrir sessão neste intervalo →
                  </button>
                </article>
              ))
            ) : (
              <div className="empty-state">
                Nenhum resultado para esta descrição no projeto selecionado.
              </div>
            )
          ) : null}
        </section>
      )}
      {!submitted && (
        <section className="studio-media-stack">
          <h2>Projetos</h2>
          {projectsQuery.isLoading ? (
            <div className="loading" role="status">
              Carregando projetos…
            </div>
          ) : (
            !projectsQuery.error && (
              <div className="studio-media-projects">
                {projectsQuery.data?.map((project) => (
                  <button
                    className="card studio-media-project"
                    key={project.id}
                    onClick={() => setSelectedProjectId(project.id)}
                  >
                    <FolderOpen size={20} aria-hidden="true" />
                    <strong>{project.name}</strong>
                    {project.description && (
                      <p className="card-description">{project.description}</p>
                    )}
                    <small>Abrir sessões →</small>
                  </button>
                ))}
                {projectsQuery.data?.length === 0 && (
                  <div className="empty-state">
                    Nenhum projeto encontrado. Crie um projeto na Biblioteca
                    audiovisual.
                  </div>
                )}
              </div>
            )
          )}
        </section>
      )}
    </div>
  );
}
