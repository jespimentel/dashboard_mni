import re


def normalizar(numero: str) -> str:
    return re.sub(r"\D", "", numero or "")


def dv_valido(numero20: str) -> bool:
    if len(numero20) != 20 or not numero20.isdigit():
        return False
    seq = numero20[0:7]
    ano = numero20[9:13]
    justica = numero20[13:14]
    tribunal = numero20[14:16]
    origem = numero20[16:20]
    dv_informado = numero20[7:9]
    base = int(seq + ano + justica + tribunal + origem + "00")
    resto = base % 97
    dv_calculado = 98 - resto
    return f"{dv_calculado:02d}" == dv_informado


def normalizar_e_validar(numero: str) -> str | None:
    numero20 = normalizar(numero)
    if len(numero20) != 20:
        return None
    if not dv_valido(numero20):
        return None
    return numero20


def formatar(numero20: str) -> str:
    return (
        f"{numero20[0:7]}-{numero20[7:9]}.{numero20[9:13]}."
        f"{numero20[13:14]}.{numero20[14:16]}.{numero20[16:20]}"
    )
