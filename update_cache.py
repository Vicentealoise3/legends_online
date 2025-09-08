import standings_cascade_points_desc as standings
import json
import os
import time
import sys
from datetime import datetime

# Ruta absoluta al cache, para que funcione igual en local y en Render
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CACHE_FILE = os.path.join(BASE_DIR, "standings_cache.json")

def update_data_cache():
    """Fetches and saves standings and today's games data to a JSON cache file."""
    ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    print(f"[{ts}] Iniciando actualización del cache...")
    try:
        # Lógica pesada (tu módulo principal)
        rows = standings.compute_rows()
        games_today = standings.games_played_today_scl()

        # (Opcional) Fallback si hoy está vacío y tú implementaste la función:
        # - NO rompe si no existe (queda tal cual).
        show_recent_when_empty = os.getenv("SHOW_RECENT_WHEN_EMPTY", "0") == "1"
        if show_recent_when_empty and not games_today:
            try:
                games_today = standings.games_played_last_hours_scl(24)
            except AttributeError:
                # Si no existe la función en tu módulo, seguimos con la lista vacía
                pass

        data_to_cache = {
            "standings": rows,
            "games_today": games_today
        }

        # Escritura del archivo JSON
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
    # Modo 1: correr una sola vez (útil en Render antes de levantar la web)
    if "--once" in sys.argv or os.getenv("RUN_ONCE") == "1":
        _run_once_then_exit()

    # Modo 2: bucle (como en local) — configurable por env
    UPDATE_INTERVAL_SECONDS = int(os.getenv("UPDATE_INTERVAL_SECONDS", "300"))  # 5 min
    while True:
        update_data_cache()
        print(f"Esperando {UPDATE_INTERVAL_SECONDS} segundos para la próxima actualización...")
        try:
            time.sleep(UPDATE_INTERVAL_SECONDS)
        except KeyboardInterrupt:
            print("Detenido por el usuario.")
            break
