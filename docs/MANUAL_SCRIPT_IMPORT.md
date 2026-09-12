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

## Rascunho colado e melhoria Editorial V3

A ação **Melhorar um rascunho meu** no Ideas Hub é uma entrada complementar ao
import JSON e não o substitui. Ela aceita texto simples em
`POST /ideias/{ideia_id}/manual-draft-improvement-runs` com:

- `draft_text`: texto humano original, sem trim ou reescrita;
- `feedback`: direção opcional para esta revisão;
- `idempotency_key`: identidade estável da submissão;
- `model_strategy`: política de modelos já suportada pelos generation runs.

O servidor adapta o texto deterministicamente para um único bloco canônico
`rascunho_humano`, calcula o duration contract e persiste `manual_create`. Em
seguida, na mesma operação transacional, cria um generation run com
`generation_intent=revision` e `parent_roteiro_id` apontando para o draft humano.
A resposta contém `draft` e `run`; o progresso continua disponível nos endpoints
normais de generation runs.

O texto original fica em `estrutura.blocos[0].conteudo` e sua identidade em
`estrutura.manual_draft`. O revision brief mapeia deterministicamente spans
contíguos do original para as seções host-owned do V3. O texto humano orienta
tese, argumentos, exemplos, ordem e voz, mas não entra no claim ledger como
evidência automática. Quando falta provenance factual, a pesquisa normal do
ProductionProfile continua sendo executada.

Repetir a mesma `idempotency_key` com o mesmo texto/feedback devolve o draft e o
run existentes. Reusar a chave com conteúdo diferente é rejeitado. Um savepoint
engloba `manual_create → enqueue_revision`; falha no enqueue não deixa uma versão
manual órfã nem altera a Idea para `em_roteiro` parcialmente.
