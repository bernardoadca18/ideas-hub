# Repaginação NeoVids — 17/10/2026

Shell lateral, Ideias, Roteiros e Studio usam a identidade dark do estúdio. Busca local por
título complementa os filtros existentes. A leitura de roteiros prioriza blocos, narração,
contexto e revisão. Duração ausente aparece como indisponível, sem estimativa fictícia.
Formulários mantêm campos e regras existentes. Modais têm foco inicial, contenção de Tab,
Escape e retorno de foco, respeitando as proteções de operações em andamento.

Foi adicionado o `QueryClientProvider` que faltava para o Studio usar os hooks de consulta
já presentes. O Studio recebeu estilos locais leves, orientação de projeto e erros de
consulta visíveis. Não foram adicionadas bibliotecas ou funcionalidades editoriais.

## Iniciar

Na pasta `frontend`, execute `npm ci` e `npm run dev -- --host 127.0.0.1`.
O Vite usa a porta 5173 configurada no projeto e informa a URL efetiva no terminal.
Configure `VITE_API_URL` com a URL real do Ideas Hub e `VITE_MEDIA_INDEXER_URL` com a URL real
da biblioteca acessível pelo navegador. Os valores padrão existentes são, respectivamente,
`http://localhost:8000` e `http://localhost:8001`; não foram usados para links entre consoles.
Reinicie o Vite após mudar variáveis.

## Validação

- PASS: TypeScript (`npm test`, que executa `tsc --noEmit`) e build (`npm run build`).
- PASS: navegador com fixtures: criar uma ideia no servidor em memória, abrir roteiro,
  ler bloqueadores, Tab/Escape e retorno de foco; Studio abre com consulta de projetos.
- PASS: leitura em 390×844 sem overflow da página; revisão desktop em 1440×900.
- PASS: carregamento com atraso e falha 503 simulados, incluindo botão de tentar novamente.
- PASS: dois testes de contrato: `node --experimental-strip-types --test tests/media-search-contract.test.mjs` em frontend (Node 22.6+).
- SKIP: lint (não há script),
  APIs reais, geração de roteiro, aprovação persistida e demais operações de IA.

Capturas e fixtures ficam em `C:/workspaces/neovids/visual-qa` e não entram na aplicação.
Tendências e Análise de jogos mantêm os fluxos existentes e herdam o shell/controles;
não receberam revisão funcional dedicada. Studio recebeu polimento contido, não um editor.

Na continuação, o Studio passou a usar a busca por projeto existente: POST
`/media-search/projects/{project_id}` com `query` e `max_results`. A busca global não existe
no backend deste checkout e foi removida do cliente. A pesquisa acontece no envio do formulário,
sem chamada por tecla. Resultados abrem sessão com o índice e os limites originais, e a volta
preserva a consulta. Falhas de projetos, sessões, índices e timeline têm mensagens e nova tentativa;
não são convertidas em listas vazias. Notas originais continuam sendo apresentadas sem alteração.
