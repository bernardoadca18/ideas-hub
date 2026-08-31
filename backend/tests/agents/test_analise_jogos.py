"""
Tests for AnaliseJogosService with Media Indexer integration.

Tests the game analysis workflow with optional media context.
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from app.agents.analise_jogos import (
    AnaliseJogosService,
    format_media_context_for_prompt,
)
from app.agents.roteirista import RoteiroEstruturado
from app.schemas.media_indexer import (
    GameAnalysisMediaContext,
    MediaIndexerAlignment,
    MediaIndexerNote,
    MediaIndexerTimelineNote,
    MediaIndexerTimelineSession,
)


@pytest.fixture
def project_id():
    """Sample project ID."""
    return uuid4()


@pytest.fixture
def session_id():
    """Sample session ID."""
    return uuid4()


def _make_timeline_session(session_id, num_notes=2):
    """Create a MediaIndexerTimelineSession for testing."""
    notes = []
    for i in range(num_notes):
        note = MediaIndexerNote(
            id=uuid4(),
            order=i,
            raw=f"Test note {i} about gameplay observations",
            alignment_status="matched" if i % 2 == 0 else "unmatched",
        )
        alignment = None
        if i % 2 == 0:
            alignment = MediaIndexerAlignment(
                candidate_alignment_id=uuid4(),
                retrieval_rank=1,
                start_seconds=float(i * 120),
                end_seconds=float(i * 120 + 45),
                confidence=0.89,
            )
        notes.append(MediaIndexerTimelineNote(note=note, alignment=alignment))

    return MediaIndexerTimelineSession(
        session_id=session_id,
        session_label="Main Gameplay Session",
        notes=notes,
    )


@pytest.fixture
def sample_media_context(session_id):
    """Sample media context for testing."""
    timeline_session = _make_timeline_session(session_id, num_notes=2)

    return GameAnalysisMediaContext(
        project_id=uuid4(),
        sessions=[timeline_session],
        search_results=[],
        total_notes=2,
        matched_notes=1,
        unmatched_notes=1,
        total_chars=200,
        warnings=[],
        available=True,
    )


class TestFormatMediaContextForPrompt:
    """Tests for format_media_context_for_prompt helper."""

    def test_formats_empty_context(self):
        """Test formatting empty/unavailable context."""
        context = GameAnalysisMediaContext(
            project_id=uuid4(),
            sessions=[],
            search_results=[],
            total_notes=0,
            matched_notes=0,
            unmatched_notes=0,
            total_chars=0,
            warnings=["Not available"],
            available=False,
        )

        result = format_media_context_for_prompt(context)
        assert result == ""

    def test_formats_matched_note(self, session_id):
        """Test formatting a matched note with timestamp."""
        timeline_session = _make_timeline_session(session_id, num_notes=1)
        context = GameAnalysisMediaContext(
            project_id=uuid4(),
            sessions=[timeline_session],
            search_results=[],
            total_notes=1,
            matched_notes=1,
            unmatched_notes=0,
            total_chars=100,
            warnings=[],
            available=True,
        )

        result = format_media_context_for_prompt(context)

        assert "Session: Main Gameplay Session" in result
        # Note format now includes [id={uuid}] for visual_query reference
        assert "[matched]" in result
        assert "Note 0" in result
        # First matched note has start_seconds=0, end_seconds=45
        assert "00:00-00:45" in result
        assert "confidence: 0.89" in result

    def test_formats_unmatched_note(self, session_id):
        """Test formatting an unmatched note."""
        note = MediaIndexerNote(
            id=uuid4(),
            order=1,
            raw="Unmatched observation",
            alignment_status="unmatched",
        )
        timeline_session = MediaIndexerTimelineSession(
            session_id=session_id,
            session_label="Session 1",
            notes=[MediaIndexerTimelineNote(note=note, alignment=None)],
        )
        context = GameAnalysisMediaContext(
            project_id=uuid4(),
            sessions=[timeline_session],
            search_results=[],
            total_notes=1,
            matched_notes=0,
            unmatched_notes=1,
            total_chars=50,
            warnings=[],
            available=True,
        )

        result = format_media_context_for_prompt(context)

        # Note format now includes [id={uuid}] for visual_query reference
        assert "[unmatched]" in result
        assert "Note 1" in result
        # Unmatched notes don't have timestamp info
        lines = result.split("\n")
        note_line = next(line for line in lines if "Note 1" in line)
        assert "confidence" not in note_line

    def test_includes_warnings(self):
        """Test that warnings are included in output."""
        context = GameAnalysisMediaContext(
            project_id=uuid4(),
            sessions=[],
            search_results=[],
            total_notes=0,
            matched_notes=0,
            unmatched_notes=0,
            total_chars=0,
            warnings=["Timeline was truncated"],
            available=True,
        )

        result = format_media_context_for_prompt(context)
        assert "Warnings:" in result
        assert "Timeline was truncated" in result


class TestAnaliseJogosServiceMediaContext:
    """Tests for media context integration in game analysis."""

    @pytest.fixture
    def analise_service(self):
        """Create an AnaliseJogosService instance for testing."""
        return AnaliseJogosService()

    @pytest.mark.asyncio
    async def test_gerar_roteiro_without_media_context(self, analise_service):
        """Test script generation without media context (legacy workflow)."""
        with patch("httpx.AsyncClient") as mock_client:
            client_instance = AsyncMock()
            mock_client.return_value = client_instance
            mock_client.return_value.__aenter__.return_value = client_instance

            # Mock LLM response
            roteiro_json = {
                "titulo": "Dark Souls Combat Analysis",
                "duracao_total_segundos": 600,
                "blocos": [
                    {
                        "tipo": "introducao",
                        "duracao_segundos": 60,
                        "conteudo": "Introduction to the combat system",
                        "dicas_visual": "Gameplay footage",
                        "dicas_audio": "Epic music",
                    },
                ],
                "tags": ["dark souls", "combat", "analysis"],
                "referencias": [],
                "justificativa": "Deep analysis",
            }

            response = MagicMock()
            response.status_code = 200
            response.json.return_value = {
                "choices": [{"message": {"content": json.dumps(roteiro_json)}}],
                "usage": {"total_tokens": 500},
            }
            response.raise_for_status = MagicMock()
            client_instance.post.return_value = response

            result = await analise_service.gerar_roteiro_de_notas(
                titulo_provisorio="Dark Souls Combat",
                anotacoes="The combat feels weighty and deliberate. Every swing matters.",
                nome_jogo="Dark Souls",
                prompt_nicho=None,
                usar_grounding=False,
                media_project_id=None,  # No media context
                media_session_ids=None,
            )

            assert isinstance(result, RoteiroEstruturado)
            assert result.titulo == "Dark Souls Combat Analysis"
            assert len(result.blocos) == 1

    @pytest.mark.asyncio
    async def test_gerar_roteiro_with_media_context(
        self, analise_service, project_id, sample_media_context
    ):
        """Test script generation with media context."""
        # Mock media context provider
        mock_provider = AsyncMock()
        mock_provider.get_context.return_value = sample_media_context
        analise_service._media_context_provider = mock_provider

        with patch("httpx.AsyncClient") as mock_client:
            client_instance = AsyncMock()
            mock_client.return_value = client_instance
            mock_client.return_value.__aenter__.return_value = client_instance

            # Mock LLM response
            roteiro_json = {
                "titulo": "Elden Ring Combat Deep Dive",
                "duracao_total_segundos": 900,
                "blocos": [
                    {
                        "tipo": "introducao",
                        "duracao_segundos": 60,
                        "conteudo": "Exploring the combat mechanics",
                        "dicas_visual": "Use timestamp 00:00 for combat footage",
                        "dicas_audio": "Tension building music",
                    },
                ],
                "tags": ["elden ring", "combat"],
                "referencias": [],
                "justificativa": "Analysis with media evidence",
            }

            response = MagicMock()
            response.status_code = 200
            response.json.return_value = {
                "choices": [{"message": {"content": json.dumps(roteiro_json)}}],
                "usage": {"total_tokens": 600},
            }
            response.raise_for_status = MagicMock()
            client_instance.post.return_value = response

            result = await analise_service.gerar_roteiro_de_notas(
                titulo_provisorio="Elden Ring Combat",
                anotacoes="The combat system rewards patience and timing.",
                nome_jogo="Elden Ring",
                prompt_nicho=None,
                usar_grounding=False,
                media_project_id=project_id,
                media_session_ids=None,
            )

            # Verify media context was requested
            mock_provider.get_context.assert_called_once()
            assert isinstance(result, RoteiroEstruturado)

    @pytest.mark.asyncio
    async def test_gerar_roteiro_media_context_fail_open(
        self, analise_service, project_id
    ):
        """Test that script generation continues if media context fails."""
        # Mock media context provider that fails
        mock_provider = AsyncMock()
        from app.services.media_indexer_client import MediaIndexerUnavailableError

        mock_provider.get_context.side_effect = MediaIndexerUnavailableError(
            "Connection refused"
        )
        analise_service._media_context_provider = mock_provider

        with patch("httpx.AsyncClient") as mock_client:
            client_instance = AsyncMock()
            mock_client.return_value = client_instance
            mock_client.return_value.__aenter__.return_value = client_instance

            # Mock LLM response
            roteiro_json = {
                "titulo": "Bloodborne Analysis",
                "duracao_total_segundos": 750,
                "blocos": [
                    {
                        "tipo": "desenvolvimento",
                        "duracao_segundos": 750,
                        "conteudo": "Analysis without media context",
                        "dicas_visual": "Generic footage",
                        "dicas_audio": None,
                    },
                ],
                "tags": ["bloodborne"],
                "referencias": None,
                "justificativa": "Generated despite media indexer unavailability",
            }

            response = MagicMock()
            response.status_code = 200
            response.json.return_value = {
                "choices": [{"message": {"content": json.dumps(roteiro_json)}}],
                "usage": {"total_tokens": 500},
            }
            response.raise_for_status = MagicMock()
            client_instance.post.return_value = response

            # Should not raise - fail open
            result = await analise_service.gerar_roteiro_de_notas(
                titulo_provisorio="Bloodborne Combat",
                anotacoes="Fast paced aggressive combat.",
                nome_jogo="Bloodborne",
                prompt_nicho=None,
                usar_grounding=False,
                media_project_id=project_id,
                media_session_ids=None,
            )

            assert isinstance(result, RoteiroEstruturado)
            assert result.titulo == "Bloodborne Analysis"

    @pytest.mark.asyncio
    async def test_gerar_roteiro_with_session_filter(
        self, analise_service, project_id, session_id, sample_media_context
    ):
        """Test script generation with specific session filter."""
        mock_provider = AsyncMock()
        mock_provider.get_context.return_value = sample_media_context
        analise_service._media_context_provider = mock_provider

        with patch("httpx.AsyncClient") as mock_client:
            client_instance = AsyncMock()
            mock_client.return_value = client_instance
            mock_client.return_value.__aenter__.return_value = client_instance

            roteiro_json = {
                "titulo": "Session Specific Analysis",
                "duracao_total_segundos": 400,
                "blocos": [
                    {
                        "tipo": "desenvolvimento",
                        "duracao_segundos": 400,
                        "conteudo": "Session-specific analysis",
                        "dicas_visual": None,
                        "dicas_audio": None,
                    }
                ],
                "tags": [],
                "referencias": None,
                "justificativa": "Test",
            }

            response = MagicMock()
            response.status_code = 200
            response.json.return_value = {
                "choices": [{"message": {"content": json.dumps(roteiro_json)}}],
                "usage": {"total_tokens": 300},
            }
            response.raise_for_status = MagicMock()
            client_instance.post.return_value = response

            result = await analise_service.gerar_roteiro_de_notas(
                titulo_provisorio="Filtered Analysis",
                anotacoes="Notes from specific session.",
                nome_jogo="Test Game",
                prompt_nicho=None,
                usar_grounding=False,
                media_project_id=project_id,
                media_session_ids=[session_id],  # Filter to specific session
            )

            # Verify session filter was passed
            call_args = mock_provider.get_context.call_args
            assert call_args.kwargs["media_session_ids"] == [session_id]
            assert result.media_context == {
                "media_project_id": str(project_id),
                "media_session_ids": [str(session_id)],
            }

    @pytest.mark.asyncio
    async def test_gerar_roteiro_with_grounding_and_media_context(
        self, analise_service, project_id, sample_media_context
    ):
        """Test script generation with both grounding and media context."""
        mock_provider = AsyncMock()
        mock_provider.get_context.return_value = sample_media_context
        analise_service._media_context_provider = mock_provider

        with patch("httpx.AsyncClient") as mock_client:
            client_instance = AsyncMock()
            mock_client.return_value = client_instance
            mock_client.return_value.__aenter__.return_value = client_instance

            # Mock Tavily response (grounding)
            tavily_response = MagicMock()
            tavily_response.status_code = 200
            tavily_response.json.return_value = {
                "answer": "FromSoftware developed Sekiro",
                "results": [],
            }
            tavily_response.raise_for_status = MagicMock()

            # Mock LLM response
            roteiro_json = {
                "titulo": "Sekiro Analysis with Context",
                "duracao_total_segundos": 800,
                "blocos": [
                    {
                        "tipo": "desenvolvimento",
                        "duracao_segundos": 800,
                        "conteudo": "Combined analysis",
                        "dicas_visual": None,
                        "dicas_audio": None,
                    }
                ],
                "tags": ["sekiro"],
                "referencias": ["FromSoftware info"],
                "justificativa": "Combined grounding and media evidence",
            }

            llm_response = MagicMock()
            llm_response.status_code = 200
            llm_response.json.return_value = {
                "choices": [{"message": {"content": json.dumps(roteiro_json)}}],
                "usage": {"total_tokens": 700},
            }
            llm_response.raise_for_status = MagicMock()

            client_instance.post.side_effect = [tavily_response, llm_response]
            analise_service.tavily_api_key = "test-key"

            result = await analise_service.gerar_roteiro_de_notas(
                titulo_provisorio="Sekiro Combat",
                anotacoes="Posture system is unique.",
                nome_jogo="Sekiro",
                prompt_nicho=None,
                usar_grounding=True,  # Enable grounding
                media_project_id=project_id,
                media_session_ids=None,
            )

            assert isinstance(result, RoteiroEstruturado)
            # Both Tavily (grounding) and media context should have been called
            assert client_instance.post.call_count == 2


class TestAnaliseJogosServiceLazyInit:
    """Tests for lazy initialization of media context provider."""

    def test_lazy_init_creates_fake_when_not_configured(self):
        """Test that fake provider is created when Media Indexer not configured."""
        # Patch the settings that the property reads
        with patch("app.agents.analise_jogos.settings") as mock_settings:
            mock_settings.media_indexer_base_url = ""  # Not configured
            mock_settings.game_analysis_media_context_max_chars = 50000

            from app.services.media_context_provider import FakeMediaContextProvider

            service = AnaliseJogosService()
            provider = service.media_context_provider

            assert isinstance(provider, FakeMediaContextProvider)

    def test_lazy_init_creates_real_when_configured(self):
        """Test that real provider is created when Media Indexer is configured."""
        with patch("app.agents.analise_jogos.settings") as mock_settings:
            mock_settings.media_indexer_base_url = "http://localhost:8012"
            mock_settings.media_indexer_timeout_seconds = 30
            mock_settings.media_indexer_api_key = ""
            mock_settings.game_analysis_media_context_max_chars = 50000

            from app.services.media_indexer_context_provider import (
                MediaIndexerContextProvider,
            )

            service = AnaliseJogosService()
            provider = service.media_context_provider

            assert isinstance(provider, MediaIndexerContextProvider)
