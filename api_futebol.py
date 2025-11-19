import os
import requests

API_FUTEBOL_TOKEN = os.getenv("API_FUTEBOL_TOKEN")

BASE_URL_FUTEBOL = "https://api.api-futebol.com.br/v1"


class ApiFutebolError(Exception):
    pass


def _get_headers():
    if not API_FUTEBOL_TOKEN:
        raise ApiFutebolError("Variável de ambiente API_FUTEBOL_TOKEN não está definida.")
    return {
        "Authorization": f"Bearer {API_FUTEBOL_TOKEN}"
    }


def _request(path: str, params: dict | None = None):
    """
    Faz uma requisição GET simples para a API-Futebol.
    """
    if params is None:
        params = {}

    url = f"{BASE_URL_FUTEBOL}{path}"
    resp = requests.get(url, headers=_get_headers(), params=params, timeout=20)

    if resp.status_code != 200:
        raise ApiFutebolError(f"Erro na API-Futebol [{path}]: {resp.status_code} - {resp.text}")

    return resp.json()


def list_campeonatos():
    """
    GET /v1/campeonatos
    Lista todos os campeonatos.
    """
    return _request("/campeonatos")


def get_championship_table(campeonato_id: int):
    """
    GET /v1/campeonatos/{id}/tabela
    Retorna a tabela de classificação de um campeonato.
    """
    return _request(f"/campeonatos/{campeonato_id}/tabela")


def get_time_partidas_anteriores(time_id: int):
    """
    GET /v1/times/{id}/partidas/anteriores
    Retorna as partidas anteriores de um time.
    """
    return _request(f"/times/{time_id}/partidas/anteriores")
