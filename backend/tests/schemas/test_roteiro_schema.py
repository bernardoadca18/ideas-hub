from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.schemas.roteiro import RoteiroCreate


def test_persisted_script_rejects_empty_blocks() -> None:
    with pytest.raises(ValidationError):
        RoteiroCreate(
            ideia_id=uuid4(),
            estrutura={
                "titulo": "Inválido",
                "duracao_total_segundos": 60,
                "blocos": [],
            },
        )
