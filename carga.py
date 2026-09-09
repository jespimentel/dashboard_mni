import hashlib
import sys
from datetime import datetime, timezone
from pathlib import Path

from db import get_connection
from numero_processo import normalizar_e_validar


def agora() -> str:
    return datetime.now(timezone.utc).isoformat()


def carregar(caminho: str) -> None:
    caminho = Path(caminho)
    conteudo = caminho.read_text(encoding="utf-8")
    hash_arquivo = hashlib.sha256(conteudo.encode("utf-8")).hexdigest()
    linhas = [l.strip() for l in conteudo.splitlines() if l.strip()]

    conn = get_connection()
    ts = agora()

    cur = conn.execute(
        "INSERT INTO cargas (arquivo, hash_arquivo, timestamp, lidos) VALUES (?, ?, ?, ?)",
        (caminho.name, hash_arquivo, ts, len(linhas)),
    )
    carga_id = cur.lastrowid

    validos = set()
    invalidos = 0
    for linha in linhas:
        numero = normalizar_e_validar(linha)
        if numero is None:
            invalidos += 1
            conn.execute(
                "INSERT INTO rejeitos (carga_id, linha_original, motivo) VALUES (?, ?, ?)",
                (carga_id, linha, "numero invalido ou digito verificador incorreto"),
            )
            continue
        validos.add(numero)

    novos = 0
    repetidos = 0
    for numero in validos:
        cur = conn.execute("SELECT numero FROM processos WHERE numero = ?", (numero,))
        existente = cur.fetchone()
        if existente is None:
            novos += 1
            conn.execute(
                """
                INSERT INTO processos (numero, hash_estado, status, primeira_carga, ultima_carga)
                VALUES (?, NULL, 'ativo', ?, ?)
                """,
                (numero, ts, ts),
            )
        else:
            repetidos += 1
            conn.execute(
                "UPDATE processos SET ultima_carga = ? WHERE numero = ?",
                (ts, numero),
            )

    conn.execute(
        "UPDATE cargas SET invalidos = ?, novos = ?, repetidos = ? WHERE id = ?",
        (invalidos, novos, repetidos, carga_id),
    )

    conn.commit()
    conn.close()

    print(f"lidos={len(linhas)} invalidos={invalidos} novos={novos} repetidos={repetidos}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("uso: python carga.py <arquivo.txt|csv>")
        sys.exit(1)
    carregar(sys.argv[1])
