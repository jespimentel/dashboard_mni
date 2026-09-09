import json
from datetime import datetime, timezone

from db import get_connection
from numero_processo import formatar

SAIDA = "index.html"

# Sequência exibida na tabela "por processo" (Distribuído e Acórdão suprimidos a pedido).
# "Ajuizamento" não é uma regra de relevância — vem direto de processos.data_ajuizamento.
SEQUENCIA_TABELA = [
    "Ajuizamento",
    "Relatório Final Juntado",
    "Denúncia Juntada",
    "Resposta à Acusação Juntada",
    "Audiência Realizada Exitosa",
    "Apelação/Razões Juntada",
    "Contrarrazões Juntada",
]


def _coletar_dados():
    conn = get_connection()

    kpis = {
        "total": conn.execute("SELECT COUNT(*) c FROM processos").fetchone()["c"],
        "ativos": conn.execute("SELECT COUNT(*) c FROM processos WHERE status='ativo'").fetchone()["c"],
        "consultados": conn.execute(
            "SELECT COUNT(*) c FROM processos WHERE hash_estado IS NOT NULL"
        ).fetchone()["c"],
        "pendentes": conn.execute(
            "SELECT COUNT(*) c FROM processos WHERE hash_estado IS NULL"
        ).fetchone()["c"],
        "com_erro": conn.execute(
            "SELECT COUNT(*) c FROM processos WHERE ultimo_erro IS NOT NULL"
        ).fetchone()["c"],
        "inqueritos_policiais": conn.execute(
            """
            SELECT COUNT(*) c FROM processos p
            JOIN tabela_cnj tc ON tc.codigo = p.classe_processual AND tc.tipo = 'C'
            WHERE tc.nome = 'Inquérito Policial'
            """
        ).fetchone()["c"],
        "movimentos": conn.execute("SELECT COUNT(*) c FROM movimentos").fetchone()["c"],
    }

    eventos_rows = conn.execute(
        """
        SELECT m.numero_processo, r.rotulo, m.data_hora
        FROM movimentos_relevantes mr
        JOIN movimentos m ON m.id = mr.movimento_id
        JOIN regras_relevancia r ON r.id = mr.regra_id
        """
    ).fetchall()

    def chave_data(dh):
        try:
            return datetime.strptime(dh, "%d/%m/%Y %H:%M:%S")
        except ValueError:
            return datetime.min

    metadados_rows = conn.execute(
        """
        SELECT p.numero, p.classe_processual, tc.nome AS classe_nome,
               p.assunto_codigo, ta.nome AS assunto_nome,
               p.vara, p.municipio_ibge, p.codigo_localidade,
               p.situacao, p.data_ajuizamento
        FROM processos p
        LEFT JOIN tabela_cnj tc ON tc.codigo = p.classe_processual AND tc.tipo = 'C'
        LEFT JOIN tabela_cnj ta ON ta.codigo = p.assunto_codigo AND ta.tipo = 'A'
        WHERE p.hash_estado IS NOT NULL
        """
    ).fetchall()
    metadados = {row["numero"]: dict(row) for row in metadados_rows}

    conn.close()

    por_processo_etapas = {}
    for row in eventos_rows:
        numero = row["numero_processo"]
        por_processo_etapas.setdefault(numero, {})
        atual = por_processo_etapas[numero].get(row["rotulo"])
        if atual is None or chave_data(row["data_hora"]) < chave_data(atual):
            por_processo_etapas[numero][row["rotulo"]] = row["data_hora"]

    def chave_data_dia(d):
        try:
            return datetime.strptime(d, "%d/%m/%Y")
        except (ValueError, TypeError):
            return datetime.max  # sem data de ajuizamento vai para o fim

    progresso = []
    for numero, meta in metadados.items():
        etapas_do_processo = por_processo_etapas.get(numero, {})
        ajuizamento = meta["data_ajuizamento"]
        etapas_linha = [ajuizamento] + [
            etapas_do_processo.get(rotulo) for rotulo in SEQUENCIA_TABELA[1:]
        ]
        progresso.append({
            "numero": formatar(numero),
            "classe_processual": meta["classe_nome"] or meta["classe_processual"],
            "assunto_codigo": meta["assunto_nome"] or meta["assunto_codigo"],
            "vara": meta["vara"],
            "municipio_ibge": meta["municipio_ibge"],
            "situacao": meta["situacao"],
            "data_ajuizamento": ajuizamento,
            "etapas": etapas_linha,
        })

    progresso.sort(key=lambda p: chave_data_dia(p["data_ajuizamento"]))

    return kpis, progresso


