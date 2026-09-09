from datetime import datetime, timezone

from db import get_connection
from ingest import combinar_hashes, gravar_consulta_completa, gravar_erro
from mni_client import consultar_alteracao, consultar_processo

LOTE = 500
LIMITE_CIRCUIT_BREAKER = 0.3


def agora() -> str:
    return datetime.now(timezone.utc).isoformat()


def rodar() -> None:
    conn = get_connection()
    cur = conn.execute(
        "SELECT numero FROM processos WHERE hash_estado IS NULL AND status = 'ativo' LIMIT ?",
        (LOTE,),
    )
    numeros = [row["numero"] for row in cur.fetchall()]

    inicio = agora()
    cur = conn.execute(
        "INSERT INTO execucoes (inicio, varridos) VALUES (?, 0)", (inicio,)
    )
    execucao_id = cur.lastrowid
    conn.commit()
    conn.close()

    if not numeros:
        _fechar_execucao(execucao_id, varridos=0, alterados=0, erros=0, abortada=0,
                          observacao="nenhum processo novo pendente")
        print("nenhum processo novo pendente")
        return

    erros = 0
    varridos = 0
    for numero in numeros:
        varridos += 1
        try:
            resultado = consultar_processo(numero)
            if not resultado.get("sucesso"):
                raise RuntimeError(resultado.get("mensagem") or "consultarProcesso sem sucesso")
            alteracao = consultar_alteracao(numero)
            hash_estado = combinar_hashes(alteracao)
            gravar_consulta_completa(numero, resultado, hash_estado)
        except Exception as exc:
            erros += 1
            gravar_erro(numero, str(exc))

        if varridos >= 10 and erros / varridos > LIMITE_CIRCUIT_BREAKER:
            _fechar_execucao(
                execucao_id, varridos, alterados=varridos - erros, erros=erros, abortada=1,
                observacao="circuit breaker: taxa de erro acima de 30%",
            )
            print(f"abortado: {erros}/{varridos} erros")
            return

    _fechar_execucao(
        execucao_id, varridos, alterados=varridos - erros, erros=erros, abortada=0, observacao=None
    )
    print(f"varridos={varridos} erros={erros}")


def _fechar_execucao(execucao_id, varridos, alterados, erros, abortada, observacao):
    conn = get_connection()
    conn.execute(
        """
        UPDATE execucoes
        SET fim = ?, varridos = ?, alterados = ?, erros = ?, abortada = ?, observacao = ?
        WHERE id = ?
        """,
        (agora(), varridos, alterados, erros, abortada, observacao, execucao_id),
    )
    conn.commit()
    conn.close()


if __name__ == "__main__":
    rodar()
