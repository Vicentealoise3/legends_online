# update_cache.py
# Construye standings con tu módulo (regenerate_cache)
# y luego re-bucketea juegos "hoy/ayer" con una pasada propia (48h).
import json, os, sys, time, re
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
import requests

import standings_cascade_points_desc as standings

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CACHE_FILE = os.path.join(BASE_DIR, "standings_cache.json")
SCL = ZoneInfo("America/Santiago")

# ------------------ Helpers de tiempo / parsing ------------------
DATE_RE = re.compile(r"^\d{2}-\d{2}-\d{4}")

def _parse_iso(dt_str: str) -> datetime:
    # similar a tu parse_iso, sin depender del módulo
    if not dt_str:
        return None
    try:
        if dt_str.endswith("Z"):
            return datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
        dt = datetime.fromisoformat(dt_str)
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except Exception:
        return None

def _to_chile(dt: datetime) -> datetime:
    if not dt:
        return None
    return (dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)).astimezone(SCL)

def _fmt_chile(dt: datetime) -> str:
    return _to_chile(dt).strftime("%d-%m-%Y - %I:%M %p (hora Chile)")

def _safe_int(x, default=None):
    try:
        return int(x)
    except Exception:
        return default

# ------------------ Lectura de CONFIG ------------------
def _cfg():
    return getattr(standings, "CONFIG", {})

def _teams_short():
    try:
        return {p["team"] for p in _cfg().get("participants", [])}
    except Exception:
        return set()

def _users():
    return _cfg().get("participants", [])

def _fetch_cfg():
    f = _cfg().get("fetch", {}) if isinstance(_cfg(), dict) else {}
    return {
        "api_version": f.get("api_version", "mlb25"),
        "max_pages": int(f.get("max_pages_per_user", 3)),
        "sleep_s": float(f.get("sleep_seconds_between_calls", 0.5)),
        "timeout": int(f.get("timeout_seconds", 15)),
    }

def _league_mode():
    return _cfg().get("game_mode", "LEAGUE")

def _league_start_dt_utc():
    start = (_cfg().get("league_start_date") or "1970-01-01") + "T00:00:00Z"
    return _parse_iso(start)

# ------------------ Normalización de equipos ------------------
def _normalize_team_from_full(full_name: str, allowed_shorts: set[str]) -> str | None:
    if not full_name:
        return None
    fn = full_name.strip().lower()
    # 1) por sufijo (p.ej. '... Blue Jays' -> 'Blue Jays')
    for short in sorted(allowed_shorts, key=lambda s: -len(s)):
        s = short.lower()
        if fn.endswith(s):
            return short
    # 2) por palabra completa
    for short in sorted(allowed_shorts, key=lambda s: -len(s)):
        if f" {short.lower()} " in f" {fn} ":
            return short
    return None

