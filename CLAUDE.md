# Projeto MNI — Monitoramento de processos TJSP

Sistema para manter atualizada uma base de ~4.000 processos via webservice
MNI 2.2.2 do TJSP (`esaj.tjsp.jus.br/mniws/servico-intercomunicacao-2.2.2/intercomunicacao`),
usando `consultarAlteracao` (hash) como varredura barata e `consultarProcesso`
apenas para os processos que mudaram.

## Regras de arquitetura (invariantes)

- SQLite é a base de verdade. Excel/planilha é apenas exportação eventual, nunca estado.
- Chave canônica de processo: 20 dígitos, sem formatação. Normalizar na porta de
  entrada (`re.sub(r'\D', '', numero)`) e validar dígito verificador (ISO 7064, MOD 97-10).
- UPSERT, nunca DELETE + INSERT na tabela `processos`. Apagar destrói `hash_estado`
  e histórico.
- `hash_estado IS NULL` é o marcador de processo novo — não usar flag separada.
  Processo novo vai direto para `consultarProcesso` completo (não passa pelo
  `consultarAlteracao`, que não tem com o que comparar).
- Backfill de processos novos em lotes limitados por execução
  (`WHERE hash_estado IS NULL LIMIT 500`), nunca tudo de uma vez.
- `carga.py` pode receber listas parciais (ex.: só os processos vistos num
  mês). Processo ausente da carga NUNCA é marcado `inativo` — a carga só
  insere/atualiza quem está no arquivo. Situação real do processo (incluindo
  extinção) vem da própria API MNI e fica em `processos.situacao`
  (`ingest.py`, campo `situacaoProcesso`), nunca inferida por ausência.
- Movimentos: chave única (`identificadorMovimento` do MNI se existir, senão
  SHA-256 de `numero + data_hora + codigo_nacional + complemento`) com
  `INSERT OR IGNORE`, para tornar o worker seguro para reexecução.
- Regras de relevância ("o que é andamento relevante") ficam em tabela/dado
  (`regras_relevancia`), nunca em `if` no código.
- Erro em um processo não aborta o lote inteiro: registra em `ultimo_erro` e
  segue. Circuit breaker: se >30% do lote falhar, aborta a rodada (provável
  indisponibilidade do serviço TJSP) e não grava resultado parcial ruidoso.
- Reaproveitar `SqliteCache` do zeep (resolvido em conversa anterior sobre
  lentidão no Colab) para não refazer o download dos XSD a cada execução.
  Instanciar o client do zeep uma única vez por rodada.
- `consultarProcesso`: sempre `movimentos=true`, `documentos=false` — sem isso
  o payload explode.
- `classe_processual` e `assunto_codigo` são códigos CNJ crus em `processos`;
  o nome (para exibição) vem de `tabela_cnj`, cache local populado sob
  demanda a partir do SGT WebService do CNJ
  (`https://www.cnj.jus.br/sgt/sgt_ws.php?wsdl`,
  `getArrayDetalhesItemPublicoWS`) via `backfill_tabela_cnj.py`. Nunca
  hardcodear a tradução código→nome no código Python — mesma lógica de
  `regras_relevancia` (dado, não `if`).

## Confirmado contra o WSDL/serviço real

- `consultarAlteracao(idConsultante, senhaConsultante, numeroProcesso)` é uma
  chamada por processo (não aceita lote) e retorna `sucesso`, `mensagem`,
  `hashCabecalho`, `hashMovimentacoes`, `hashDocumentos` — sem `dataReferencia`.
  `hash_estado` gravado em `processos` é o SHA-256 da concatenação dos três
  hashes (`ingest.combinar_hashes`), para comparação direta entre rodadas.
- Primeira carga (`consultarProcesso` sem `dataReferencia`) traz o histórico
  completo de movimentos.

## Pendências / a confirmar

- Comportamento do serviço para número inexistente/sigiloso (casos de borda
  que hoje caem no `try/except` genérico dos workers e só gravam
  `ultimo_erro`).

## Convenções gerais

- Não gerar arquivos `.docx`/`.pdf`/`.xlsx` sem pedido explícito.
- Código em Python, objetivo e sem comentários desnecessários.
