# Manual Script Import V1

`neovids_manual_script_v1` importa texto escrito fora do Ideas Hub para o mesmo
histórico canônico de roteiros. A Idea já deve existir; nicho, ProductionProfile,
author briefing e intenção de duração continuam pertencendo a ela.

Campos obrigatórios:

- `schema`: sempre `neovids_manual_script_v1`;
- `title`;
- `blocks`: um ou mais objetos com `type` e `text`.

Campos opcionais:

- `blocks[].duration_seconds`: estimativa editorial positiva; quando omitida, o
  servidor usa a calibração de duração corrente;
- `tags` e `references`;
- `media.project_id` e `media.session_ids`. Uma lista vazia mantém a semântica
  canônica de pesquisar o projeto inteiro.

O schema é estrito. Não forneça VisualQueries, spans, timestamps, IDs de beats,
duration contract, readiness, approval, evidence, prompt trace, generation run ou
outros metadados host-owned. O arquivo contém dados; paths, URLs de importação e
overrides de provider/model não são aceitos.

Fluxo:

1. selecione uma Idea e valide o arquivo em `POST /roteiros/importar/preview`;
2. importe em `POST /roteiros/importar`;
3. se houver mídia, o Ideas Hub cria `manual_create → media_binding`;
4. use normalmente Preparar para produção, revisão e aprovação;
5. somente uma revisão enriquecida, aprovada e `production-readiness=ready` pode
   entrar no Orchestrator.

O import não cria auditoria factual. Se uma auditoria posterior definir
`approval_blocked=true`, a aprovação retorna um erro de negócio e exige uma nova
revisão; warnings não bloqueantes continuam disponíveis para decisão humana.

Veja [o exemplo](examples/manual-script-v1.json).
