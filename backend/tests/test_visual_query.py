"""
Tests for VisualQuery domain model and provenance canonicalization.

Tests cover:
- VisualQuery dataclass creation and serialization
- Provenance canonicalization in AnaliseJogosService
- Backward compatibility for old roteiros without visual_queries
- VisualQueryIntent and VisualQueryImportance enums
"""

from uuid import UUID, uuid4

import pytest
from app.agents.analise_jogos import (
    AnaliseJogosService,
    format_media_context_for_prompt,
)
from app.agents.roteirista import BlocoNarrativo, RoteiroEstruturado
from app.schemas.media_indexer import (
    GameAnalysisMediaContext,
    MediaIndexerAlignment,
    MediaIndexerNote,
    MediaIndexerTimelineNote,
    MediaIndexerTimelineSession,
)
from app.schemas.visual_query import (
    VisualQuery,
    VisualQueryImportance,
    VisualQueryIntent,
)


@pytest.fixture
def note_id():
    """Sample note ID."""
    return uuid4()


@pytest.fixture
def session_id():
    """Sample session ID."""
    return uuid4()


@pytest.fixture
def project_id():
    """Sample project ID."""
    return uuid4()


class TestVisualQueryDataclass:
    """Tests for VisualQuery dataclass."""

    def test_create_visual_query_with_defaults(self):
        """Test creating a VisualQuery with default values."""
        vq = VisualQuery()

        assert isinstance(vq.id, UUID)
        assert vq.order == 0
        assert vq.intent == VisualQueryIntent.ILLUSTRATION.value
        assert vq.query == ""
        assert vq.narration_excerpt is None
        assert vq.importance == VisualQueryImportance.PREFERRED.value
        assert vq.source_note_id is None
        assert vq.preferred_session_id is None
        assert vq.preferred_start_seconds is None
        assert vq.preferred_end_seconds is None
        assert vq.desired_duration_seconds is None
        assert vq.notes is None

    def test_create_visual_query_with_all_fields(self, note_id, session_id):
        """Test creating a VisualQuery with all fields."""
        vq = VisualQuery(
            id=uuid4(),
            order=1,
            intent=VisualQueryIntent.EVIDENCE.value,
            query="Gameplay showing the boss fight",
            narration_excerpt="The boss has three phases",
            importance=VisualQueryImportance.REQUIRED.value,
            source_note_id=note_id,
            preferred_session_id=session_id,
            preferred_start_seconds=120.0,
            preferred_end_seconds=180.0,
            desired_duration_seconds=15.0,
            notes="Must show phase transition",
        )

        assert vq.order == 1
        assert vq.intent == "evidence"
        assert vq.query == "Gameplay showing the boss fight"
        assert vq.narration_excerpt == "The boss has three phases"
        assert vq.importance == "required"
        assert vq.source_note_id == note_id
        assert vq.preferred_session_id == session_id
        assert vq.preferred_start_seconds == 120.0
        assert vq.preferred_end_seconds == 180.0
        assert vq.desired_duration_seconds == 15.0
        assert vq.notes == "Must show phase transition"

    def test_visual_query_to_dict(self, note_id, session_id):
        """Test serializing VisualQuery to dictionary."""
        vq_id = uuid4()
        vq = VisualQuery(
            id=vq_id,
            order=2,
            intent=VisualQueryIntent.COMPARISON.value,
            query="Side by side comparison",
            narration_excerpt="Comparing the two versions",
            importance=VisualQueryImportance.PREFERRED.value,
            source_note_id=note_id,
            preferred_session_id=session_id,
            preferred_start_seconds=60.0,
            preferred_end_seconds=90.0,
            desired_duration_seconds=10.0,
            notes=None,
        )

        result = vq.to_dict()

        assert result["id"] == str(vq_id)
        assert result["order"] == 2
        assert result["intent"] == "comparison"
        assert result["query"] == "Side by side comparison"
        assert result["narration_excerpt"] == "Comparing the two versions"
        assert result["importance"] == "preferred"
        assert result["source_note_id"] == str(note_id)
        assert result["preferred_session_id"] == str(session_id)
        assert result["preferred_start_seconds"] == 60.0
        assert result["preferred_end_seconds"] == 90.0
        assert result["desired_duration_seconds"] == 10.0
        assert result["notes"] is None

    def test_visual_query_from_dict(self, note_id, session_id):
        """Test deserializing VisualQuery from dictionary."""
        vq_id = uuid4()
        data = {
            "id": str(vq_id),
            "order": 3,
            "intent": "atmosphere",
            "query": "Dark moody environment",
            "narration_excerpt": "The atmosphere is oppressive",
            "importance": "optional",
            "source_note_id": str(note_id),
            "preferred_session_id": str(session_id),
            "preferred_start_seconds": 200.0,
            "preferred_end_seconds": 250.0,
            "desired_duration_seconds": 20.0,
            "notes": "No dialogue needed",
        }

        vq = VisualQuery.from_dict(data)

        assert vq.id == vq_id
        assert vq.order == 3
        assert vq.intent == "atmosphere"
        assert vq.query == "Dark moody environment"
        assert vq.narration_excerpt == "The atmosphere is oppressive"
        assert vq.importance == "optional"
        assert vq.source_note_id == note_id
        assert vq.preferred_session_id == session_id
        assert vq.preferred_start_seconds == 200.0
        assert vq.preferred_end_seconds == 250.0
        assert vq.desired_duration_seconds == 20.0
        assert vq.notes == "No dialogue needed"

    def test_visual_query_from_dict_with_nulls(self):
        """Test deserializing VisualQuery with null optional fields."""
        vq_id = uuid4()
        data = {
            "id": str(vq_id),
            "order": 0,
            "intent": "illustration",
            "query": "Generic gameplay",
            "narration_excerpt": None,
            "importance": "optional",
            "source_note_id": None,
            "preferred_session_id": None,
            "preferred_start_seconds": None,
            "preferred_end_seconds": None,
            "desired_duration_seconds": None,
            "notes": None,
        }

        vq = VisualQuery.from_dict(data)

        assert vq.id == vq_id
        assert vq.narration_excerpt is None
        assert vq.source_note_id is None
        assert vq.preferred_session_id is None


