from app.models.ideia import Ideia
from app.models.nicho import Nicho


def test_idea_projects_its_niche_production_profile() -> None:
    idea = Ideia(origem="manual", titulo="Ideia")
    idea.nicho = Nicho(
        slug="jogos",
        nome="Jogos",
        prompt_ideacao="Ideias",
        prompt_roteiro="Roteiros",
        perfil_producao="bernardo_xvec_v1",
    )
    assert idea.perfil_producao == "bernardo_xvec_v1"


def test_idea_without_niche_has_no_profile_override() -> None:
    idea = Ideia(origem="manual", titulo="Ideia")
    idea.nicho = None
    assert idea.perfil_producao is None
