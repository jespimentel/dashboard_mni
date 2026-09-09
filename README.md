# MNI — Monitoramento de processos TJSP

Sistema para manter atualizada uma base de processos via webservice MNI 2.2.2
do TJSP, usando `consultarAlteracao` (hash) como varredura barata e
`consultarProcesso` apenas para os processos que mudaram. Regras de
arquitetura e decisões estão em `CLAUDE.md` e `docs/decisoes.md`.

## Setup

```
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Copiar `.env.example` para `.env` e preencher:

```
cp .env.example .env
```

```
USUARIO_MNI=...
SENHA_MNI=...
```

Inicializar o banco (uma vez só):

```
python3 db.py
```

## Uso

**1. Carregar/atualizar a lista de processos** (a partir de um `.txt`/`.csv`,
um número de processo por linha):

```
python3 carga.py processos.txt
```

Faz UPSERT: processos novos entram com `hash_estado` nulo, repetidos só
atualizam `ultima_carga`. A lista pode ser parcial (ex.: só os processos
vistos num mês) — quem não aparece na carga não é tocado, nunca inativado
por ausência. Extinção real vem da própria API (campo `situacao`), não da
carga.

**2. Rodar o worker**

Processos nunca consultados (backfill, em lotes de 500 por execução):

```
python3 worker_novos.py
```

Repita até a contagem de `pendentes` (ver dashboard) chegar a zero.

Processos já consultados antes (varredura barata de alteração — só refaz a
consulta completa se o hash mudou):

```
python3 worker_alteracao.py
```

**3. Traduzir código de classe/assunto para nome**

```
python3 backfill_tabela_cnj.py
```

Consulta o SGT WebService do CNJ (`sgt_ws.php`) para os códigos de
`classe_processual`/`assunto_codigo` que aparecem em `processos` e ainda não
estão em cache, e grava em `tabela_cnj`. Rodar depois de cada worker que traga
processo novo.

**4. Marcar andamentos relevantes**

```
python3 aplicar_relevancia.py
```

Aplica as regras da tabela `regras_relevancia` sobre os movimentos ainda não
classificados. Rodar depois de cada worker.

**5. Ver o resultado**

Relatório em texto no terminal, de todos os processos ou de um só:

```
python3 relatorio_relevantes.py
python3 relatorio_relevantes.py 1503003-61.2025.8.26.0599
```

Dashboard visual (HTML local, autocontido, sem envio de dados a serviços
externos):

```
python3 generate_dashboard.py
open index.html
```

## Rotina do dia a dia

```
python3 carga.py processos.txt
python3 worker_novos.py        # repetir até pendentes = 0
python3 worker_alteracao.py
python3 backfill_tabela_cnj.py
python3 aplicar_relevancia.py
python3 generate_dashboard.py && open index.html
```

## Adicionar um novo tipo de andamento relevante

Editar a lista `REGRAS` em `seed_regras.py` e rodar de novo:

```
python3 seed_regras.py
```

Não requer alteração no worker — regras de relevância são dado, não código.

## Compartilhar com outro rol de processos

Para dar a base a outra pessoa com uma lista de processos diferente (sem
misturar com a sua), ela deve partir de um `mni.db` vazio, não do seu:

```
git clone <repo>          # mni.db, .env e processos.txt não vêm (.gitignore)
cp .env.example .env      # preencher com as credenciais MNI dela
python3 db.py             # cria mni.db vazio a partir do schema.sql
python3 seed_regras.py    # semeia regras_relevancia
python3 carga.py <lista_dela.txt>
python3 worker_novos.py   # repetir até pendentes = 0
```

Nenhum dado do seu `mni.db` é apagado nesse processo — cada pessoa mantém o
próprio banco local.

## Arquivos

| Arquivo | Função |
|---|---|
| `db.py` | inicializa o SQLite a partir de `schema.sql` |
| `schema.sql` | schema das tabelas (`processos`, `movimentos`, `regras_relevancia`, ...) |
| `numero_processo.py` | normalização e validação do número CNJ (dígito verificador) |
| `mni_client.py` | cliente zeep singleton, com cache dos XSD |
| `carga.py` | importa a lista de processos e faz UPSERT |
| `worker_novos.py` | backfill de processos nunca consultados |
| `worker_alteracao.py` | varredura de alteração dos processos já consultados |
| `ingest.py` | grava movimentos e atualiza `hash_estado` |
| `backfill_metadados.py` | migração pontual: preenche `classe_processual`/`situacao`/etc. de processos já consultados antes desses campos existirem |
| `cnj_client.py` | cliente zeep singleton do SGT WebService (classes/assuntos CNJ) |
| `backfill_tabela_cnj.py` | traduz códigos de classe/assunto para nome, cacheados em `tabela_cnj` |
| `seed_regras.py` | define as regras de relevância |
| `aplicar_relevancia.py` | aplica as regras sobre os movimentos coletados |
| `relatorio_relevantes.py` | relatório em texto dos andamentos relevantes |
| `generate_dashboard.py` | gera `index.html` |

`mni.db`, `zeep_cache.db` e `index.html` são gerados/estado local — não
versionados (ver `.gitignore`).
