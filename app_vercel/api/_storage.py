import csv
import io
import json
import logging
import os
import time
import urllib.parse
import urllib.request
from typing import Dict, List, Any, Optional

logger = logging.getLogger("vercel-storage")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

# Archivos temporales locales (fallback en servidor)
TMP_PRIORITY_FILE = "/tmp/kanban_priorities.json" if os.name != "nt" else os.path.join(os.environ.get("TEMP", "."), "kanban_priorities.json")
TMP_LOGS_FILE = "/tmp/kanban_priority_logs.json" if os.name != "nt" else os.path.join(os.environ.get("TEMP", "."), "kanban_priority_logs.json")

# Configuración de Google Sheets
SPREADSHEET_ID = os.environ.get("SPREADSHEET_ID", "1U4LtXEf3WE2Uu3U6V0dhBlsI4iINwUdPITRpXx90qg8")
# Webhook opcional de Google Apps Script (Recomendado para cero dependencias y 100% gratuito)
GSHEETS_PRIORITIES_URL = os.environ.get("GSHEETS_PRIORITIES_URL") or os.environ.get("GSHEETS_WEBHOOK_URL", "")
# URL de exportación CSV de la pestaña 'prioridades_pcp'
DEFAULT_PRIORITIES_CSV_URL = f"https://docs.google.com/spreadsheets/d/{SPREADSHEET_ID}/gviz/tq?tqx=out:csv&sheet=prioridades_pcp"
GSHEETS_PRIORITIES_CSV_URL = os.environ.get("GSHEETS_PRIORITIES_CSV_URL", DEFAULT_PRIORITIES_CSV_URL)

# Service Account de Google opcional (en variable de entorno JSON o archivo)
GOOGLE_SERVICE_ACCOUNT_JSON = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON", "")
GOOGLE_SERVICE_ACCOUNT_FILE = os.environ.get(
    "GOOGLE_SERVICE_ACCOUNT_FILE",
    os.path.join(os.path.dirname(__file__), "service_account.json")
)

# Soporte para Vercel KV / Upstash Redis REST API
KV_URL = os.environ.get("KV_REST_API_URL") or os.environ.get("UPSTASH_REDIS_REST_URL")
KV_TOKEN = os.environ.get("KV_REST_API_TOKEN") or os.environ.get("UPSTASH_REDIS_REST_TOKEN")

# Caché en memoria de la instancia con TTL para ultra-alta velocidad (<1ms)
_memory_priorities: Dict[str, Any] = {}
_priorities_cache_time: float = 0.0
_memory_logs: List[Dict[str, Any]] = []
_logs_cache_time: float = 0.0
CACHE_TTL_SECONDS = 10.0


# ==============================================================================
# MOTOR 1: VERCEL KV / UPSTASH REDIS
# ==============================================================================
def _kv_command(cmd: str, *args) -> Any:
    """Envía un comando REST a Upstash / Vercel KV si están configurados."""
    if not KV_URL or not KV_TOKEN:
        return None
    try:
        url = f"{KV_URL.rstrip('/')}/{cmd}"
        payload = json.dumps(list(args)).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=payload,
            headers={
                "Authorization": f"Bearer {KV_TOKEN}",
                "Content-Type": "application/json"
            },
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=4) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data.get("result")
    except Exception as e:
        logger.debug(f"Aviso Vercel KV ({cmd}): {e}")
        return None


