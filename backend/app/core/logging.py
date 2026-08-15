"""
Sistema de logging estruturado para os agentes.

Registra tempo de resposta, tokens usados, resultados de checagem de duplicidade
e outras métricas importantes em formato JSON estruturado.
"""
import json
import time
from datetime import datetime
from typing import Any
from functools import wraps
from dataclasses import dataclass, asdict
from enum import Enum

import structlog


class AgentType(str, Enum):
    """Tipos de agentes no sistema."""
    CURADOR = "curador"
    ROTEIRISTA = "roteirista"
    GERADOR_IDEIAS = "gerador_ideias"


@dataclass
class AgentMetrics:
    """Métricas coletadas durante execução do agente."""
    agent_type: str
    operation: str
    start_time: float
    end_time: float | None = None
    duration_seconds: float | None = None
    tokens_used: int | None = None
    llm_model: str | None = None
    success: bool = True
    error: str | None = None

    # Métricas específicas do Curador
    similarity_score: float | None = None
    is_duplicate: bool | None = None
    is_continuation: bool | None = None
    grounding_used: bool | None = None

    # Métricas específicas do Roteirista
    num_blocos: int | None = None
    duracao_total_segundos: int | None = None

    # Métricas específicas do Gerador de Ideias
    num_ideias_geradas: int | None = None

    # Contexto adicional
    nicho_id: str | None = None
    ideia_id: str | None = None
    trend_id: str | None = None
    roteiro_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Converte para dicionário, removendo campos None."""
        return {k: v for k, v in asdict(self).items() if v is not None}


def setup_logging():
    """Configura o logging estruturado."""
    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.UnicodeDecoder(),
            structlog.processors.JSONRenderer()
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )


class AgentLogger:
    """Logger especializado para agentes com métricas."""

    def __init__(self, agent_type: AgentType):
        self.agent_type = agent_type
        self.logger = structlog.get_logger(f"agent.{agent_type.value}")

    def start_operation(self, operation: str, **context) -> AgentMetrics:
        """Inicia uma operação e retorna objeto de métricas."""
        metrics = AgentMetrics(
            agent_type=self.agent_type.value,
            operation=operation,
            start_time=time.time(),
            **context
        )

        self.logger.info(
            f"{operation}_started",
            agent_type=self.agent_type.value,
            operation=operation,
            **context
        )

        return metrics

    def end_operation(
        self,
        metrics: AgentMetrics,
        success: bool = True,
        error: str | None = None,
        **additional_metrics
    ) -> AgentMetrics:
        """Finaliza uma operação e registra métricas."""
        metrics.end_time = time.time()
        metrics.duration_seconds = round(metrics.end_time - metrics.start_time, 3)
        metrics.success = success
        metrics.error = error

        # Adiciona métricas adicionais
        for key, value in additional_metrics.items():
            if hasattr(metrics, key):
                setattr(metrics, key, value)

        # Log estruturado
        log_data = metrics.to_dict()

        if success:
            self.logger.info(
                f"{metrics.operation}_completed",
                **log_data
            )
        else:
            self.logger.error(
                f"{metrics.operation}_failed",
                **log_data
            )

        return metrics

    def log_llm_call(
        self,
        model: str,
        tokens_used: int | None = None,
        duration: float | None = None,
        success: bool = True,
        error: str | None = None
    ):
        """Registra chamada para LLM."""
        self.logger.info(
            "llm_call",
            agent_type=self.agent_type.value,
            llm_model=model,
            tokens_used=tokens_used,
            duration_seconds=duration,
            success=success,
            error=error
        )

    def log_tavily_call(
        self,
        query: str,
        results_count: int | None = None,
        duration: float | None = None,
        success: bool = True,
        error: str | None = None
    ):
        """Registra chamada para Tavily."""
        self.logger.info(
            "tavily_call",
            agent_type=self.agent_type.value,
            query=query[:100],  # Limita tamanho da query no log
            results_count=results_count,
            duration_seconds=duration,
            success=success,
            error=error
        )

    def log_similarity_check(
        self,
        similarity_score: float,
        is_duplicate: bool,
        is_continuation: bool,
        similar_ideia_id: str | None = None
    ):
        """Registra resultado da checagem de similaridade."""
        self.logger.info(
            "similarity_check",
            agent_type=self.agent_type.value,
            similarity_score=round(similarity_score, 4),
            is_duplicate=is_duplicate,
            is_continuation=is_continuation,
            similar_ideia_id=similar_ideia_id
        )


# Instâncias globais dos loggers
curador_logger = AgentLogger(AgentType.CURADOR)
roteirista_logger = AgentLogger(AgentType.ROTEIRISTA)
gerador_ideias_logger = AgentLogger(AgentType.GERADOR_IDEIAS)
