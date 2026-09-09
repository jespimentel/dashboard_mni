from datetime import datetime, timezone

from db import get_connection
from ingest import combinar_hashes, gravar_consulta_completa, gravar_erro
from mni_client import consultar_alteracao, consultar_processo

LIMITE_CIRCUIT_BREAKER = 0.3


def agora() -> str:
    return datetime.now(timezone.utc).isoformat()


def rodar() -> None:
    conn = get_connection()
    cur = conn.execute(
        "SELECT numero, hash_estado FROM processos WHERE status = 'ativo' AND hash_estado IS NOT NULL"
    )
    processos = [(row["numero"], row["hash_estado"]) for row in cur.fetchall()]

    inicio = agora()
    cur = conn.execute("INSERT INTO execucoes (inicio, varridos) VALUES (?, 0)", (inicio,))
    execucao_id = cur.lastrowid
    conn.commit()
    conn.close()

    if not processos:
        _fechar_execucao(execucao_id, 0, 0, 0, 0, "nenhum processo ativo para varrer")
        print("nenhum processo ativo para varrer")
        return

    varridos = 0
    alterados = 0
    erros = 0
    for numero, hash_anterior in processos:
        varridos += 1
        try:
            alteracao = consultar_alteracao(numero)
            if not alteracao.get("sucesso"):
                raise RuntimeError(alteracao.get("mensagem") or "consultarAlteracao sem sucesso")

            hash_atual = combinar_hashes(alteracao)
            if hash_atual != hash_anterior:
                resultado = consultar_processo(numero)
                if not resultado.get("sucesso"):
                    raise RuntimeError(resultado.get("mensagem") or "consultarProcesso sem sucesso")
                gravar_consulta_completa(numero, resultado, hash_atual)
                alterados += 1
            else:
                _marcar_consultado(numero)
        except Exception as exc:
            erros += 1
            gravar_erro(numero, str(exc))

        if varridos >= 10 and erros / varridos > LIMITE_CIRCUIT_BREAKER:
            _fechar_execucao(
                execucao_id, varridos, alterados, erros, 1,
                "circuit breaker: taxa de erro acima de 30%",
            )
            print(f"abortado: {erros}/{varridos} erros")
            return

    _fechar_execucao(execucao_id, varridos, alterados, erros, 0, None)
    print(f"varridos={varridos} alterados={alterados} erros={erros}")


def _marcar_consultado(numero: str) -> None:
    conn = get_connection()
    conn.execute(
        "UPDATE processos SET ultima_consulta = ?, ultimo_erro = NULL WHERE numero = ?",
        (agora(), numero),
    )
    conn.commit()
    conn.close()


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
