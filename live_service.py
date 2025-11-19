# live_service.py
import os
from typing import List, Dict, Any, Optional

import httpx
from fastapi import HTTPException

API_BASE = os.getenv("FOOTBALL_API_BASE", "https://v3.football.api-sports.io")
API_KEY = os.getenv("FOOTBALL_API_KEY")

if not API_KEY:
    raise RuntimeError("FOOTBALL_API_KEY não definida nas variáveis de ambiente.")

HEADERS = {
    "x-apisports-key": API_KEY
}

# ID do Brasileirão Série A na API-FOOTBALL
BRAZIL_SERIE_A_ID = 71
DEFAULT_SEASON = 2025


async def fetch_live_matches_bra(team: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Busca jogos AO VIVO do Brasileirão Série A.
    Se 'team' for informado, filtra apenas jogos em que esse time esteja em campo.
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
            detail=f"Erro ao consultar API externa (status {resp.status_code}): {resp.text}",
        )

    data = resp.json()
    fixtures = data.get("response", [])

    live_matches: List[Dict[str, Any]] = []
    team_filter = team.lower() if team else None

    for item in fixtures:
        fixture = item.get("fixture", {})
        league = item.get("league", {})
        teams = item.get("teams", {})
        goals = item.get("goals", {})
        status = fixture.get("status", {})

        home_name = teams.get("home", {}).get("name")
        away_name = teams.get("away", {}).get("name")

        # se tiver filtro de time, só deixa jogos onde o time participa
        if team_filter:
            if not home_name or not away_name:
                continue
            if team_filter not in (home_name.lower(), away_name.lower()):
                continue

        live_matches.append(
            {
                "fixture_id": fixture.get("id"),
                "date": fixture.get("date"),
                "league": league.get("name"),
                "season": league.get("season"),
                "round": league.get("round"),

                "status_short": status.get("short"),  # 1H, 2H, HT, FT...
                "status_long": status.get("long"),
                "minute": status.get("elapsed"),

                "home_team": home_name,
                "away_team": away_name,

                "home_goals": goals.get("home"),
                "away_goals": goals.get("away"),
            }
        )

    return live_matches
