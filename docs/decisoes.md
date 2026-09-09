# Decisões de arquitetura — Projeto MNI

## 001 — SQLite em vez de planilha Excel como base de estado

Planilha como estado dá problema previsível: arquivo travado enquanto aberto,
corrupção em escrita interrompida, ausência de chave única, fórmulas que
quebram quando a linha se desloca, e crescimento para dezenas de milhares de
linhas de movimentos.

Decisão: SQLite como base de verdade (um único arquivo `.db`, zero
infraestrutura, transacional). Excel vira saída regenerada a cada rodada —
relatório, não banco. Se algo der errado, basta rodar de novo.

## 002 — Varredura em duas camadas (consultarAlteracao + consultarProcesso)

Sem separar detecção de coleta, o job diário de 4.000 processos fica
inviável em tempo e em educação com o servidor do TJSP.

Decisão:
1. Varredura barata — `consultarAlteracao` em lote, comparando hash/token de
   estado guardado com o retorno.
2. Coleta cara — `consultarProcesso` (com `movimentos=true`,
   `documentos=false`) apenas para os que acusaram alteração. Estimativa:
   3–8% do acervo por dia (120–320 chamadas em vez de 4.000).

Ressalva: os nomes exatos dos campos de retorno de `consultarAlteracao`
(hash, dataReferencia, ou os dois) e se a operação aceita lote não estavam
confirmados — recomendado piloto com ~50 processos antes de escalar.

## 003 — `hash_estado NULL` como marcador de processo novo

Em vez de uma flag "é novo" separada, o estado nulo da coluna `hash_estado`
já diz tudo ao worker: se é NULL, pular `consultarAlteracao` (não há com o
que comparar) e ir direto ao `consultarProcesso` completo para semear a base.

Consequência: a primeira carga custa 4.000 consultas completas, que não
cabem numa única rodada. Backfill em lotes limitados
(`WHERE hash_estado IS NULL LIMIT 500`), drenando ao longo de vários dias.

## 004 — UPSERT, nunca DELETE + INSERT

Apagar e reinserir destruiria o `hash_estado` (fazendo tudo parecer novo na
rodada seguinte) e o histórico de movimentos já coletados.

Decisão: `INSERT ... ON CONFLICT(numero) DO UPDATE` — processo repetido no
CSV só atualiza `ultima_carga` (e ressuscita se estava inativo); processo
novo entra com `hash_estado` nulo.

## 005 — Inativação nunca inferida por ausência na carga (revisado)

Versão original desta decisão: processo que desaparecesse do CSV/TXT de
carga era marcado `status = 'inativo'`. Errado — assume que toda carga
representa a lista completa e atual do acervo. Na prática a carga pode ser
parcial (ex.: só os processos vistos num mês específico); tratar ausência
como sinal de arquivamento inativaria processos que continuam ativos e
simplesmente não estavam naquele arquivo.

Decisão revisada: `carga.py` nunca inativa por ausência — só insere
processo novo e atualiza `ultima_carga` de quem já existe. Situação real do
processo (inclusive extinção) vem da própria API MNI, gravada em
`processos.situacao` (`ingest.py`, `situacaoProcesso` de
`dadosBasicos.outroParametro`) a cada `consultarProcesso`. `status` continua
existindo no schema como campo administrativo (`ativo`/`inativo`), mas hoje
nada o define como `inativo` automaticamente — seria uma ação deliberada e
separada, não um efeito colateral de carga.

## 006 — Regras de relevância como dado

"Andamento relevante" definido como `if` no código exige deploy a cada
ajuste. Decisão: tabela `regras_relevancia` (`codigo_cnj | padrao_texto |
rotulo | prioridade`), permitindo adicionar um tipo de andamento a
acompanhar como uma linha nova, não uma alteração de código.

## 007 — Chave canônica de processo

Formatos variados de entrada (com pontuação, com espaço, com BOM) fariam o
mesmo processo entrar múltiplas vezes se comparado como string crua.

Decisão: normalizar para 20 dígitos na porta de entrada e validar dígito
verificador (ISO 7064, MOD 97-10) antes de gravar. A forma formatada
(NNNNNNN-DD.AAAA.J.TR.OOOO) é derivada só na exportação, nunca armazenada
como chave.

