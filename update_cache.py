import standings_cascade_points_desc as standings
import json
import os
import time
import sys
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

# Ruta absoluta al cache
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CACHE_FILE = os.path.join(BASE_DIR, "standings_cache.json")

SCL = ZoneInfo("America/Santiago")

def _filter_yesterday_from_list(mixed_list):
    """
    Acepta lista de strings u objetos. Devuelve solo los de AYER (hora Chile).
    Busca la fecha 'dd-mm-YYYY' en 'ended_at_local' o dentro del string.
    """
    if not mixed_list:
        return []

    ayer = (datetime.now(SCL) - timedelta(days=1)).strftime("%d-%m-%Y")
    out = []
    for g in mixed_list:
        if isinstance(g, dict):
            txt = (g.get("ended_at_local") or "").strip()
            if txt.startswith(ayer):
                out.append(g)
        else:
            # string
            s = (str(g) or "").strip()
            if ayer in s:
                out.append(s)
    return out

def update_data_cache():
    """Fetches and saves standings and games (today + yesterday) to a JSON cache file."""
    ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    print(f"[{ts}] Iniciando actualización del cache...")
    try:
        # Lógica pesada (tu módulo principal)
        rows = standings.compute_rows()

        # Hoy
        games_today = standings.games_played_today_scl()

        # Ayer (variante 1: si existe función dedicada)
        games_yesterday = []
        try:
            games_yesterday = standings.games_played_yesterday_scl()
        except AttributeError:
            # Variante 2 (fallback): si tienes "last hours", filtramos AYER
            try:
                last48 = standings.games_played_last_hours_scl(48)
                games_yesterday = _filter_yesterday_from_list(last48)
            except AttributeError:
                # Si no existe ninguna, queda vacío (frontend lo soporta)
                games_yesterday = []

        data_to_cache = {
            "standings": rows,
            "games_today": games_today,
            "games_yesterday": games_yesterday
        }

        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(data_to_cache, f, ensure_ascii=False, indent=2)

        print("Actualización completada exitosamente.")
        return True
    except Exception as e:
        print(f"ERROR durante la actualización del cache: {e}")
        return False

def _run_once_then_exit():
    ok = update_data_cache()
    sys.exit(0 if ok else 1)

if __name__ == "__main__":
    # Modo 1: una sola pasada (útil en Render antes de levantar la web)
    if "--once" in sys.argv or os.getenv("RUN_ONCE") == "1":
        _run_once_then_exit()

    # Modo 2: bucle (local / worker)
    UPDATE_INTERVAL_SECONDS = int(os.getenv("UPDATE_INTERVAL_SECONDS", "300"))  # 5 min
    while True:
        update_data_cache()
        print(f"Esperando {UPDATE_INTERVAL_SECONDS} segundos para la próxima actualización...")
        try:
            time.sleep(UPDATE_INTERVAL_SECONDS)
        except KeyboardInterrupt:
            print("Detenido por el usuario.")
            break
