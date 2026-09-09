import os
from pathlib import Path

from dotenv import load_dotenv
from zeep import Client, helpers
from zeep.cache import SqliteCache
from zeep.transports import Transport

load_dotenv()

USUARIO_MNI = os.getenv("USUARIO_MNI")
SENHA_MNI = os.getenv("SENHA_MNI")

WSDL_URL = "http://esaj.tjsp.jus.br/mniws/servico-intercomunicacao-2.2.2/intercomunicacao?wsdl"
CACHE_PATH = Path(__file__).parent / "zeep_cache.db"

_client = None


def get_client():
    global _client
    if _client is None:
        transport = Transport(cache=SqliteCache(path=str(CACHE_PATH)))
        _client = Client(wsdl=WSDL_URL, transport=transport)
    return _client


def consultar_alteracao(numero_processo: str) -> dict:
    client = get_client()
    resposta = client.service.consultarAlteracao(
        idConsultante=USUARIO_MNI,
        senhaConsultante=SENHA_MNI,
        numeroProcesso=numero_processo,
    )
    return helpers.serialize_object(resposta)


def consultar_processo(numero_processo: str) -> dict:
    client = get_client()
    resposta = client.service.consultarProcesso(
        idConsultante=USUARIO_MNI,
        senhaConsultante=SENHA_MNI,
        numeroProcesso=numero_processo,
        movimentos=True,
        incluirDocumentos=False,
    )
    return helpers.serialize_object(resposta)
