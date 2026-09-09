from db import get_connection

REGRAS = [
    (26, None, "Distribuído Livremente (1ª vez)", 10),
    (581, r"Relatório Final", "Relatório Final Juntado", 10),
    (85, r"Resposta à Acusação", "Resposta à Acusação Juntada", 10),
    (60189, None, "Audiência Realizada Exitosa", 10),
    (85, r"Apelação/Razões Juntada|Tipo da Petição: Razões de Apelação", "Apelação/Razões Juntada", 10),
    (85, r"Contrarrazões", "Contrarrazões Juntada", 10),
    (50132, None, "Acórdão registrado", 10),
    (None, r"Denúncia Juntada", "Denúncia Juntada", 10),
]


def seed() -> None:
    conn = get_connection()
    for codigo_cnj, padrao_texto, rotulo, prioridade in REGRAS:
        existe = conn.execute(
            "SELECT 1 FROM regras_relevancia WHERE rotulo = ?", (rotulo,)
        ).fetchone()
        if existe:
            continue
        conn.execute(
            """
            INSERT INTO regras_relevancia (codigo_cnj, padrao_texto, rotulo, prioridade, ativo)
            VALUES (?, ?, ?, ?, 1)
            """,
            (codigo_cnj, padrao_texto, rotulo, prioridade),
        )
    conn.commit()
    conn.close()


if __name__ == "__main__":
    seed()
    print("regras de relevância semeadas")
