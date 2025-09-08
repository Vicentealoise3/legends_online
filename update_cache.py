import standings_cascade_points_desc as standings
import json
import os
import time
import sys
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import re

# Ruta absoluta al cache
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CACHE_FILE = os.path.join(BASE_DIR, "standings_cache.json")

SCL = ZoneInfo("America/Santiago")

# ---------- Helpers de normalización ----------
DATE_RE = re.compile(r"^\d{2}-\d{2}-\d{4}")

def _parse_game_string(s: str):
    """
    Convierte: "Mets 3 - Mariners 0 - 07-09-2025 - 6:30 pm (hora Chile)"
    a un objeto estandarizado. Si no puede, devuelve {"raw": s}.
    """
    if not s:
        return {"raw": s}
    norm = " ".join(str(s).split()).strip()
    parts = norm.split(" - ")
    if len(parts) < 4:
        return {"raw": s}

    home_part, away_part, date_part, time_part = parts[0], parts[1], parts[2], " - ".join(parts[3:])
    def split_last(txt):
        i = txt.strip().rfind(" ")
        if i == -1:
            return {"name": txt.strip(), "score": ""}
        return {"name": txt[:i].strip(), "score": txt[i+1:].strip()}

    h = split_last(home_part)
    a = split_last(away_part)
    ended_at_local = f"{date_part} - {time_part}"

    return {
        "home_team": h["name"],
        "home_score": h["score"],
        "away_team": a["name"],
        "away_score": a["score"],
        "ended_at_local": ended_at_local
    }

def _standardize_game(entry):
    """
    Acepta string u objeto (con ended_at_local). Devuelve dict con las mismas claves.
    """
    if isinstance(entry, str):
        return _parse_game_string(entry)
    if isinstance(entry, dict):
        # aseguramos campos esperados
        obj = {
            "home_team": entry.get("home_team", ""),
            "home_score": entry.get("home_score", ""),
            "away_team": entry.get("away_team", ""),
            "away_score": entry.get("away_score", ""),
            "ended_at_local": entry.get("ended_at_local", "")
        }
        # si vino en otro formato, intenta rescatar "ended_at_local" o fecha en texto
        if not obj["ended_at_local"]:
            raw = (entry.get("raw") or "") if "raw" in entry else ""
            if DATE_RE.search(raw):
                # no arriesgamos más parsing aquí
                obj["ended_at_local"] = raw
        return obj
    # fallback
    return {"raw": str(entry)}

def _ended_local_date_str(obj):
    """
    Extrae la fecha dd-mm-YYYY desde ended_at_local (si existe).
    """
    txt = (obj.get("ended_at_local") or "").strip()
    # ended_at_local suele comenzar con "dd-mm-YYYY - ..."
    if DATE_RE.match(txt):
        return txt[:10]
    # si vino incrustado, intenta buscar patrón
    m = DATE_RE.search(txt)
    if m:
        return m.group(0)
    return ""

def _bucket_today_yesterday(games_48h):
    """
    Re-bucketea según la FECHA LOCAL CHILE ACTUAL.
    games_48h: lista heterogénea (strings/objetos).
    """
    today = datetime.now(SCL).date()
    today_str = today.strftime("%d-%m-%Y")
    yesterday = (today - timedelta(days=1)).strftime("%d-%m-%Y")

    today_list, yday_list = [], []

    for g in games_48h:
        obj = _standardize_game(g)
        if "raw" in obj and not obj.get("ended_at_local"):
            # no se pudo estandarizar: lo tiro a un bucket "seguro" (ayer) para no confundir
            yday_list.append(obj["raw"])
            continue
        dstr = _ended_local_date_str(obj)
        if dstr == today_str:
            today_list.append(obj)
        elif dstr == yesterday:
            yday_list.append(obj)
        else:
            # fuera de los dos días; ignoramos porque pedimos 48h
            pass

    # orden opcional por texto de hora
    def sort_key(x):
        if isinstance(x, str):
            return x
        return x.get("ended_at_local", "")
    today_list.sort(key=sort_key)
    yday_list.sort(key=sort_key)

    # Mantener compatibilidad: si el front soporta objetos y strings, OK.
    return today_list, yday_list

# ---------- Pipeline principal ----------
def update_data_cache():
    ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    print(f"[{ts}] Iniciando actualización del cache...")
    try:
        # Standings tal cual
        rows = standings.compute_rows()

        # Preferimos últimos 48h para clasificar bien por 'hoy/ayer'
        games_48h = None
        try:
            games_48h = standings.games_played_last_hours_scl(48)
        except AttributeError:
            # si no existe, armamos con hoy + ayer (si lo tienes), como fallback
            today_only = standings.games_played_today_scl()
            try:
                yday_only = standings.games_played_yesterday_scl()
            except AttributeError:
                yday_only = []
            games_48h = (today_only or []) + (yday_only or [])

        games_today, games_yesterday = _bucket_today_yesterday(games_48h)

        data_to_cache = {
            "standings": rows,
            "games_today": games_today,
            "games_yesterday": games_yesterday,
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
