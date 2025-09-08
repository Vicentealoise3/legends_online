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
        # Aquí se ejecuta toda la lógica pesada de la API (tu módulo principal)
        rows = standings.compute_rows()
        games_today = standings.games_played_today_scl()

        data_to_cache = {
            "standings": rows,
            "games_today": games_today
        }

        # Guarda el resultado en un archivo JSON (mismo nombre que tu app lee)
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(data_to_cache, f, ensure_ascii=False, indent=2)

        print("Actualización completada exitosamente.")
        return True
    except Exception as e:
        print(f"ERROR durante la actualización del cache: {e}")
        return False

def _run_once_then_exit():
    ok = update_data_cache()
    # Salida 0/1 útil para jobs o scripts de inicio
    sys.exit(0 if ok else 1)

if __name__ == "__main__":
    # Modo 1: correr una sola vez (para inicio en Render)
    if "--once" in sys.argv or os.getenv("RUN_ONCE") == "1":
        _run_once_then_exit()

    # Modo 2: bucle (como ya hacías en local) — configurable por env
    UPDATE_INTERVAL_SECONDS = int(os.getenv("UPDATE_INTERVAL_SECONDS", "300"))  # default 5 min
    while True:
        update_data_cache()
        print(f"Esperando {UPDATE_INTERVAL_SECONDS} segundos para la próxima actualización...")
        try:
            time.sleep(UPDATE_INTERVAL_SECONDS)
        except KeyboardInterrupt:
            print("Detenido por el usuario.")
            break
