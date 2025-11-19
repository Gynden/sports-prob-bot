import os
import requests

API_SPORTS_KEY = os.getenv("API_SPORTS_KEY")

# Endpoint de futebol da API-SPORTS (ajuste se o provedor mudar)
BASE_URL_FOOTBALL = "https://v3.football.api-sports.io"


class ApiSportsError(Exception):
    pass


def _get_headers():
    if not API_SPORTS_KEY:
        raise ApiSportsError("Variável de ambiente API_SPORTS_KEY não está definida.")
    return {
        "x-apisports-key": API_SPORTS_KEY
    }


def get_soccer_leagues(country: str = "Brazil") -> dict:
    """
    Busca ligas de futebol na API-SPORTS para um determinado país.
    Exemplo de country: 'Brazil', 'England', etc.
    """
    url = f"{BASE_URL_FOOTBALL}/leagues"
    params = {"country": country}
    headers = _get_headers()

    resp = requests.get(url, headers=headers, params=params, timeout=20)
    if resp.status_code != 200:
        raise ApiSportsError(f"Erro na API-SPORTS: {resp.status_code} - {resp.text}")

    return resp.json()


def search_soccer_team(name: str, country: str | None = None) -> dict:
    """
    Busca times pelo nome (e opcionalmente país).
    Retorna o JSON completo da API.
    """
    url = f"{BASE_URL_FOOTBALL}/teams"
    params = {"search": name}
    if country:
        params["country"] = country

    headers = _get_headers()
    resp = requests.get(url, headers=headers, params=params, timeout=20)

    if resp.status_code != 200:
        raise ApiSportsError(f"Erro na API-SPORTS (teams): {resp.status_code} - {resp.text}")

    return resp.json()


def get_head_to_head_fixtures(home_team_id: int, away_team_id: int, last: int = 10) -> dict:
    """
    Busca confrontos diretos (head-to-head) entre dois times.
    last = quantidade de jogos recentes para analisar.
    """
    url = f"{BASE_URL_FOOTBALL}/fixtures/headtohead"
    params = {
        "h2h": f"{home_team_id}-{away_team_id}",
        "last": last
    }
    headers = _get_headers()

    resp = requests.get(url, headers=headers, params=params, timeout=20)
    if resp.status_code != 200:
        raise ApiSportsError(f"Erro na API-SPORTS (headtohead): {resp.status_code} - {resp.text}")

    return resp.json()
