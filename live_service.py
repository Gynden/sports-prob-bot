# live_service.py
import os
from typing import List, Dict, Any

import httpx
from fastapi import HTTPException

# Base da API (pode vir de env ou usar o default)
API_BASE = os.getenv("FOOTBALL_API_BASE", "https://v3.football.api-sports.io")
API_KEY = os.getenv("FOOTBALL_API_KEY")

if not API_KEY:
    # Se der erro logo no start, é porque esqueceu de configurar a env no Render
    raise RuntimeError("FOOTBALL_API_KEY não definida nas variáveis de ambiente.")

HEADERS = {
    "x-apisports-key": API_KEY
}

# ID do Brasileirão Série A na API-FOOTBALL (padrão conhecido)
BRAZIL_SERIE_A_ID = 71  # se quiser outro campeonato, muda aqui
DEFAULT_SEASON = 2025   # ou o ano que estiver em curso


async def fetch_live_matches_bra() -> List[Dict[str, Any]]:
    """
    Busca jogos AO VIVO do Brasileirão Série A na API-FOOTBALL.
    Retorna uma lista simplificada pronta pra devolver na sua API.
    """
    params = {
        "league": BRAZIL_SERIE_A_ID,
        "season": DEFAULT_SEASON,
        "live": "all",
    }

    async with httpx.AsyncClient(base_url=API_BASE, timeout=20) as client:
        resp = await client.get("/fixtures", headers=HEADERS, params=params)

    if resp.status_code != 200:
        raise HTTPException(
            status_code=502,
            detail=f"Erro ao consultar API externa (status {resp.status_code}): {resp.text}"
        )

    data = resp.json()

    # Na API-FOOTBALL normalmente a estrutura é:
    # { "response": [ { fixture: {...}, league: {...}, teams: {...}, goals: {...}, ... }, ... ] }
    fixtures = data.get("response", [])

    live_matches: List[Dict[str, Any]] = []

    for item in fixtures:
        fixture = item.get("fixture", {})
        league = item.get("league", {})
        teams = item.get("teams", {})
        goals = item.get("goals", {})
        status = fixture.get("status", {})

        live_matches.append(
            {
                "fixture_id": fixture.get("id"),
                "date": fixture.get("date"),
                "league": league.get("name"),
                "round": league.get("round"),

                "status_short": status.get("short"),   # e.g. 1H, 2H, HT, FT
                "status_long": status.get("long"),     # e.g. First Half, Match Finished
                "minute": status.get("elapsed"),       # minuto do jogo

                "home_team": teams.get("home", {}).get("name"),
                "away_team": teams.get("away", {}).get("name"),

                "home_goals": goals.get("home"),
                "away_goals": goals.get("away"),
            }
        )

    return live_matches