## 008 — Não migração de contexto entre claude.ai e Claude Code

O histórico de conversa em claude.ai não migra para o Claude Code (VS Code,
CLI ou desktop) — cada ambiente mantém sessões próprias. Por isso as decisões
de arquitetura foram formalizadas em `CLAUDE.md` (regras, lidas
automaticamente a cada sessão do Claude Code) e neste arquivo (raciocínio,
consultado quando o assunto voltar), em vez de depender de continuidade de
chat.

## 009 — Um `mni.db` por rol de processos, não um reset do existente

Compartilhar a aplicação com alguém que acompanha um rol de processos
diferente não deve significar apagar ou reaproveitar o `mni.db` de quem já
usa o sistema — isso destruiria `hash_estado` e histórico de movimentos já
coletados (contrariaria a decisão 004/005).

Decisão: cada pessoa/rol tem seu próprio `mni.db`, criado do zero
(`schema.sql` via `db.py`) e populado com `carga.py` a partir da lista dela.
O `.gitignore` mantém `mni.db`, `.env`, `processos.txt` e `index.html` fora
do repositório, então clonar o código não traz dados de ninguém junto;
`.env.example` documenta as variáveis exigidas sem expor credenciais. Passo a
passo em `README.md` § "Compartilhar com outro rol de processos".

Nota: `processos.txt` foi versionado por engano na estrutura inicial do
projeto (commit `314ed94`) — 8.463 números de processo ficaram públicos no
GitHub antes desta regra existir na prática, não só no papel. Removido do
controle de versão depois (`git rm --cached`), mas permanece no histórico
antigo do git; reescrever histórico (`git filter-repo`/BFG) é uma decisão
separada, não tomada aqui.

## 010 — `worker_alteracao.py` parar de varrer `situacao = 'Extinto'` (revertida)

Tentativa: já que `situacao` vem da API, parecia desperdício continuar
chamando `consultarAlteracao` em processo extinto, já que "o estado não muda
mais". Premissa falsa: um processo extinto pode reabrir (embargos, recurso,
reautuação), e é exatamente o `consultarAlteracao` — a varredura barata —
quem detectaria isso via mudança de hash. Filtrar por `situacao` antes dessa
chamada eliminava o próprio mecanismo de detecção da reabertura, congelando
o processo como extinto para sempre no banco.

Decisão revertida: `worker_alteracao.py` volta a varrer todo `status =
'ativo'` com `hash_estado IS NOT NULL`, sem filtrar por `situacao`. O custo
de manter processos extintos na varredura barata é aceitável — é uma
chamada por processo, sem `consultarProcesso` completo — e é o preço de não
perder reaberturas silenciosamente.

## 011 — Tradução de classe/assunto via cache do SGT WebService do CNJ

`classe_processual` e `assunto_codigo` (vindos do MNI) são apenas códigos
numéricos — inúteis para leitura direta no dashboard. Primeira tentativa foi
popular uma tabela local a partir das Tabelas Processuais Unificadas do CNJ,
baixadas como `.xlsx` do site do CNJ; os arquivos vieram com corrupção de
codificação (bytes de texto quebrados, inclusive resíduos do escape
`_xHHHH_` do Excel para caractere inválido), tornando arriscado extrair
nomes confiáveis por reconstrução de bytes.

Decisão: usar o SGT WebService público do CNJ
(`https://www.cnj.jus.br/sgt/sgt_ws.php?wsdl`, operação
`getArrayDetalhesItemPublicoWS(codigo, tipo)`, `tipo` = `C` (classe) ou `A`
(assunto)) como fonte de verdade — mesmo padrão já usado para o MNI (webservice
+ client zeep singleton + cache local em SQLite). Tabela `tabela_cnj`
(`codigo`, `tipo`, `nome`, `codigo_pai`, `situacao`, `atualizado_em`) é
populada sob demanda por `backfill_tabela_cnj.py`, só para os códigos que
aparecem em `processos` e ainda não estão cacheados — evita varrer a tabela
CNJ inteira (dezenas de milhares de itens) quando só uma fração aparece no
acervo monitorado. `generate_dashboard.py` faz `LEFT JOIN` com `tabela_cnj`
e cai para o código cru se o nome ainda não foi cacheado.