class TestVisualQueryEnums:
    """Tests for VisualQueryIntent and VisualQueryImportance enums."""

    def test_intent_values(self):
        """Test VisualQueryIntent enum values."""
        assert VisualQueryIntent.ILLUSTRATION.value == "illustration"
        assert VisualQueryIntent.EVIDENCE.value == "evidence"
        assert VisualQueryIntent.TRANSITION.value == "transition"
        assert VisualQueryIntent.ATMOSPHERE.value == "atmosphere"
        assert VisualQueryIntent.COMPARISON.value == "comparison"

    def test_importance_values(self):
        """Test VisualQueryImportance enum values."""
        assert VisualQueryImportance.REQUIRED.value == "required"
        assert VisualQueryImportance.PREFERRED.value == "preferred"
        assert VisualQueryImportance.OPTIONAL.value == "optional"


class TestBlocoNarrativoWithVisualQueries:
    """Tests for BlocoNarrativo with visual_queries field."""

    def test_bloco_with_empty_visual_queries(self):
        """Test BlocoNarrativo with empty visual_queries list."""
        bloco = BlocoNarrativo(
            tipo="introducao",
            duracao_segundos=60,
            conteudo="This is the intro",
        )

        assert bloco.visual_queries == []

    def test_bloco_with_visual_queries(self, note_id, session_id):
        """Test BlocoNarrativo with visual_queries."""
        vq = VisualQuery(
            order=0,
            intent=VisualQueryIntent.EVIDENCE.value,
            query="Boss fight footage",
            importance=VisualQueryImportance.REQUIRED.value,
            source_note_id=note_id,
            preferred_session_id=session_id,
            preferred_start_seconds=100.0,
            preferred_end_seconds=150.0,
        )

        bloco = BlocoNarrativo(
            tipo="boss_fight",
            duracao_segundos=120,
            conteudo="The boss fight is challenging",
            visual_queries=[vq],
        )

        assert len(bloco.visual_queries) == 1
        assert bloco.visual_queries[0].query == "Boss fight footage"


class TestRoteiristaServiceSerialization:
    """Tests for RoteiristaService.to_dict with visual_queries."""

    def test_to_dict_with_visual_queries(self, note_id, session_id):
        """Test to_dict serialization includes visual_queries."""
        from app.agents.roteirista import RoteiristaService

        service = RoteiristaService()

        vq = VisualQuery(
            order=0,
            intent=VisualQueryIntent.ILLUSTRATION.value,
            query="General gameplay",
            importance=VisualQueryImportance.PREFERRED.value,
            source_note_id=note_id,
            preferred_session_id=session_id,
        )

        bloco = BlocoNarrativo(
            tipo="desenvolvimento",
            duracao_segundos=60,
            conteudo="Some content",
            visual_queries=[vq],
        )

        roteiro = RoteiroEstruturado(
            titulo="Test Roteiro",
            duracao_total_segundos=60,
            blocos=[bloco],
            tags=["test"],
        )

        result = service.to_dict(roteiro)

        assert "production_script_schema_version" in result
        assert result["production_script_schema_version"] == "2.1"
        assert result["media_context"] is None
        assert len(result["blocos"]) == 1
        assert "visual_queries" in result["blocos"][0]
        assert len(result["blocos"][0]["visual_queries"]) == 1
        assert result["blocos"][0]["visual_queries"][0]["query"] == "General gameplay"

    def test_to_dict_backward_compatibility_no_visual_queries(self):
        """Test to_dict with old roteiro without visual_queries."""
        from app.agents.roteirista import RoteiristaService

        service = RoteiristaService()

        bloco = BlocoNarrativo(
            tipo="introducao",
            duracao_segundos=60,
            conteudo="Some content",
        )

        roteiro = RoteiroEstruturado(
            titulo="Old Roteiro",
            duracao_total_segundos=60,
            blocos=[bloco],
            tags=["old"],
        )

        result = service.to_dict(roteiro)

        # Should still have visual_queries field (empty list)
        assert "visual_queries" in result["blocos"][0]
        assert result["blocos"][0]["visual_queries"] == []


