-- Schema do sistema de monitoramento de processos TJSP via webservice MNI 2.2.2
-- Base de verdade: SQLite. Excel/planilha é apenas exportação eventual, nunca estado.

PRAGMA foreign_keys = ON;

-- ============================================================
-- processos: estado de monitoramento de cada processo
-- ============================================================
CREATE TABLE IF NOT EXISTS processos (
    numero              TEXT PRIMARY KEY,      -- 20 dígitos, sem formatação (chave canônica)
    hash_estado         TEXT,                  -- NULL = nunca consultado (processo novo)
    ultima_consulta     TEXT,                  -- timestamp da última consulta bem-sucedida ao MNI
    ultimo_erro         TEXT,                  -- mensagem do último erro, se houver
    status              TEXT NOT NULL DEFAULT 'ativo',  -- 'ativo' | 'inativo'
    primeira_carga      TEXT NOT NULL,         -- timestamp da primeira vez que apareceu num CSV
    ultima_carga        TEXT NOT NULL,         -- timestamp da última vez que apareceu num CSV
    classe_processual   INTEGER,               -- código CNJ (tabela unificada), sem tradução local
    assunto_codigo      INTEGER,               -- código CNJ do assunto principal, sem tradução local
    vara                TEXT,                  -- dadosBasicos.orgaoJulgador.nomeOrgao (já textual)
    municipio_ibge      INTEGER,               -- dadosBasicos.orgaoJulgador.codigoMunicipioIBGE
    codigo_localidade   TEXT,                  -- código de foro/comarca do TJSP
    situacao            TEXT,                  -- dadosBasicos.outroParametro['situacaoProcesso']
    data_ajuizamento    TEXT                   -- formatada DD/MM/AAAA
);

CREATE INDEX IF NOT EXISTS idx_processos_status ON processos(status);
CREATE INDEX IF NOT EXISTS idx_processos_hash_null ON processos(numero) WHERE hash_estado IS NULL;

-- ============================================================
-- movimentos: andamentos coletados de cada processo
-- ============================================================
CREATE TABLE IF NOT EXISTS movimentos (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    numero_processo     TEXT NOT NULL REFERENCES processos(numero),
    data_hora           TEXT NOT NULL,      -- formatada DD/MM/AAAA HH:MM:SS
    codigo_nacional     TEXT,               -- código CNJ do movimento, se houver
    descricao           TEXT,
    complemento         TEXT,               -- já limpo de \r\n embutidos
    data_captura        TEXT NOT NULL,      -- quando o worker coletou este registro
    chave_unica         TEXT NOT NULL UNIQUE  -- identificadorMovimento do MNI, ou
                                               -- SHA-256(numero + data_hora + codigo_nacional + complemento)
);

CREATE INDEX IF NOT EXISTS idx_movimentos_processo ON movimentos(numero_processo);
CREATE INDEX IF NOT EXISTS idx_movimentos_data ON movimentos(data_hora);

-- ============================================================
-- regras_relevancia: o que conta como "andamento relevante"
-- Dado, não código -- nova regra = nova linha, não deploy.
-- ============================================================
CREATE TABLE IF NOT EXISTS regras_relevancia (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    codigo_cnj      TEXT,           -- código nacional exato, se aplicável
    padrao_texto    TEXT,           -- regex aplicada à descrição/complemento (ex.: 'mandad')
    rotulo          TEXT NOT NULL,  -- rótulo amigável (ex.: 'Mandado')
    prioridade      INTEGER NOT NULL DEFAULT 0,
    ativo           INTEGER NOT NULL DEFAULT 1
);

-- ============================================================
-- movimentos_relevantes: cruzamento movimento x regra disparada
-- ============================================================
CREATE TABLE IF NOT EXISTS movimentos_relevantes (
    movimento_id    INTEGER NOT NULL REFERENCES movimentos(id),
    regra_id        INTEGER NOT NULL REFERENCES regras_relevancia(id),
    PRIMARY KEY (movimento_id, regra_id)
);

-- ============================================================
-- cargas: log de cada importação de CSV/TXT com a lista de processos
-- ============================================================
CREATE TABLE IF NOT EXISTS cargas (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    arquivo         TEXT NOT NULL,
    hash_arquivo    TEXT NOT NULL,   -- SHA-256 do conteúdo, detecta recarga idêntica
    timestamp       TEXT NOT NULL,
    lidos           INTEGER NOT NULL DEFAULT 0,
    invalidos       INTEGER NOT NULL DEFAULT 0,
    novos           INTEGER NOT NULL DEFAULT 0,
    repetidos       INTEGER NOT NULL DEFAULT 0,
    inativados      INTEGER NOT NULL DEFAULT 0
);

-- ============================================================
-- rejeitos: linhas do CSV/TXT que não puderam ser processadas
-- ============================================================
CREATE TABLE IF NOT EXISTS rejeitos (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    carga_id        INTEGER NOT NULL REFERENCES cargas(id),
    linha_original  TEXT NOT NULL,
    motivo          TEXT NOT NULL
);

-- ============================================================
-- execucoes: log de cada rodada do worker (consultarAlteracao / consultarProcesso)
-- ============================================================
CREATE TABLE IF NOT EXISTS execucoes (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    inicio          TEXT NOT NULL,
    fim             TEXT,
    varridos        INTEGER NOT NULL DEFAULT 0,
    alterados       INTEGER NOT NULL DEFAULT 0,
    erros           INTEGER NOT NULL DEFAULT 0,
    abortada        INTEGER NOT NULL DEFAULT 0,  -- 1 se o circuit breaker disparou
    observacao      TEXT
);
