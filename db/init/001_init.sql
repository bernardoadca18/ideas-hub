-- ideas-hub: schema inicial
-- Postgres + pgvector. Revisado para 1NF/2NF/3NF (ver notas no final).

CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pgcrypto; -- gen_random_uuid()

CREATE TYPE origem_ideia AS ENUM ('manual', 'trend', 'llm');
CREATE TYPE status_ideia AS ENUM ('rascunho', 'aprovada', 'rejeitada', 'em_roteiro', 'roteirizada', 'produzida');
CREATE TYPE fonte_trend AS ENUM ('google_trends', 'reddit_publico', 'youtube', 'rss');
CREATE TYPE status_trend AS ENUM ('pendente', 'aprovada', 'rejeitada');
CREATE TYPE status_roteiro AS ENUM ('rascunho', 'aprovado', 'rejeitado');
CREATE TYPE tipo_fonte_nicho AS ENUM ('reddit_publico', 'rss', 'youtube_categoria');

-- ---------------------------------------------------------------------------
CREATE TABLE nichos (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    slug VARCHAR(80) NOT NULL UNIQUE,
    nome VARCHAR(120) NOT NULL,
    descricao TEXT,
    prompt_ideacao TEXT NOT NULL,
    prompt_roteiro TEXT NOT NULL,
    categoria_google_trends VARCHAR(80),
    ativo BOOLEAN NOT NULL DEFAULT TRUE,
    criado_em TIMESTAMPTZ NOT NULL DEFAULT now(),
    atualizado_em TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Extraído de nichos para resolver violação de 1NF (subreddits/rss/youtube
-- eram um grupo repetitivo dentro de uma única coluna).
CREATE TABLE fontes_trend_nicho (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    nicho_id UUID NOT NULL REFERENCES nichos(id) ON DELETE CASCADE,
    tipo tipo_fonte_nicho NOT NULL,
    identificador VARCHAR(200) NOT NULL, -- ex: 'nome_subreddit', url do rss, categoria do youtube
    ativo BOOLEAN NOT NULL DEFAULT TRUE,
    criado_em TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (nicho_id, tipo, identificador)
);

CREATE TABLE trends_coletadas (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    nicho_id UUID NOT NULL REFERENCES nichos(id) ON DELETE CASCADE,
    fonte_trend_nicho_id UUID REFERENCES fontes_trend_nicho(id) ON DELETE SET NULL,
    termo_bruto VARCHAR(300) NOT NULL,
    fonte fonte_trend NOT NULL,
    status status_trend NOT NULL DEFAULT 'pendente',
    -- payload_raw fica JSONB de propósito: cada fonte devolve um formato
    -- diferente e normalizar em colunas fixas exigiria migração a cada
    -- fonte nova. Não compromete integridade nem escalabilidade.
    payload_raw JSONB NOT NULL DEFAULT '{}'::jsonb,
    coletado_em TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE ideias (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    nicho_id UUID REFERENCES nichos(id) ON DELETE SET NULL,
    origem origem_ideia NOT NULL,
    titulo VARCHAR(300) NOT NULL,
    descricao_breve TEXT,
    status status_ideia NOT NULL DEFAULT 'rascunho',
    eh_continuacao_de UUID REFERENCES ideias(id) ON DELETE SET NULL,
    numero_parte SMALLINT,
    embedding VECTOR(1024),
    fonte_trend_id UUID REFERENCES trends_coletadas(id) ON DELETE SET NULL,
    justificativa_llm TEXT,
    criado_em TIMESTAMPTZ NOT NULL DEFAULT now(),
    atualizado_em TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT chk_numero_parte CHECK (numero_parte IS NULL OR numero_parte > 1),
    CONSTRAINT chk_continuacao CHECK (
        (eh_continuacao_de IS NULL AND numero_parte IS NULL) OR
        (eh_continuacao_de IS NOT NULL AND numero_parte IS NOT NULL)
    )
);

CREATE TABLE roteiros (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    ideia_id UUID NOT NULL REFERENCES ideias(id) ON DELETE CASCADE,
    versao SMALLINT NOT NULL DEFAULT 1,
    estrutura JSONB NOT NULL, -- blocos narrativos, ganchos, CTA (consumido como unidade pelo serviço de voz)
    status status_roteiro NOT NULL DEFAULT 'rascunho',
    criado_em TIMESTAMPTZ NOT NULL DEFAULT now(),
    atualizado_em TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (ideia_id, versao)
);

-- ---------------------------------------------------------------------------
-- Índices
-- ---------------------------------------------------------------------------
CREATE INDEX idx_ideias_nicho ON ideias(nicho_id);
CREATE INDEX idx_ideias_status ON ideias(status);
CREATE INDEX idx_trends_nicho_status ON trends_coletadas(nicho_id, status);
CREATE INDEX idx_roteiros_ideia ON roteiros(ideia_id);
CREATE INDEX idx_fontes_nicho ON fontes_trend_nicho(nicho_id);

-- HNSW: melhor trade-off de recall/latência que ivfflat para esse volume
CREATE INDEX idx_ideias_embedding_hnsw ON ideias USING hnsw (embedding vector_cosine_ops);

-- ---------------------------------------------------------------------------
-- Trigger genérica de atualizado_em
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION set_atualizado_em()
RETURNS TRIGGER AS $$
BEGIN
  NEW.atualizado_em = now();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_nichos_atualizado BEFORE UPDATE ON nichos
    FOR EACH ROW EXECUTE FUNCTION set_atualizado_em();
CREATE TRIGGER trg_ideias_atualizado BEFORE UPDATE ON ideias
    FOR EACH ROW EXECUTE FUNCTION set_atualizado_em();
CREATE TRIGGER trg_roteiros_atualizado BEFORE UPDATE ON roteiros
    FOR EACH ROW EXECUTE FUNCTION set_atualizado_em();

-- ---------------------------------------------------------------------------
-- Notas de normalização:
-- 1NF: nenhuma coluna guarda lista/grupo repetitivo (subreddits/rss/youtube
--      viraram linhas em fontes_trend_nicho).
-- 2NF: todas as tabelas têm PK simples (UUID) -> dependência parcial não
--      se aplica.
-- 3NF: nenhum atributo não-chave depende de outro atributo não-chave.
--      payload_raw (JSONB) e estrutura (JSONB) são exceções deliberadas:
--      guardam dados semiestruturados heterogêneos por natureza, não
--      colunas que deveriam estar em outra tabela.
-- ---------------------------------------------------------------------------