class TestProvenanceCanonicalization:
    """Tests for provenance canonicalization in AnaliseJogosService."""

    @pytest.fixture
    def service(self):
        """Create an AnaliseJogosService instance."""
        return AnaliseJogosService()

    def _make_media_context(
        self, session_id: UUID, note_id: UUID, start: float = 120.0, end: float = 180.0
    ) -> GameAnalysisMediaContext:
        """Create a GameAnalysisMediaContext with a matched note."""
        note = MediaIndexerNote(
            id=note_id,
            order=0,
            raw="The combat system feels smooth",
            alignment_status="matched",
        )
        alignment = MediaIndexerAlignment(
            candidate_alignment_id=uuid4(),
            retrieval_rank=1,
            start_seconds=start,
            end_seconds=end,
            confidence=0.85,
        )
        timeline_note = MediaIndexerTimelineNote(note=note, alignment=alignment)
        session = MediaIndexerTimelineSession(
            session_id=session_id,
            session_label="Test Session",
            notes=[timeline_note],
        )

        return GameAnalysisMediaContext(
            project_id=uuid4(),
            sessions=[session],
            search_results=[],
            total_notes=1,
            matched_notes=1,
            unmatched_notes=0,
            total_chars=100,
            warnings=[],
            available=True,
        )

    def test_build_note_provenance_lookup(self, service, session_id, note_id):
        """Test building note provenance lookup from media context."""
        media_context = self._make_media_context(session_id, note_id)

        lookup = service._build_note_provenance_lookup(media_context)

        assert len(lookup) == 1
        assert note_id in lookup
        assert lookup[note_id] == (session_id, 120.0, 180.0)

    def test_build_note_provenance_lookup_empty_context(self, service):
        """Test lookup with no media context."""
        lookup = service._build_note_provenance_lookup(None)

        assert lookup == {}

    def test_build_note_provenance_lookup_unavailable_context(self, service):
        """Test lookup with unavailable media context."""
        media_context = GameAnalysisMediaContext(
            project_id=uuid4(),
            sessions=[],
            search_results=[],
            total_notes=0,
            matched_notes=0,
            unmatched_notes=0,
            total_chars=0,
            warnings=[],
            available=False,
        )

        lookup = service._build_note_provenance_lookup(media_context)

        assert lookup == {}

    def test_parse_visual_queries_with_valid_source_note(
        self, service, session_id, note_id
    ):
        """Test parsing visual queries with valid source_note_id."""
        media_context = self._make_media_context(session_id, note_id)
        lookup = service._build_note_provenance_lookup(media_context)

        vq_data = [
            {
                "intent": "evidence",
                "query": "Combat footage",
                "narration_excerpt": "The combat feels smooth",
                "importance": "required",
                "source_note_id": str(note_id),
                "desired_duration_seconds": 15.0,
            }
        ]

        queries = service._parse_visual_queries(vq_data, lookup)

        assert len(queries) == 1
        assert queries[0].source_note_id == note_id
        assert queries[0].preferred_session_id == session_id
        assert queries[0].preferred_start_seconds == 120.0
        assert queries[0].preferred_end_seconds == 180.0

    def test_parse_visual_queries_with_invalid_source_note(self, service):
        """Test parsing visual queries with invalid source_note_id."""
        fake_note_id = uuid4()
        lookup = {}

        vq_data = [
            {
                "intent": "illustration",
                "query": "Generic footage",
                "importance": "optional",
                "source_note_id": str(fake_note_id),
            }
        ]

        queries = service._parse_visual_queries(vq_data, lookup)

        # Should keep the source_note_id but not fill provenance
        assert len(queries) == 1
        assert queries[0].source_note_id == fake_note_id
        assert queries[0].preferred_session_id is None
        assert queries[0].preferred_start_seconds is None

    def test_parse_visual_queries_without_source_note(self, service):
        """Test parsing visual queries without source_note_id."""
        lookup = {}

        vq_data = [
            {
                "intent": "atmosphere",
                "query": "Dark environment",
                "importance": "preferred",
            }
        ]

        queries = service._parse_visual_queries(vq_data, lookup)

        assert len(queries) == 1
        assert queries[0].source_note_id is None
        assert queries[0].preferred_session_id is None

    def test_parse_visual_queries_max_five(self, service):
        """Test that only 5 visual queries are parsed per block."""
        lookup = {}

        vq_data = [{"intent": "illustration", "query": f"Query {i}"} for i in range(10)]

        queries = service._parse_visual_queries(vq_data, lookup)

        assert len(queries) == 5

    def test_parse_visual_queries_empty_list(self, service):
        """Test parsing empty visual queries list."""
        lookup = {}

        queries = service._parse_visual_queries([], lookup)

        assert queries == []

    def test_parse_visual_queries_none(self, service):
        """Test parsing None visual queries."""
        lookup = {}

        queries = service._parse_visual_queries(None, lookup)

        assert queries == []


