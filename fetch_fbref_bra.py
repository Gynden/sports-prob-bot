import soccerdata as sd
import pandas as pd
from pathlib import Path

# Liga e temporada (vamos ajustar depois se precisar)
LEAGUE_ID = "BRA-Serie A"
SEASONS = [2025]

# Arquivos de debug / saída
OUT_SCHEDULE = Path("DEBUG_fbref_schedule.csv")
OUT_EVENTS = Path("DEBUG_fbref_events_sample.csv")


def main():
    # 1) Mostra ligas disponíveis (só pra ver se o BRA-Serie A existe com esse nome)
    print("Ligas disponíveis no FBref através do soccerdata:")
    print(sd.FBref.available_leagues())

    # 2) Cria o scraper
    fbref = sd.FBref(leagues=[LEAGUE_ID], seasons=SEASONS)

    # 3) Lê o calendário de jogos (schedule)
    schedule = fbref.read_schedule()
    print("Schedule - colunas:", schedule.columns)
    schedule.to_csv(OUT_SCHEDULE, index=False)
    print(f"Schedule salvo em: {OUT_SCHEDULE.absolute()}")

    # 4) Lê eventos (gols, cartões, etc.) e salva só um pedaço pra inspecionar
    events = fbref.read_events()
    print("Events - colunas:", events.columns)
    events.head(200).to_csv(OUT_EVENTS, index=False)
    print(f"Amostra de eventos salva em: {OUT_EVENTS.absolute()}")


if __name__ == "__main__":
    main()