def gerar():
    kpis, progresso = _coletar_dados()
    gerado_em = datetime.now(timezone.utc).strftime("%d/%m/%Y %H:%M UTC")

    html = HTML_TEMPLATE.replace("__GERADO_EM__", gerado_em)
    html = html.replace("__DADOS_JSON__", json.dumps(
        {"kpis": kpis, "progresso": progresso, "etapas": SEQUENCIA_TABELA},
        ensure_ascii=False,
    ))

    with open(SAIDA, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"dashboard gerado em {SAIDA}")


HTML_TEMPLATE = """<!doctype html>
<html lang="pt-br">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Painel MNI — TJSP</title>
<style>
  :root {
    --bg: #f4f5f7;
    --surface: #ffffff;
    --border: #e1e4e8;
    --text: #1f2933;
    --text-muted: #5a6472;
    --navy: #0f2b46;
    --navy-light: #1c4267;
    --accent: #2f6690;
    --accent-soft: #e7eef3;
    --ok: #2f7d4f;
    --warn: #a15c07;
    --danger: #a3312a;
  }
  * { box-sizing: border-box; }
  body {
    margin: 0;
    background: var(--bg);
    color: var(--text);
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Arial, sans-serif;
  }
  header {
    background: var(--navy);
    color: #fff;
    padding: 24px 32px;
    display: flex;
    justify-content: space-between;
    align-items: baseline;
    flex-wrap: wrap;
    gap: 8px;
  }
  header h1 { font-size: 20px; margin: 0; font-weight: 600; letter-spacing: 0.2px; }
  header .sub { color: #c9d6e2; font-size: 13px; }
  main { padding: 24px 32px 48px; max-width: 1400px; margin: 0 auto; }

  .kpis {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
    gap: 12px;
    margin-bottom: 28px;
  }
  .kpi {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 16px 18px;
  }
  .kpi .valor { font-size: 26px; font-weight: 700; color: var(--navy); }
  .kpi .rotulo { font-size: 12.5px; color: var(--text-muted); margin-top: 4px; }
  .kpi.warn .valor { color: var(--warn); }
  .kpi.danger .valor { color: var(--danger); }

  section {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 20px 22px;
    margin-bottom: 24px;
  }
  section h2 {
    font-size: 15px;
    margin: 0 0 16px;
    color: var(--navy);
    font-weight: 600;
  }

  table { width: 100%; border-collapse: collapse; font-size: 13.5px; }
  thead th {
    text-align: left;
    color: var(--text-muted);
    font-weight: 600;
    font-size: 11.5px;
    text-transform: uppercase;
    letter-spacing: 0.04em;
    padding: 8px 10px 4px;
    border-bottom: none;
  }
  tbody td { padding: 9px 10px; border-bottom: 1px solid var(--border); }
  tbody tr:hover { background: var(--accent-soft); }
  .numero-processo { font-variant-numeric: tabular-nums; color: var(--text); }
  .vazio { color: var(--text-muted); font-size: 13px; padding: 16px 0; text-align: center; }
  .contador-tabela { color: var(--text-muted); font-size: 12.5px; margin-bottom: 10px; }

  .tabela-scroll { overflow-x: auto; }
  table.progresso { min-width: 1350px; }
  table.progresso th.etapa, table.progresso td.etapa { text-align: center; white-space: nowrap; }
  .etapa-atingida { color: var(--navy-light); font-weight: 600; font-size: 12px; }
  .etapa-atingida .ponto { color: var(--ok); margin-right: 4px; }
  .etapa-pendente { color: #c3c9d1; }
  td.info-processo { white-space: nowrap; }
  .th-rotulo { margin-bottom: 6px; }
  .filtro-coluna {
    display: block;
    width: 100%;
    font-size: 10.5px;
    font-weight: 500;
    text-transform: none;
    letter-spacing: 0;
    padding: 3px 4px;
    border: 1px solid var(--border);
    border-radius: 4px;
    color: var(--text);
    background: var(--surface);
  }
  thead tr.linha-filtros th { padding-top: 0; padding-bottom: 8px; border-bottom: 2px solid var(--border); }
  .situacao-tag {
    display: inline-block;
    padding: 2px 8px;
    border-radius: 999px;
    font-size: 11px;
    font-weight: 600;
    white-space: nowrap;
  }
  .situacao-Em-andamento { background: var(--accent-soft); color: var(--navy-light); }
  .situacao-Suspenso { background: #fbeed9; color: var(--warn); }
  .situacao-Extinto { background: #eef0f2; color: var(--text-muted); }
  .situacao-Julgado { background: #e3f0e7; color: var(--ok); }
  .situacao-Pendente-de-Julgamento { background: #f4e9df; color: var(--warn); }
  .situacao-outra { background: #eef0f2; color: var(--text-muted); }

  footer { text-align: center; color: var(--text-muted); font-size: 12px; padding: 20px; }
</style>
</head>
<body>

<header>
  <h1>Painel de Monitoramento MNI — TJSP</h1>
  <div class="sub">Gerado em __GERADO_EM__</div>
</header>

<main>
  <div class="kpis" id="kpis"></div>

  <section>
    <h2>Sequência de atos por processo</h2>
    <div class="contador-tabela" id="contador-progresso"></div>
    <div class="tabela-scroll">
      <table class="progresso">
        <thead>
          <tr id="cabecalho-progresso"></tr>
          <tr class="linha-filtros" id="linha-filtros-progresso"></tr>
        </thead>
        <tbody id="tabela-progresso"></tbody>
      </table>
    </div>
    <div class="vazio" id="vazio-progresso" style="display:none;">Nenhum processo encontrado para o filtro atual.</div>
  </section>
</main>

<footer>Fonte: base SQLite local do projeto MNI — hash_estado / consultarAlteracao / consultarProcesso (TJSP)</footer>

<script>
const DADOS = __DADOS_JSON__;

function renderKpis() {
  const k = DADOS.kpis;
  const itens = [
    { valor: k.total, rotulo: 'Processos monitorados' },
    { valor: k.ativos, rotulo: 'Ativos' },
    { valor: k.consultados, rotulo: 'Já consultados' },
    { valor: k.pendentes, rotulo: 'Pendentes de 1ª consulta', classe: k.pendentes > 0 ? 'warn' : '' },
    { valor: k.com_erro, rotulo: 'Com último erro', classe: k.com_erro > 0 ? 'danger' : '' },
    { valor: k.inqueritos_policiais, rotulo: 'Inquéritos Policiais' },
    { valor: k.movimentos, rotulo: 'Movimentos coletados' },
  ];
  document.getElementById('kpis').innerHTML = itens.map(i => `
    <div class="kpi ${i.classe || ''}">
      <div class="valor">${i.valor.toLocaleString('pt-BR')}</div>
      <div class="rotulo">${i.rotulo}</div>
    </div>
  `).join('');
}

const ROTULOS_CURTOS = {
  'Ajuizamento': 'Ajuizamento',
  'Denúncia Juntada': 'Denúncia',
  'Resposta à Acusação Juntada': 'Resp. Acusação',
  'Relatório Final Juntado': 'Relatório Final',
  'Audiência Realizada Exitosa': 'Audiência',
  'Apelação/Razões Juntada': 'Apelação',
  'Contrarrazões Juntada': 'Contrarrazões',
};

const SITUACOES_COM_ESTILO = ['Em andamento', 'Suspenso', 'Extinto', 'Julgado', 'Pendente de Julgamento'];

function classeSituacao(situacao) {
  if (situacao && SITUACOES_COM_ESTILO.includes(situacao)) {
    return 'situacao-' + situacao.replace(/\\s+/g, '-');
  }
  return 'situacao-outra';
}

// Colunas fixas: cada uma sabe extrair seu valor e construir seu próprio filtro.
const COLUNAS_FIXAS = [
  {
    chave: 'numero', rotulo: 'Processo', tipo: 'texto',
    valor: p => p.numero,
    exibir: p => `<td class="numero-processo">${p.numero}</td>`,
  },
  {
    chave: 'classe_processual', rotulo: 'Classe', tipo: 'select',
    valor: p => p.classe_processual,
    exibir: p => `<td class="info-processo">${p.classe_processual ?? '—'}</td>`,
  },
  {
    chave: 'assunto_codigo', rotulo: 'Assunto', tipo: 'select',
    valor: p => p.assunto_codigo,
    exibir: p => `<td class="info-processo">${p.assunto_codigo ?? '—'}</td>`,
  },
  {
    chave: 'vara', rotulo: 'Vara', tipo: 'select',
    valor: p => p.vara,
    exibir: p => `<td class="info-processo">${p.vara || '—'}</td>`,
  },
  {
    chave: 'municipio_ibge', rotulo: 'Município (IBGE)', tipo: 'select',
    valor: p => p.municipio_ibge,
    exibir: p => `<td class="info-processo">${p.municipio_ibge ?? '—'}</td>`,
  },
  {
    chave: 'situacao', rotulo: 'Situação', tipo: 'select',
    valor: p => p.situacao,
    exibir: p => p.situacao
      ? `<td class="info-processo"><span class="situacao-tag ${classeSituacao(p.situacao)}">${p.situacao}</span></td>`
      : `<td class="info-processo"><span class="etapa-pendente">—</span></td>`,
  },
];

const FILTROS = {}; // chave da coluna -> valor selecionado/digitado

function opcoesOrdenadas(valores) {
  return [...new Set(valores.filter(v => v !== null && v !== undefined && v !== ''))]
    .sort((a, b) => String(a).localeCompare(String(b), 'pt-BR', { numeric: true }));
}

function renderCabecalhoProgresso() {
  const thRotulos = COLUNAS_FIXAS.map(c => `<th><div class="th-rotulo">${c.rotulo}</div></th>`).concat(
    DADOS.etapas.map(e => `<th class="etapa"><div class="th-rotulo" title="${e}">${ROTULOS_CURTOS[e] || e}</div></th>`)
  );
  document.getElementById('cabecalho-progresso').innerHTML = thRotulos.join('');

  const thFiltrosFixos = COLUNAS_FIXAS.map(c => {
    if (c.tipo === 'texto') {
      return `<th><input class="filtro-coluna" data-coluna="${c.chave}" type="text" placeholder="Filtrar..."></th>`;
    }
    const opcoes = opcoesOrdenadas(DADOS.progresso.map(c.valor));
    return `<th><select class="filtro-coluna" data-coluna="${c.chave}">
      <option value="">Todos</option>
      ${opcoes.map(o => `<option value="${o}">${o}</option>`).join('')}
    </select></th>`;
  });

  const thFiltrosEtapas = DADOS.etapas.map((e, i) => {
    if (i === 0) {
      const anos = opcoesOrdenadas(DADOS.progresso.map(p => (p.etapas[0] || '').slice(-4)));
      return `<th><select class="filtro-coluna" data-etapa-ano="${e}">
        <option value="">Todos</option>
        ${anos.map(a => `<option value="${a}">${a}</option>`).join('')}
      </select></th>`;
    }
    return `<th><select class="filtro-coluna" data-etapa="${e}">
      <option value="">Todos</option>
      <option value="atingiu">Atingiu</option>
      <option value="pendente">Pendente</option>
    </select></th>`;
  });

  const linha = document.getElementById('linha-filtros-progresso');
  linha.innerHTML = thFiltrosFixos.concat(thFiltrosEtapas).join('');

  linha.querySelectorAll('[data-coluna]').forEach(el => {
    const evento = el.tagName === 'INPUT' ? 'input' : 'change';
    el.addEventListener(evento, () => {
      FILTROS['coluna:' + el.dataset.coluna] = el.value;
      renderProgresso();
    });
  });
  linha.querySelectorAll('[data-etapa]').forEach(sel => {
    sel.addEventListener('change', () => {
      FILTROS['etapa:' + sel.dataset.etapa] = sel.value;
      renderProgresso();
    });
  });
  linha.querySelectorAll('[data-etapa-ano]').forEach(sel => {
    sel.addEventListener('change', () => {
      FILTROS['etapa-ano:' + sel.dataset.etapaAno] = sel.value;
      renderProgresso();
    });
  });
}

function passaFiltros(p) {
  for (const coluna of COLUNAS_FIXAS) {
    const filtro = FILTROS['coluna:' + coluna.chave];
    if (!filtro) continue;
    const valor = coluna.valor(p);
    if (coluna.tipo === 'texto') {
      if (!String(valor || '').toLowerCase().includes(filtro.toLowerCase())) return false;
    } else if (String(valor ?? '') !== filtro) {
      return false;
    }
  }
  for (let i = 1; i < DADOS.etapas.length; i++) {
    const filtro = FILTROS['etapa:' + DADOS.etapas[i]];
    if (!filtro) continue;
    const atingiu = !!p.etapas[i];
    if (filtro === 'atingiu' && !atingiu) return false;
    if (filtro === 'pendente' && atingiu) return false;
  }
  const filtroAno = FILTROS['etapa-ano:' + DADOS.etapas[0]];
  if (filtroAno && (p.etapas[0] || '').slice(-4) !== filtroAno) return false;
  return true;
}

function renderProgresso() {
  const filtrados = DADOS.progresso.filter(passaFiltros);

  document.getElementById('contador-progresso').textContent =
    `${filtrados.length.toLocaleString('pt-BR')} de ${DADOS.progresso.length.toLocaleString('pt-BR')} processos`;

  const tbody = document.getElementById('tabela-progresso');
  const vazio = document.getElementById('vazio-progresso');
  if (!filtrados.length) {
    tbody.innerHTML = '';
    vazio.style.display = 'block';
    return;
  }
  vazio.style.display = 'none';

  tbody.innerHTML = filtrados.slice(0, 500).map(p => {
    const celulasFixas = COLUNAS_FIXAS.map(c => c.exibir(p)).join('');
    const celulasEtapas = p.etapas.map(data => {
      if (data) {
        return `<td class="etapa"><span class="etapa-atingida"><span class="ponto">●</span>${data.slice(0, 10)}</span></td>`;
      }
      return `<td class="etapa"><span class="etapa-pendente">—</span></td>`;
    }).join('');
    return `<tr>${celulasFixas}${celulasEtapas}</tr>`;
  }).join('');
}

renderKpis();
renderCabecalhoProgresso();
renderProgresso();
</script>

</body>
</html>
"""

if __name__ == "__main__":
    gerar()