class TestFormatMediaContextForPrompt:
    """Tests for format_media_context_for_prompt with note IDs."""

    def test_format_includes_note_id(self, session_id, note_id):
        """Test that formatted output includes note ID for visual_query reference."""
        note = MediaIndexerNote(
            id=note_id,
            order=0,
            raw="The combat feels smooth",
            alignment_status="matched",
        )
        alignment = MediaIndexerAlignment(
            candidate_alignment_id=uuid4(),
            retrieval_rank=1,
            start_seconds=120.0,
            end_seconds=180.0,
            confidence=0.85,
        )
        timeline_note = MediaIndexerTimelineNote(note=note, alignment=alignment)
        session = MediaIndexerTimelineSession(
            session_id=session_id,
            session_label="Main Gameplay",
            notes=[timeline_note],
        )

        media_context = GameAnalysisMediaContext(
            project_id=uuid4(),
            sessions=[session],
            search_results=[],
            total_notes=1,
            matched_notes=1,
            unmatched_notes=0,
            total_chars=100,
            warnings=[],
            available=True,
        )

        result = format_media_context_for_prompt(media_context)

        # Should include note ID in the format [id={uuid}]
        assert f"[id={note_id}]" in result
        assert "The combat feels smooth" in result

    def test_format_unmatched_note_includes_id(self, session_id, note_id):
        """Test that unmatched notes also include note ID."""
        note = MediaIndexerNote(
            id=note_id,
            order=0,
            raw="Unmatched observation",
            alignment_status="unmatched",
        )
        timeline_note = MediaIndexerTimelineNote(note=note, alignment=None)
        session = MediaIndexerTimelineSession(
            session_id=session_id,
            session_label="Test Session",
            notes=[timeline_note],
        )

        media_context = GameAnalysisMediaContext(
            project_id=uuid4(),
            sessions=[session],
            search_results=[],
            total_notes=1,
            matched_notes=0,
            unmatched_notes=1,
            total_chars=50,
            warnings=[],
            available=True,
        )

        result = format_media_context_for_prompt(media_context)

        assert f"[id={note_id}]" in result
        assert "[unmatched]" in result
        assert "Unmatched observation" in result


class TestBackwardCompatibility:
    """Tests for backward compatibility with old roteiros."""

    def test_old_roteiro_dict_without_visual_queries(self):
        """Test that old roteiro dicts without visual_queries can be handled."""
        # Simulating an old roteiro dict from JSONB
        old_roteiro_dict = {
            "titulo": "Old Analysis",
            "duracao_total_segundos": 300,
            "blocos": [
                {
                    "tipo": "introducao",
                    "duracao_segundos": 60,
                    "conteudo": "Intro content",
                    "dicas_visual": "Show gameplay",
                    "dicas_audio": "Upbeat music",
                    # No visual_queries key
                }
            ],
            "tags": ["game"],
        }

        # When parsing, visual_queries should default to empty list
        bloco_data = old_roteiro_dict["blocos"][0]
        visual_queries = bloco_data.get("visual_queries", [])

        assert visual_queries == []

    def test_schema_versioning(self):
        """Test that new roteiros include schema version."""
        from app.agents.roteirista import RoteiristaService

        service = RoteiristaService()

        bloco = BlocoNarrativo(
            tipo="test",
            duracao_segundos=60,
            conteudo="Content",
        )

        roteiro = RoteiroEstruturado(
            titulo="New Roteiro",
            duracao_total_segundos=60,
            blocos=[bloco],
            tags=[],
        )

        result = service.to_dict(roteiro)

        # New schema includes version
        assert "production_script_schema_version" in result
        assert result["production_script_schema_version"] == "2.1"
