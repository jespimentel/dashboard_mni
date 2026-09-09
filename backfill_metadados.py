from db import get_connection
from ingest import extrair_dados_basicos, gravar_movimentos
from mni_client import consultar_processo

LIMITE_CIRCUIT_BREAKER = 0.3


def rodar() -> None:
    conn = get_connection()
    cur = conn.execute(
        """
        SELECT numero FROM processos
        WHERE hash_estado IS NOT NULL AND situacao IS NULL AND status = 'ativo'
        """
    )
    numeros = [row["numero"] for row in cur.fetchall()]
    conn.close()

    if not numeros:
        print("nenhum processo pendente de backfill de metadados")
        return

    varridos = 0
    erros = 0
    for numero in numeros:
        varridos += 1
        try:
            resultado = consultar_processo(numero)
            if not resultado.get("sucesso"):
                raise RuntimeError(resultado.get("mensagem") or "consultarProcesso sem sucesso")

            dados_basicos = extrair_dados_basicos(resultado)
            conn = get_connection()
            gravar_movimentos(conn, numero, resultado["processo"].get("movimento") or [])
            conn.execute(
                """
                UPDATE processos
                SET classe_processual = ?, assunto_codigo = ?, vara = ?,
                    municipio_ibge = ?, codigo_localidade = ?, situacao = ?, data_ajuizamento = ?
                WHERE numero = ?
                """,
                (
                    dados_basicos["classe_processual"], dados_basicos["assunto_codigo"],
                    dados_basicos["vara"], dados_basicos["municipio_ibge"],
                    dados_basicos["codigo_localidade"], dados_basicos["situacao"],
                    dados_basicos["data_ajuizamento"], numero,
                ),
            )
            conn.commit()
            conn.close()
        except Exception as exc:
            erros += 1
            conn = get_connection()
            conn.execute("UPDATE processos SET ultimo_erro = ? WHERE numero = ?", (str(exc), numero))
            conn.commit()
            conn.close()

        if varridos >= 10 and erros / varridos > LIMITE_CIRCUIT_BREAKER:
            print(f"abortado: {erros}/{varridos} erros")
            return

    print(f"varridos={varridos} erros={erros}")


if __name__ == "__main__":
    rodar()
