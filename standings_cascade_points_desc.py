# ====== BEGIN: Juegos de AYER (hora Chile) ======
# Esta sección es independiente y no rompe nada existente.
# Usa los mismos nombres/convenciones del archivo:
# - CONFIG["participants"], CONFIG["game_mode"], CONFIG["league_start_date"]
# - CHILE_TZ, parse_iso(), to_chile(), safe_int()

from datetime import timedelta

try:
    import requests  # por si no estaba importado arriba
except Exception:
    pass

def _api_version_from_config(default="mlb25"):
    try:
        return CONFIG.get("fetch", {}).get("api_version", default)
    except Exception:
        return default

def _max_pages_from_config(default=3):
    try:
        return int(CONFIG.get("fetch", {}).get("max_pages_per_user", default))
    except Exception:
        return default

def _sleep_between_calls_from_config(default=0.5):
    try:
        return float(CONFIG.get("fetch", {}).get("sleep_seconds_between_calls", default))
    except Exception:
        return default

def _timeout_from_config(default=15):
    try:
        return int(CONFIG.get("fetch", {}).get("timeout_seconds", default))
    except Exception:
        return default

def _league_start_dt_utc():
    # Si tienes parse_iso en el archivo, lo reutilizamos
    start = (CONFIG.get("league_start_date") or "1970-01-01") + "T00:00:00Z"
    return parse_iso(start)

def _teams_short_set():
    # Equipos (forma corta) definidos en tu CONFIG de participantes
    try:
        return {p["team"] for p in CONFIG.get("participants", [])}
    except Exception:
        return set()

def _user_list():
    return CONFIG.get("participants", [])

def _normalize_team_from_full(full_name: str, allowed_shorts: set[str]) -> str | None:
    if not full_name:
        return None
    fn = full_name.strip().lower()
    # 1) por sufijo (p.ej. '... Blue Jays' -> 'Blue Jays')
    for short in sorted(allowed_shorts, key=lambda s: -len(s)):
        s = short.lower()
        if fn.endswith(s):
            return short
    # 2) por presencia de palabra
    for short in sorted(allowed_shorts, key=lambda s: -len(s)):
        if f" {short.lower()} " in f" {fn} ":
            return short
    return None

def _fetch_user_page(username: str, platform: str, page: int, api_version: str, timeout_s: int):
    url = f"https://{api_version}.theshow.com/apis/game_history.json"
    params = {"username": username, "platform": platform, "page": page}
    UA = {"User-Agent": "LigaLegends/1.0 (+https://example.com)"}
    r = requests.get(url, params=params, headers=UA, timeout=timeout_s)
    if not r.ok:
        return None
    return r.json() or {}

def _collect_yesterday_games_chile():
    """
    Descarga como máximo N páginas por usuario, filtra:
    - solo modo de liga (CONFIG["game_mode"])
    - solo juegos entre equipos de la liga
    - solo juegos cuya fecha local Chile == ayer
    Devuelve lista de diccionarios con campos normalizados.
    """
    api_version = _api_version_from_config("mlb25")
    max_pages = _max_pages_from_config(3)
    sleep_s = _sleep_between_calls_from_config(0.5)
    timeout_s = _timeout_from_config(15)

    teams_short = _teams_short_set()
    mode = CONFIG.get("game_mode", "LEAGUE")
    start_dt_utc = _league_start_dt_utc()

    yesterday_date = (datetime.now(CHILE_TZ) - timedelta(days=1)).date()

    collected = []
    seen_ids = set()

    for p in _user_list():
        username = p["username"]
        platform = p["platform"]
        for page in range(1, max_pages + 1):
            raw = _fetch_user_page(username, platform, page, api_version, timeout_s)
            if not raw:
                break
            for g in raw.get("data", []):
                # mínimos
                gid = g.get("id")
                ended_at = g.get("ended_at")
                home_full = g.get("home_full_name") or g.get("home_team") or g.get("home_name")
                away_full = g.get("away_full_name") or g.get("away_team") or g.get("away_name")
                if not gid or not ended_at or not home_full or not away_full:
                    continue

                # modo de liga y fecha posterior al inicio de liga
                if g.get("game_mode") != mode:
                    continue
                ended_dt = parse_iso(ended_at)
                if ended_dt < start_dt_utc:
                    continue

                # normalizar equipos al set de la liga
                home_short = _normalize_team_from_full(home_full, teams_short)
                away_short = _normalize_team_from_full(away_full, teams_short)
                if not home_short or not away_short:
                    continue

                # fecha local == ayer (Chile)
                ended_local = to_chile(ended_dt)
                if ended_local.date() != yesterday_date:
                    continue

                if gid in seen_ids:
                    continue
                seen_ids.add(gid)

                collected.append({
                    "id": str(gid),
                    "home_team": home_short,
                    "away_team": away_short,
                    "home_score": safe_int(g.get("home_score", g.get("display_home_score")), ""),
                    "away_score": safe_int(g.get("away_score", g.get("display_away_score")), ""),
                    "ended_at_local": ended_local.strftime("%d-%m-%Y - %I:%M %p (Chile)")
                })
            # pausa amable entre páginas/usuarios
            time.sleep(sleep_s)

    # opcional: ordenar por hora local
    collected.sort(key=lambda x: x["ended_at_local"])
    return collected

def games_played_yesterday_scl():
    """
    Devuelve una lista de juegos finalizados AYER (hora Chile).
    Formato: lista de *strings* igual a tu formato actual:
      "Mets 3 - Mariners 0 - 07-09-2025 - 6:30 pm (hora Chile)"
    Si prefieres objetos, puedes devolver el dict tal cual de _collect_yesterday_games_chile().
    """
    try:
        games = _collect_yesterday_games_chile()
    except Exception as e:
        print(f"[games_played_yesterday_scl] error: {e}")
        games = []

    out = []
    for g in games:
        home = g["home_team"]
        away = g["away_team"]
        hs = "" if g.get("home_score") in (None, "") else g["home_score"]
        as_ = "" if g.get("away_score") in (None, "") else g["away_score"]
        out.append(f"{home} {hs} - {away} {as_} - {g['ended_at_local']}")
    return out
# ====== END: Juegos de AYER (hora Chile) ======
