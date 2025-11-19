import os
import requests

API_SPORTS_KEY = os.getenv("API_SPORTS_KEY")
BASE_URL_SPORTS = "https://v3.football.api-sports.io"


class ApiSportsError(Exception):
    pass


def _get_headers():
    if not API_SPORTS_KEY:
        raise ApiSportsError("Variável de ambiente API_SPORTS_KEY não está definida.")
    return {"x-apisports-key": API_SPORTS_KEY}


def _request(path: str, params: dict | None = None):
    if params is None:
        params = {}

    url = f"{BASE_URL_SPORTS}{path}"
    resp = requests.get(url, headers=_get_headers(), params=params, timeout=20)

    if resp.status_code != 200:
        raise ApiSportsError(f"Erro na API-SPORTS [{path}]: {resp.status_code} - {resp.text}")

    return resp.json()


def get_soccer_leagues(country: str | None = None):
    params = {}
    if country:
        params["country"] = country
    return _request("/leagues", params)


def search_soccer_team(name: str, country: str | None = None):
    params = {"search": name}
    if country:
        params["country"] = country
    return _request("/teams", params)


def get_head_to_head_fixtures(team1_id: int, team2_id: int, last: int = 10):
    params = {
        "h2h": f"{team1_id}-{team2_id}",
        "last": last,
    }
    return _request("/fixtures/headtohead", params)


def get_team_last_fixtures(team_id: int, last: int = 10):
    params = {
        "team": team_id,
        "last": last,
    }
    return _request("/fixtures", params)