# ------------------ Mini fetch 48h para bucketing ------------------
def _fetch_last48h_games():
    """
    Descarga como máximo N páginas por usuario, filtra:
      - solo modo de liga
      - solo juegos entre equipos de la liga
      - solo >= fecha de inicio de liga
    Devuelve lista de objetos con ended_at_local (Chile).
    """
    fcfg = _fetch_cfg()
    api_version = fcfg["api_version"]
    max_pages   = fcfg["max_pages"]
    sleep_s     = fcfg["sleep_s"]
    timeout_s   = fcfg["timeout"]

    teams_short = _teams_short()
    start_dt_utc = _league_start_dt_utc()
    mode = _league_mode()

    since_cutoff = datetime.now(timezone.utc) - timedelta(hours=48)

    UA = {"User-Agent":"LigaLegends/1.0 (+https://example.com)"}
    out, seen = [], set()

    for p in _users():
        username = p["username"]; platform = p["platform"]
        for page in range(1, max_pages+1):
            url = f"https://{api_version}.theshow.com/apis/game_history.json"
            params = {"username": username, "platform": platform, "page": page}
            try:
                r = requests.get(url, params=params, headers=UA, timeout=timeout_s)
                if not r.ok:
                    break
                raw = r.json() or {}
            except Exception:
                break

            for g in raw.get("data", []):
                gid = g.get("id")
                ended_at = g.get("ended_at")
                home_full = g.get("home_full_name") or g.get("home_team") or g.get("home_name")
                away_full = g.get("away_full_name") or g.get("away_team") or g.get("away_name")
                if not gid or not ended_at or not home_full or not away_full:
                    continue

                if g.get("game_mode") != mode:
                    continue

                ended_dt = _parse_iso(ended_at)
                if not ended_dt:
                    continue
                if ended_dt < start_dt_utc:
                    continue
                if ended_dt < since_cutoff:
                    # fuera de la ventana 48h
                    continue

                home_short = _normalize_team_from_full(home_full, teams_short)
                away_short = _normalize_team_from_full(away_full, teams_short)
                if not home_short or not away_short:
                    continue

                if gid in seen:
                    continue
                seen.add(gid)

                ended_local = _to_chile(ended_dt)
                out.append({
                    "id": str(gid),
                    "home_team": home_short,
                    "away_team": away_short,
                    "home_score": _safe_int(g.get("home_score", g.get("display_home_score")), ""),
                    "away_score": _safe_int(g.get("away_score", g.get("display_away_score")), ""),
                    "ended_at_local": ended_local.strftime("%d-%m-%Y - %I:%M %p (hora Chile)")
                })

            time.sleep(sleep_s)

    # ordenar por ended_at_local textual
    out.sort(key=lambda x: x["ended_at_local"])
    return out

def _bucket_today_yesterday(games_48h):
    today = datetime.now(SCL).date()
    today_str = today.strftime("%d-%m-%Y")
    yday_str  = (today - timedelta(days=1)).strftime("%d-%m-%Y")
    today_list, yday_list = [], []
    for g in games_48h:
        txt = (g.get("ended_at_local") or "").strip()
        # Formato esperado "dd-mm-YYYY - ..."
        dstr = txt[:10] if DATE_RE.match(txt) else ""
        if dstr == today_str:
            today_list.append(g)
        elif dstr == yday_str:
            yday_list.append(g)
    return today_list, yday_list

# ------------------ Pipeline principal ------------------
def update_data_cache():
    ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    print(f"[{ts}] Iniciando actualización del cache...")

    try:
        # 1) Deja que TU módulo haga la tabla y juegos de hoy básicos
        ok, msg = standings.regenerate_cache()  # escribe standings_cache.json
        if not ok:
            print(f"[update_cache] regenerate_cache devolvió error: {msg}")

        # 2) Lee lo que dejó tu módulo
        try:
            with open(CACHE_FILE, "r", encoding="utf-8") as f:
                base = json.load(f)
        except Exception:
            base = {}

        # 3) Trae últimos 48h y bucketiza por hoy/ayer (Chile)
        games_48h = _fetch_last48h_games()
        games_today, games_yesterday = _bucket_today_yesterday(games_48h)

        # 4) Re-escribe el cache con los buckets nuevos (manteniendo standings)
        data_to_cache = {
            "standings": base.get("standings", []),
            "games_today": games_today,
            "games_yesterday": games_yesterday,
            "last_updated": datetime.now(SCL).strftime("%Y-%m-%d %H:%M:%S")
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
    # Modo 1: una pasada (para Render antes de levantar la web)
    if "--once" in sys.argv or os.getenv("RUN_ONCE") == "1":
        _run_once_then_exit()

    # Modo 2: bucle (local/worker)
    UPDATE_INTERVAL_SECONDS = int(os.getenv("UPDATE_INTERVAL_SECONDS", "300"))  # 5 min
    while True:
        update_data_cache()
        print(f"Esperando {UPDATE_INTERVAL_SECONDS} segundos para la próxima actualización...")
        try:
            time.sleep(UPDATE_INTERVAL_SECONDS)
        except KeyboardInterrupt:
            print("Detenido por el usuario.")
            break