# ==============================================================================
# MOTOR 2: GOOGLE APPS SCRIPT WEBHOOK (SIN DEPENDENCIAS, 100% GRATUITO)
# ==============================================================================
def _gsheets_webhook_get() -> Optional[Dict[str, Any]]:
    """Consulta prioridades y logs desde el Webhook de Google Apps Script."""
    if not GSHEETS_PRIORITIES_URL:
        return None
    try:
        req = urllib.request.Request(
            GSHEETS_PRIORITIES_URL,
            headers={"User-Agent": "KanbanVercel/2.0"}
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            if isinstance(data, dict):
                return data
    except Exception as e:
        logger.warning(f"Error consultando Google Apps Script Webhook: {e}")
    return None


def _gsheets_webhook_post(payload: Dict[str, Any]) -> bool:
    """Guarda prioridades y/o logs vía POST al Webhook de Google Apps Script."""
    if not GSHEETS_PRIORITIES_URL:
        return False
    try:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(
            GSHEETS_PRIORITIES_URL,
            data=body,
            headers={
                "Content-Type": "application/json; charset=utf-8",
                "User-Agent": "KanbanVercel/2.0"
            },
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=6) as resp:
            res = json.loads(resp.read().decode("utf-8"))
            return bool(res.get("status") in ["ok", "success", True])
    except Exception as e:
        logger.warning(f"Error enviando actualización a Google Apps Script Webhook: {e}")
        return False


# ==============================================================================
# MOTOR 3: GOOGLE SHEETS CSV EXPORT TAB (LECTURA DIRECTA 'prioridades_pcp')
# ==============================================================================
def _gsheets_csv_read_priorities() -> Optional[Dict[str, Any]]:
    """Lee prioridades directamente desde la pestaña 'prioridades_pcp' exportada en CSV."""
    if not GSHEETS_PRIORITIES_CSV_URL:
        return None
    try:
        req = urllib.request.Request(
            GSHEETS_PRIORITIES_CSV_URL,
            headers={"User-Agent": "KanbanVercel/2.0"}
        )
        with urllib.request.urlopen(req, timeout=4) as resp:
            csv_text = resp.read().decode("utf-8", errors="replace")

        # Verificar que sea un CSV válido y no un error HTML de Google
        if "<!DOCTYPE html" in csv_text or "<html" in csv_text:
            return None

        reader = csv.DictReader(io.StringIO(csv_text))
        priorities: Dict[str, Any] = {}
        for row in reader:
            of_code = str(row.get("OF") or row.get("of") or "").strip()
            if not of_code:
                continue
            prioridad = str(row.get("PRIORIDAD") or row.get("prioridad") or "ALTA").strip().upper()
            priorities[of_code] = {
                "prioridad": prioridad,
                "denominacion": str(row.get("DENOMINACION") or row.get("denominacion") or "").strip(),
                "sector": str(row.get("SECTOR") or row.get("sector") or "").strip(),
                "user_email": str(row.get("USER_EMAIL") or row.get("user_email") or "").strip(),
                "user_name": str(row.get("USER_NAME") or row.get("user_name") or "").strip(),
                "updated_at": str(row.get("UPDATED_AT") or row.get("updated_at") or "").strip(),
            }
        if priorities:
            return priorities
    except Exception as e:
        logger.debug(f"Aviso lectura CSV prioridades Google Sheets: {e}")
    return None


# ==============================================================================
# MOTOR 4: GOOGLE SHEETS SERVICE ACCOUNT (GSPREAD SI ESTÁ DISPONIBLE)
# ==============================================================================
def _get_gspread_client():
    """Inicializa cliente gspread si están presentes las credenciales y biblioteca."""
    try:
        import gspread
        from google.oauth2.service_account import Credentials
        scopes = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive"
        ]
        if GOOGLE_SERVICE_ACCOUNT_JSON:
            info = json.loads(GOOGLE_SERVICE_ACCOUNT_JSON)
            creds = Credentials.from_service_account_info(info, scopes=scopes)
            return gspread.authorize(creds)
        elif os.path.exists(GOOGLE_SERVICE_ACCOUNT_FILE):
            creds = Credentials.from_service_account_file(GOOGLE_SERVICE_ACCOUNT_FILE, scopes=scopes)
            return gspread.authorize(creds)
    except Exception as e:
        logger.debug(f"GSpread no configurado o no disponible: {e}")
    return None


