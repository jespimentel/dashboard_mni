import sys
from datetime import datetime

from db import get_connection
from numero_processo import formatar


def _chave_ordenacao(data_hora: str) -> datetime:
    return datetime.strptime(data_hora, "%d/%m/%Y %H:%M:%S")


def relatorio(numero: str | None = None):
    conn = get_connection()
    sql = """
        SELECT m.numero_processo, r.rotulo, m.data_hora
        FROM movimentos_relevantes mr
        JOIN movimentos m ON m.id = mr.movimento_id
        JOIN regras_relevancia r ON r.id = mr.regra_id
    """
    params = ()
    if numero:
        sql += " WHERE m.numero_processo = ?"
        params = (numero,)
    sql += " ORDER BY m.numero_processo"

    linhas = conn.execute(sql, params).fetchall()
    conn.close()
    linhas = sorted(linhas, key=lambda l: (l["numero_processo"], _chave_ordenacao(l["data_hora"])))

    atual = None
    for linha in linhas:
        if linha["numero_processo"] != atual:
            atual = linha["numero_processo"]
            print(f"\n{formatar(atual)}")
        print(f"  {linha['data_hora']}  {linha['rotulo']}")


if __name__ == "__main__":
    numero = sys.argv[1] if len(sys.argv) > 1 else None
    relatorio(numero)
