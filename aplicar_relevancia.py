import re

from db import get_connection


def _bate(regra, codigo_nacional, texto) -> bool:
    if regra["codigo_cnj"] is not None and str(regra["codigo_cnj"]) != str(codigo_nacional):
        return False
    if regra["padrao_texto"] and not re.search(regra["padrao_texto"], texto, re.IGNORECASE):
        return False
    return True


def aplicar() -> int:
    conn = get_connection()
    regras = conn.execute(
        "SELECT id, codigo_cnj, padrao_texto FROM regras_relevancia WHERE ativo = 1"
    ).fetchall()

    movimentos = conn.execute(
        """
        SELECT m.id, m.codigo_nacional, m.descricao, m.complemento
        FROM movimentos m
        LEFT JOIN movimentos_relevantes mr ON mr.movimento_id = m.id
        WHERE mr.movimento_id IS NULL
        """
    ).fetchall()

    marcados = 0
    for mov in movimentos:
        texto = f"{mov['descricao'] or ''} {mov['complemento'] or ''}"
        for regra in regras:
            if _bate(regra, mov["codigo_nacional"], texto):
                conn.execute(
                    "INSERT OR IGNORE INTO movimentos_relevantes (movimento_id, regra_id) VALUES (?, ?)",
                    (mov["id"], regra["id"]),
                )
                marcados += 1

    conn.commit()
    conn.close()
    return marcados


if __name__ == "__main__":
    n = aplicar()
    print(f"movimentos marcados como relevantes: {n}")
