import hashlib
from datetime import datetime, timezone

from db import get_connection


def agora() -> str:
    return datetime.now(timezone.utc).isoformat()


def _formatar_data_hora(data_hora_mni: str) -> str:
    # formato MNI: AAAAMMDDHHMMSS
    dt = datetime.strptime(data_hora_mni, "%Y%m%d%H%M%S")
    return dt.strftime("%d/%m/%Y %H:%M:%S")


def _limpar(texto):
    if texto is None:
        return None
    return str(texto).replace("\r\n", " ").replace("\n", " ").strip()


def _codigo_e_descricao(mov: dict):
    nacional = mov.get("movimentoNacional")
    if nacional:
        return nacional.get("codigoNacional"), None
    local = mov.get("movimentoLocal")
    if local:
        return local.get("codigoPaiNacional"), local.get("descricao")
    return None, None


def _complemento(mov: dict):
    partes = [p for p in (mov.get("complemento") or []) if p]
    return _limpar("; ".join(partes)) if partes else None


def gravar_movimentos(conn, numero: str, movimentos: list) -> int:
    inseridos = 0
    ts = agora()
    for mov in movimentos or []:
        data_hora = _formatar_data_hora(mov["dataHora"])
        codigo_nacional, descricao_local = _codigo_e_descricao(mov)
        complemento = _complemento(mov)
        identificador = mov.get("identificadorMovimento")

        if identificador:
            chave_unica = f"{numero}:{identificador}"
        else:
            base = f"{numero}{data_hora}{codigo_nacional}{complemento}"
            chave_unica = hashlib.sha256(base.encode("utf-8")).hexdigest()

        cur = conn.execute(
            """
            INSERT OR IGNORE INTO movimentos
                (numero_processo, data_hora, codigo_nacional, descricao, complemento,
                 data_captura, chave_unica)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (numero, data_hora, codigo_nacional, descricao_local, complemento, ts, chave_unica),
        )
        if cur.rowcount:
            inseridos += 1
    return inseridos


def _formatar_data(data_mni):
    if not data_mni:
        return None
    return datetime.strptime(data_mni, "%Y%m%d%H%M%S").strftime("%d/%m/%Y")


def _situacao(dados_basicos: dict):
    for parametro in dados_basicos.get("outroParametro") or []:
        if parametro.get("nome") == "situacaoProcesso":
            return parametro.get("valor")
    return None


def extrair_dados_basicos(resultado: dict) -> dict:
    dados = resultado["processo"]["dadosBasicos"]
    orgao = dados.get("orgaoJulgador") or {}
    assuntos = dados.get("assunto") or []
    assunto_principal = next((a for a in assuntos if a.get("principal")), assuntos[0] if assuntos else {})

    return {
        "classe_processual": dados.get("classeProcessual"),
        "assunto_codigo": assunto_principal.get("codigoNacional") if assunto_principal else None,
        "vara": orgao.get("nomeOrgao"),
        "municipio_ibge": orgao.get("codigoMunicipioIBGE"),
        "codigo_localidade": dados.get("codigoLocalidade"),
        "situacao": _situacao(dados),
        "data_ajuizamento": _formatar_data(dados.get("dataAjuizamento")),
    }


def combinar_hashes(alteracao: dict) -> str:
    base = "{}|{}|{}".format(
        alteracao.get("hashCabecalho") or "",
        alteracao.get("hashMovimentacoes") or "",
        alteracao.get("hashDocumentos") or "",
    )
    return hashlib.sha256(base.encode("utf-8")).hexdigest()


def gravar_consulta_completa(numero: str, resultado: dict, hash_estado: str) -> int:
    conn = get_connection()
    try:
        movimentos = resultado["processo"].get("movimento") or []
        inseridos = gravar_movimentos(conn, numero, movimentos)
        dados_basicos = extrair_dados_basicos(resultado)
        ts = agora()
        conn.execute(
            """
            UPDATE processos
            SET hash_estado = ?, ultima_consulta = ?, ultimo_erro = NULL,
                classe_processual = ?, assunto_codigo = ?, vara = ?,
                municipio_ibge = ?, codigo_localidade = ?, situacao = ?, data_ajuizamento = ?
            WHERE numero = ?
            """,
            (
                hash_estado, ts,
                dados_basicos["classe_processual"], dados_basicos["assunto_codigo"],
                dados_basicos["vara"], dados_basicos["municipio_ibge"],
                dados_basicos["codigo_localidade"], dados_basicos["situacao"],
                dados_basicos["data_ajuizamento"], numero,
            ),
        )
        conn.commit()
        return inseridos
    finally:
        conn.close()


def gravar_erro(numero: str, mensagem: str) -> None:
    conn = get_connection()
    try:
        conn.execute(
            "UPDATE processos SET ultimo_erro = ? WHERE numero = ?",
            (mensagem, numero),
        )
        conn.commit()
    finally:
        conn.close()