def _gspread_read_priorities() -> Optional[Dict[str, Any]]:
    gc = _get_gspread_client()
    if not gc:
        return None
    try:
        sh = gc.open_by_key(SPREADSHEET_ID)
        ws = sh.worksheet("prioridades_pcp")
        records = ws.get_all_records()
        priorities: Dict[str, Any] = {}
        for r in records:
            of_val = str(r.get("OF", "")).strip()
            if not of_val:
                continue
            priorities[of_val] = {
                "prioridad": str(r.get("PRIORIDAD", "ALTA")).strip().upper(),
                "denominacion": str(r.get("DENOMINACION", "")).strip(),
                "sector": str(r.get("SECTOR", "")).strip(),
                "user_email": str(r.get("USER_EMAIL", "")).strip(),
                "user_name": str(r.get("USER_NAME", "")).strip(),
                "updated_at": str(r.get("UPDATED_AT", "")).strip(),
            }
        return priorities
    except Exception as e:
        logger.debug(f"Error gspread lectura prioridades: {e}")
    return None


def _gspread_save_priorities(priorities: Dict[str, Any], log_entry: Optional[Dict[str, Any]] = None) -> bool:
    gc = _get_gspread_client()
    if not gc:
        return False
    try:
        sh = gc.open_by_key(SPREADSHEET_ID)
        try:
            ws = sh.worksheet("prioridades_pcp")
        except Exception:
            ws = sh.add_worksheet(title="prioridades_pcp", rows="200", cols="10")

        headers = ["OF", "PRIORIDAD", "DENOMINACION", "SECTOR", "USER_EMAIL", "USER_NAME", "UPDATED_AT"]
        rows = [headers]
        for of_code, p in priorities.items():
            rows.append([
                of_code,
                p.get("prioridad", "ALTA"),
                p.get("denominacion", ""),
                p.get("sector", ""),
                p.get("user_email", ""),
                p.get("user_name", ""),
                p.get("updated_at", "")
            ])

        ws.clear()
        ws.update("A1", rows)

        if log_entry:
            try:
                try:
                    ws_logs = sh.worksheet("logs_pcp")
                except Exception:
                    ws_logs = sh.add_worksheet(title="logs_pcp", rows="1000", cols="10")
                    ws_logs.append_row(["ID", "TIMESTAMP", "OF", "DENOMINACION", "SECTOR", "OLD_PRIORITY", "NEW_PRIORITY", "USER_EMAIL", "USER_NAME"])

                ws_logs.insert_row([
                    log_entry.get("id", ""),
                    log_entry.get("timestamp", ""),
                    log_entry.get("of", ""),
                    log_entry.get("denominacion", ""),
                    log_entry.get("sector", ""),
                    log_entry.get("old_priority", ""),
                    log_entry.get("new_priority", ""),
                    log_entry.get("user_email", ""),
                    log_entry.get("user_name", "")
                ], 2)
            except Exception as le:
                logger.warning(f"Error guardando log en Google Sheets: {le}")

        return True
    except Exception as e:
        logger.warning(f"Error gspread guardando prioridades: {e}")
        return False


# ==============================================================================
# FUNCIONES PRINCIPALES EXPUESTAS
# ==============================================================================
def get_all_priorities(force_refresh: bool = False) -> Dict[str, Any]:
    """
    Obtiene el mapa de prioridades {OF: {prioridad, user_name, user_email, updated_at}}
    utilizando una estrategia de capas:
    1. Caché en memoria (<1ms si < 10 segundos)
    2. Google Apps Script Webhook
    3. Google Sheets Service Account (gspread)
    4. Google Sheets CSV directo (tab 'prioridades_pcp')
    5. Vercel KV / Upstash Redis
    6. Archivo /tmp local
    """
    global _memory_priorities, _priorities_cache_time
    now = time.time()

    if not force_refresh and _memory_priorities and (now - _priorities_cache_time) < CACHE_TTL_SECONDS:
        return _memory_priorities

    # 1. Google Apps Script Webhook
    wh_data = _gsheets_webhook_get()
    if wh_data and "priorities" in wh_data:
        _memory_priorities = wh_data["priorities"]
        _priorities_cache_time = now
        return _memory_priorities

    # 2. Google Sheets Service Account
    gspread_data = _gspread_read_priorities()
    if gspread_data is not None:
        _memory_priorities = gspread_data
        _priorities_cache_time = now
        return _memory_priorities

    # 3. Google Sheets CSV
    csv_data = _gsheets_csv_read_priorities()
    if csv_data is not None:
        _memory_priorities = csv_data
        _priorities_cache_time = now
        return _memory_priorities

    # 4. Vercel KV / Upstash Redis
    if KV_URL and KV_TOKEN:
        res = _kv_command("get", "kanban:priorities")
        if res:
            try:
                parsed = json.loads(res) if isinstance(res, str) else res
                if isinstance(parsed, dict):
                    _memory_priorities = parsed
                    _priorities_cache_time = now
                    return parsed
            except Exception:
                pass

    # 5. Archivo temporal /tmp
    if os.path.exists(TMP_PRIORITY_FILE):
        try:
            with open(TMP_PRIORITY_FILE, "r", encoding="utf-8") as f:
                loaded = json.load(f)
                if isinstance(loaded, dict):
                    _memory_priorities = loaded
                    _priorities_cache_time = now
                    return _memory_priorities
        except Exception:
            pass

    return _memory_priorities


