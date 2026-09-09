from pathlib import Path

from zeep import Client
from zeep.cache import SqliteCache
from zeep.transports import Transport

WSDL_URL = "https://www.cnj.jus.br/sgt/sgt_ws.php?wsdl"
CACHE_PATH = Path(__file__).parent / "zeep_cache.db"

_client = None


def get_client():
    global _client
    if _client is None:
        transport = Transport(cache=SqliteCache(path=str(CACHE_PATH)))
        _client = Client(wsdl=WSDL_URL, transport=transport)
    return _client


def consultar_item(codigo: int, tipo: str) -> dict:
    client = get_client()
    resposta = client.service.getArrayDetalhesItemPublicoWS(str(codigo), tipo)
    return {el.find("key").text: el.find("value").text for el in resposta["_value_1"]}
