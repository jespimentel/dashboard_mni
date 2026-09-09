from datetime import datetime, timezone

from cnj_client import consultar_item
from db import get_connection


def agora() -> str:
    return datetime.now(timezone.utc).isoformat()


def _codigos_pendentes(conn, coluna: str, tipo: str) -> set:
    cur = conn.execute(
        f"""
        SELECT DISTINCT {coluna} c FROM processos
        WHERE {coluna} IS NOT NULL
          AND {coluna} NOT IN (SELECT codigo FROM tabela_cnj WHERE tipo = ?)
        """,
        (tipo,),
    )
    return {row["c"] for row in cur.fetchall()}


def rodar() -> None:
    conn = get_connection()
    pendentes = [(c, "C") for c in _codigos_pendentes(conn, "classe_processual", "C")]
    pendentes += [(c, "A") for c in _codigos_pendentes(conn, "assunto_codigo", "A")]
    conn.close()

    if not pendentes:
        print("nenhum código pendente")
        return

    ts = agora()
    consultados = 0
    erros = 0
    for codigo, tipo in pendentes:
        try:
            item = consultar_item(codigo, tipo)
        except Exception as exc:
            erros += 1
            print(f"erro {tipo}:{codigo} -> {exc}")
            continue

        conn = get_connection()
        conn.execute(
            """
            INSERT INTO tabela_cnj (codigo, tipo, nome, codigo_pai, situacao, atualizado_em)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(codigo, tipo) DO UPDATE SET
                nome = excluded.nome, codigo_pai = excluded.codigo_pai,
                situacao = excluded.situacao, atualizado_em = excluded.atualizado_em
            """,
            (
                codigo, tipo, item.get("nome"),
                int(item["cod_item_pai"]) if item.get("cod_item_pai") else None,
                item.get("situacao"), ts,
            ),
        )
        conn.commit()
        conn.close()
        consultados += 1

    print(f"consultados={consultados} erros={erros}")


if __name__ == "__main__":
    rodar()