def save_priorities(priorities: Dict[str, Any], log_entry: Optional[Dict[str, Any]] = None) -> bool:
    """
    Guarda el mapa de prioridades en almacenamiento persistente con respaldo en Google Sheets.
    """
    global _memory_priorities, _priorities_cache_time
    _memory_priorities = priorities
    _priorities_cache_time = time.time()

    # 1. Google Apps Script Webhook
    if GSHEETS_PRIORITIES_URL:
        _gsheets_webhook_post({
            "action": "save_priorities",
            "priorities": priorities,
            "log": log_entry
        })

    # 2. Google Sheets Service Account
    _gspread_save_priorities(priorities, log_entry=log_entry)

    # 3. Vercel KV / Upstash
    if KV_URL and KV_TOKEN:
        _kv_command("set", "kanban:priorities", json.dumps(priorities))

    # 4. Archivo temporal /tmp
    try:
        with open(TMP_PRIORITY_FILE, "w", encoding="utf-8") as f:
            json.dump(priorities, f, ensure_ascii=False, indent=2)
    except Exception:
        pass

    return True


def get_all_logs(force_refresh: bool = False) -> List[Dict[str, Any]]:
    """Obtiene el listado de logs de auditoría."""
    global _memory_logs, _logs_cache_time
    now = time.time()

    if not force_refresh and _memory_logs and (now - _logs_cache_time) < CACHE_TTL_SECONDS:
        return _memory_logs

    # 1. Google Apps Script Webhook
    wh_data = _gsheets_webhook_get()
    if wh_data and "logs" in wh_data and isinstance(wh_data["logs"], list):
        _memory_logs = wh_data["logs"]
        _logs_cache_time = now
        return _memory_logs

    # 2. Vercel KV
    if KV_URL and KV_TOKEN:
        res = _kv_command("get", "kanban:priority_logs")
        if res:
            try:
                parsed = json.loads(res) if isinstance(res, str) else res
                if isinstance(parsed, list):
                    _memory_logs = parsed
                    _logs_cache_time = now
                    return parsed
            except Exception:
                pass

    # 3. Archivo temporal /tmp
    if os.path.exists(TMP_LOGS_FILE):
        try:
            with open(TMP_LOGS_FILE, "r", encoding="utf-8") as f:
                loaded = json.load(f)
                if isinstance(loaded, list):
                    _memory_logs = loaded
                    _logs_cache_time = now
                    return _memory_logs
        except Exception:
            pass

    return _memory_logs


def append_audit_log(entry: Dict[str, Any]) -> bool:
    """Añade una entrada al historial de logs de auditoría de PCP."""
    logs = get_all_logs()
    logs.insert(0, entry)
    logs = logs[:500]

    global _memory_logs, _logs_cache_time
    _memory_logs = logs
    _logs_cache_time = time.time()

    if KV_URL and KV_TOKEN:
        _kv_command("set", "kanban:priority_logs", json.dumps(logs))

    try:
        with open(TMP_LOGS_FILE, "w", encoding="utf-8") as f:
            json.dump(logs, f, ensure_ascii=False, indent=2)
    except Exception:
        pass

    return True
