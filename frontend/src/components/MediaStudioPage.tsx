import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { FolderOpen, Film, Clock, FileText, Search, Loader, ChevronRight } from 'lucide-react';
import { mediaIndexerApi, type MediaProject, type MediaSessionSummary, type SemanticTimeline, type TimelineNote, type TimelineItem } from '../api/mediaIndexerClient';

function formatSeconds(seconds: number): string {
  const mins = Math.floor(seconds / 60);
  const secs = Math.floor(seconds % 60);
  return `${mins}:${secs.toString().padStart(2, '0')}`;
}

function TimelineNoteCard({ note, onClick }: { note: TimelineNote; onClick?: () => void }) {
  const hasTimestamp = note.start_seconds !== null;

  return (
    <div
      onClick={onClick}
      className="p-3 rounded-lg border border-slate-600 bg-slate-800 hover:bg-slate-750 cursor-pointer transition-all"
    >
      <div className="flex items-center gap-2 text-xs text-slate-500 mb-1">
        <span>#{note.order}</span>
        {hasTimestamp && (
          <>
            <Clock className="w-3 h-3" />
            <span>{formatSeconds(note.start_seconds!)}</span>
            {note.end_seconds && <span>- {formatSeconds(note.end_seconds)}</span>}
          </>
        )}
      </div>
      <p className="text-sm text-slate-300 line-clamp-3">{note.raw}</p>
      {note.description && (
        <p className="text-xs text-slate-400 mt-1">{note.description}</p>
      )}
      {note.tags && note.tags.length > 0 && (
        <div className="flex gap-1 mt-2 flex-wrap">
          {note.tags.map((tag, i) => (
            <span key={i} className="px-2 py-0.5 bg-slate-700 rounded text-xs text-slate-400">
              {tag}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}

function TimelineSegmentCard({ item }: { item: TimelineItem }) {
  return (
    <div className={`p-3 rounded-lg border ${item.silent ? 'bg-slate-850 border-slate-700' : 'bg-slate-800 border-slate-600'}`}>
      <div className="flex items-center gap-3 mb-2">
        <div className="text-xs text-slate-500">
          <span className="font-mono">{formatSeconds(item.start_seconds)}</span>
          <span className="mx-1">-</span>
          <span className="font-mono">{formatSeconds(item.end_seconds)}</span>
        </div>
        <span className="text-xs text-slate-600">#{item.sequence}</span>
      </div>
      <p className={`text-sm ${item.silent ? 'text-slate-600 italic' : 'text-slate-300'}`}>
        {item.silent ? '[silent]' : item.text}
      </p>
    </div>
  );
}

function SessionDetailView({ projectId, sessionId }: { projectId: string; sessionId: string }) {
  const { data: session, isLoading: loadingSession } = useQuery({
    queryKey: ['media-session', sessionId],
    queryFn: () => mediaIndexerApi.getSession(sessionId),
  });

  const { data: temporalIndexes } = useQuery({
    queryKey: ['temporal-indexes', sessionId],
    queryFn: () => mediaIndexerApi.listTemporalIndexes(sessionId),
    enabled: !!session && session.status === 'ready',
  });

  const completedIndex = temporalIndexes?.find(ti => ti.status === 'completed');

  const { data: timeline, isLoading: loadingTimeline } = useQuery({
    queryKey: ['semantic-timeline', sessionId, completedIndex?.id],
    queryFn: () => mediaIndexerApi.getSemanticTimeline(sessionId, {
      temporal_index_id: completedIndex!.id,
    }),
    enabled: !!completedIndex,
  });

  const [viewMode, setViewMode] = useState<'timeline' | 'notes'>('timeline');

  if (loadingSession) {
    return (
      <div className="flex items-center justify-center py-20">
        <Loader className="w-6 h-6 animate-spin text-slate-500" />
      </div>
    );
  }

  if (!session) {
    return <div className="text-center py-20 text-red-400">Session not found</div>;
  }

  return (
    <div className="space-y-6">
      <div className="bg-slate-800 border border-slate-700 rounded-lg p-6">
        <h2 className="text-xl font-bold mb-4">{session.label}</h2>
        <div className="grid grid-cols-2 gap-4 text-sm">
          <div>
            <span className="text-slate-500">Status:</span>
            <span className="ml-2 text-slate-300">{session.status}</span>
          </div>
          <div>
            <span className="text-slate-500">Created:</span>
            <span className="ml-2 text-slate-300">{new Date(session.created_at).toLocaleString()}</span>
          </div>
          <div>
            <span className="text-slate-500">Notes:</span>
            <span className="ml-2 text-slate-300">{session.notes.length} notes</span>
          </div>
          {session.notes_filename && (
            <div>
              <span className="text-slate-500">File:</span>
              <span className="ml-2 text-slate-300">{session.notes_filename}</span>
            </div>
          )}
        </div>
      </div>

      {session.status === 'ready' && (
        <>
          {loadingTimeline ? (
            <div className="flex items-center justify-center py-10">
              <Loader className="w-6 h-6 animate-spin text-slate-500" />
            </div>
          ) : temporalIndexes && temporalIndexes.length === 0 ? (
            <div className="p-4 bg-slate-800/50 rounded-lg border border-dashed border-slate-700">
              <p className="text-sm text-slate-500">No temporal indexes available.</p>
            </div>
          ) : !completedIndex ? (
            <div className="p-4 bg-slate-800/50 rounded-lg border border-yellow-500/50">
              <p className="text-sm text-slate-400">Temporal index processing in progress...</p>
            </div>
          ) : timeline ? (
            <div className="space-y-4">
              <div className="flex items-center justify-between">
                <div className="text-sm text-slate-500">
                  {timeline.items.length} segments • {timeline.notes.length} notes
                </div>
                <div className="flex gap-2">
                  <button
                    onClick={() => setViewMode('timeline')}
                    className={`px-3 py-1 text-sm rounded ${
                      viewMode === 'timeline' ? 'bg-blue-600 text-white' : 'bg-slate-700 text-slate-400'
                    }`}
                  >
                    Timeline
                  </button>
                  <button
                    onClick={() => setViewMode('notes')}
                    className={`px-3 py-1 text-sm rounded ${
                      viewMode === 'notes' ? 'bg-blue-600 text-white' : 'bg-slate-700 text-slate-400'
                    }`}
                  >
                    Notes
                  </button>
                </div>
              </div>

              {viewMode === 'timeline' ? (
                <div className="space-y-2">
                  {timeline.items.map((item) => (
                    <TimelineSegmentCard key={item.temporal_segment_id} item={item} />
                  ))}
                </div>
              ) : (
                <div className="grid gap-3 md:grid-cols-2 lg:grid-cols-3">
                  {timeline.notes.map((note) => (
                    <TimelineNoteCard key={note.id} note={note} />
                  ))}
                </div>
              )}
            </div>
          ) : null}
        </>
      )}

      {session.status !== 'ready' && (
        <div className="p-4 bg-slate-800/50 rounded-lg border border-yellow-500/50">
          <p className="text-sm text-slate-400">Session is {session.status}. Timeline will be available when ready.</p>
        </div>
      )}
    </div>
  );
}

function ProjectDetailView({ project }: { project: MediaProject }) {
  const { data: sessions, isLoading } = useQuery({
    queryKey: ['media-sessions', project.id],
    queryFn: () => mediaIndexerApi.listSessions(project.id),
  });

  const [selectedSessionId, setSelectedSessionId] = useState<string | null>(null);

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-10">
        <Loader className="w-6 h-6 animate-spin text-slate-500" />
      </div>
    );
  }

  if (selectedSessionId) {
    return (
      <div>
        <button
          onClick={() => setSelectedSessionId(null)}
          className="flex items-center gap-2 text-slate-400 hover:text-slate-200 mb-4"
        >
          <ChevronRight className="w-4 h-4 rotate-180" />
          Back to sessions
        </button>
        <SessionDetailView projectId={project.id} sessionId={selectedSessionId} />
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-xl font-bold">{project.name}</h2>
        <span className="text-sm text-slate-500">
          {sessions?.length || 0} sessions
        </span>
      </div>

      {project.description && (
        <p className="text-sm text-slate-400">{project.description}</p>
      )}

      <div className="space-y-2">
        {sessions?.map((session) => (
          <button
            key={session.id}
            onClick={() => setSelectedSessionId(session.id)}
            className="w-full p-4 bg-slate-800 border border-slate-700 rounded-lg hover:bg-slate-750 text-left transition-all"
          >
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-3">
                <Film className="w-5 h-5 text-slate-500" />
                <div>
                  <div className="font-medium text-slate-200">{session.label}</div>
                  <div className="text-xs text-slate-500">
                    {new Date(session.created_at).toLocaleString()}
                  </div>
                </div>
              </div>
              <div className="flex items-center gap-2">
                {session.notes_filename && (
                  <FileText className="w-4 h-4 text-slate-500" />
                )}
                <span className={`text-xs px-2 py-1 rounded ${
                  session.status === 'ready' ? 'bg-green-500/20 text-green-400' :
                  session.status === 'processing' ? 'bg-yellow-500/20 text-yellow-400' :
                  'bg-slate-700 text-slate-400'
                }`}>
                  {session.status}
                </span>
              </div>
            </div>
          </button>
        ))}

        {sessions && sessions.length === 0 && (
          <div className="text-center py-10 text-slate-500">
            No sessions in this project
          </div>
        )}
      </div>
    </div>
  );
}

export function MediaStudioPage() {
  const [selectedProjectId, setSelectedProjectId] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState('');

  const { data: projects, isLoading } = useQuery({
    queryKey: ['media-projects'],
    queryFn: () => mediaIndexerApi.listProjects(),
  });

  const { data: searchResults, isLoading: searching } = useQuery({
    queryKey: ['media-search', searchQuery],
    queryFn: () => mediaIndexerApi.searchGlobal(searchQuery),
    enabled: searchQuery.length >= 3,
  });

  const selectedProject = projects?.find(p => p.id === selectedProjectId);

  if (selectedProject) {
    return (
      <div>
        <button
          onClick={() => setSelectedProjectId(null)}
          className="flex items-center gap-2 text-slate-400 hover:text-slate-200 mb-4"
        >
          <ChevronRight className="w-4 h-4 rotate-180" />
          Back to projects
        </button>
        <ProjectDetailView project={selectedProject} />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Media Studio</h1>
        <div className="relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-500" />
          <input
            type="text"
            placeholder="Search footage..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="pl-10 pr-4 py-2 bg-slate-800 border border-slate-700 rounded-lg text-sm focus:outline-none focus:border-blue-500 w-64"
          />
        </div>
      </div>

      {searchQuery.length >= 3 ? (
        <div className="space-y-4">
          <h2 className="text-lg font-semibold">Search Results</h2>
          {searching ? (
            <div className="flex items-center justify-center py-10">
              <Loader className="w-6 h-6 animate-spin text-slate-500" />
            </div>
          ) : searchResults && searchResults.length > 0 ? (
            <div className="space-y-2">
              {searchResults.map((result, i) => (
                <div key={i} className="p-3 bg-slate-800 border border-slate-700 rounded-lg">
                  <p className="text-sm text-slate-300">{result.transcript_preview}</p>
                  <div className="text-xs text-slate-500 mt-1">
                    {formatSeconds(result.start_seconds)} - {formatSeconds(result.end_seconds)}
                    <span className="ml-2">Similarity: {(result.score * 100).toFixed(1)}%</span>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="text-center py-10 text-slate-500">No results found</div>
          )}
        </div>
      ) : (
        <div className="space-y-4">
          <h2 className="text-lg font-semibold">Projects</h2>
          {isLoading ? (
            <div className="flex items-center justify-center py-10">
              <Loader className="w-6 h-6 animate-spin text-slate-500" />
            </div>
          ) : (
            <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
              {projects?.map((project) => (
                <button
                  key={project.id}
                  onClick={() => setSelectedProjectId(project.id)}
                  className="p-4 bg-slate-800 border border-slate-700 rounded-lg hover:bg-slate-750 text-left transition-all"
                >
                  <div className="flex items-center gap-3 mb-2">
                    <FolderOpen className="w-5 h-5 text-blue-400" />
                    <span className="font-medium text-slate-200">{project.name}</span>
                  </div>
                  {project.description && (
                    <p className="text-sm text-slate-400 line-clamp-2">{project.description}</p>
                  )}
                  <div className="text-xs text-slate-500 mt-2">
                    Created {new Date(project.created_at).toLocaleDateString()}
                  </div>
                </button>
              ))}

              {projects && projects.length === 0 && (
                <div className="col-span-full text-center py-10 text-slate-500">
                  No projects found. Create one in Media Indexer first.
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
