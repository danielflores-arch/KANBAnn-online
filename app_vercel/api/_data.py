import csv
import io
import json
import logging
import os
import re
import time
import urllib.request
from datetime import datetime
from http.server import BaseHTTPRequestHandler
from typing import Dict, List, Any, Optional

try:
    from _storage import get_all_priorities
except ImportError:
    from storage import get_all_priorities

logger = logging.getLogger("vercel-data")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

GOOGLE_SHEET_CSV_URL = os.environ.get(
    "GOOGLE_SHEET_CSV_URL",
    "https://docs.google.com/spreadsheets/d/1U4LtXEf3WE2Uu3U6V0dhBlsI4iINwUdPITRpXx90qg8/export?format=csv&gid=234100709"
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CATALOG_FILE = os.path.join(BASE_DIR, "product_catalog.json")
CACHE_BACKUP_FILE = os.path.join(BASE_DIR, "cached_data.json")


def load_backup_cache() -> Dict[str, Any]:
    """Carga los datos de respaldo local si Google Sheets aún no está disponible."""
    if os.path.exists(CACHE_BACKUP_FILE):
        try:
            with open(CACHE_BACKUP_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f"No se pudo leer cached_data.json de respaldo: {e}")
    return {"records": [], "sectors": [], "source": "empty", "last_updated": None}

# Normalizaciones comunes de caracteres dañados por codificaciones (Latin-1/UTF-8/Windows-1252)
CHAR_REPLACEMENTS = {
    # Errores con símbolo de reemplazo Unicode \ufffd
    "INSPECCI\ufffdN": "INSPECCIÓN",
    "PR\ufffdXIMO": "PRÓXIMO",
    "M\ufffdQUINA": "MÁQUINA",
    "L\ufffdSER": "LÁSER",
    "MET\ufffdLICO": "METÁLICO",
    "OPERACI\ufffdN": "OPERACIÓN",
    "PRODUCCI\ufffdN": "PRODUCCIÓN",
    "FABRICACI\ufffdN": "FABRICACIÓN",
    # Errores con signo de interrogación '?' (muy común al exportar en ASCII/Windows)
    "MET?LICO": "METÁLICO",
    "INSPECCI?N": "INSPECCIÓN",
    "PR?XIMO": "PRÓXIMO",
    "M?QUINA": "MÁQUINA",
    "L?SER": "LÁSER",
    "OPERACI?N": "OPERACIÓN",
    "PRODUCCI?N": "PRODUCCIÓN",
    "FABRICACI?N": "FABRICACIÓN",
    # Variantes sin tilde frecuentes
    "INSPECCIN": "INSPECCIÓN",
    "PRXIMO": "PRÓXIMO",
    "MQUINA": "MÁQUINA",
    "LSER": "LÁSER",
    "METLICO": "METÁLICO",
    "OPERACIN": "OPERACIÓN",
}

# Caché en memoria del catálogo (evita leer 830KB en disco en cada request)
_CATALOG_CACHE: Optional[Dict[str, str]] = None
_CATALOG_MTIME: float = 0.0

# Caché en memoria de los datos procesados (amortigua llamadas simultáneas y previene cuelgues)
_DATA_CACHE: Optional[Dict[str, Any]] = None
_DATA_CACHE_TIME: float = 0.0
DATA_CACHE_TTL = 5.0  # 5 segundos


def clean_str(val: Any) -> str:
    if val is None:
        return ""
    s = str(val).strip()
    if not s:
        return ""
    for bad, good in CHAR_REPLACEMENTS.items():
        if bad in s:
            s = s.replace(bad, good)
    return s


def parse_num(val: Any) -> float:
    if not val:
        return 0.0
    s = str(val).strip().replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return 0.0


def load_catalog() -> Dict[str, str]:
    """Carga el catálogo en memoria de forma persistente entre invocaciones serverless."""
    global _CATALOG_CACHE, _CATALOG_MTIME
    if not os.path.exists(CATALOG_FILE):
        return {}
    try:
        mtime = os.path.getmtime(CATALOG_FILE)
        if _CATALOG_CACHE is not None and mtime == _CATALOG_MTIME:
            return _CATALOG_CACHE
        with open(CATALOG_FILE, "r", encoding="utf-8") as f:
            _CATALOG_CACHE = json.load(f)
            _CATALOG_MTIME = mtime
            return _CATALOG_CACHE
    except Exception as e:
        logger.warning(f"Error cargando catálogo: {e}")
        return _CATALOG_CACHE or {}


def fetch_kanban_data(force_remote: bool = False) -> Dict[str, Any]:
    """Descarga y normaliza los datos con caché de alta velocidad y fallback de resiliencia."""
    global _DATA_CACHE, _DATA_CACHE_TIME
    now = time.time()

    # Si la caché es reciente y no se fuerza recarga, responder en <1ms
    if not force_remote and _DATA_CACHE is not None and (now - _DATA_CACHE_TIME) < DATA_CACHE_TTL:
        # Actualizar prioridades en memoria de forma instantánea
        priorities = get_all_priorities()
        records = _DATA_CACHE.get("records", [])
        for r in records:
            p_info = priorities.get(r["of"], {})
            prioridad_val = p_info.get("prioridad", "NORMAL")
            r["prioridad"] = prioridad_val
            r["prioridad_info"] = p_info if prioridad_val == "ALTA" else None
        records.sort(key=lambda r: (0 if r.get("prioridad") == "ALTA" else 1))
        _DATA_CACHE["priorities_map"] = priorities
        return _DATA_CACHE

    catalog = load_catalog()
    priorities = get_all_priorities()

    try:
        req = urllib.request.Request(
            GOOGLE_SHEET_CSV_URL,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) KanbanVercel/2.0"}
        )
        with urllib.request.urlopen(req, timeout=10) as response:
            csv_bytes = response.read()
        csv_text = csv_bytes.decode("utf-8", errors="replace")
    except Exception as e:
        logger.warning(f"Error descargando de Google Sheets: {e}")
        if _DATA_CACHE is not None:
            logger.info("Sirviendo datos desde caché previa debido a fallo de red con Google Sheets.")
            return _DATA_CACHE
        backup = load_backup_cache()
        if backup.get("records"):
            logger.info("Sirviendo datos desde archivo de respaldo cached_data.json.")
            _DATA_CACHE = backup
            return backup
        return {
            "records": [],
            "sectors": [],
            "priorities_map": priorities,
            "last_updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "source": "waiting_data_provider",
            "total_count": 0,
            "warning": "Proveedor de datos aún no conectado o en línea."
        }

    reader = csv.DictReader(io.StringIO(csv_text))
    records: List[Dict[str, Any]] = []
    sectors_set = set()

    for idx, row in enumerate(reader):
        of_val = clean_str(row.get("OF"))
        if not of_val:
            continue

        estado = clean_str(row.get("ESTADO", "PENDIENTE")).upper()
        fecha_emision = clean_str(row.get("FECHA EMISION OF", ""))
        producto = clean_str(row.get("PRODUCTO", ""))
        fecha_apunte = clean_str(row.get("FECHA DE APUNTE", ""))
        operacion = clean_str(row.get("OPERACION", ""))
        descripcion = clean_str(row.get("DESCRIPCION", ""))
        recurso = clean_str(row.get("RECURSO", ""))
        recurso_desc = clean_str(row.get("RECURSO DESCIPCION", ""))
        planificado = parse_num(row.get("PLANIFICADO", 0))
        producido = parse_num(row.get("PRODUCIDO", 0))
        scrap = parse_num(row.get("SCRAP", 0))
        lugar_actual = clean_str(row.get("LUGAR ACTUAL", "SIN SECTOR"))
        prox = clean_str(row.get("PRÓXIMO LUGAR") or row.get("PRXIMO LUGAR") or row.get("PROXIMO LUGAR") or "")

        denominacion = catalog.get(producto, "")
        if not denominacion:
            denominacion = descripcion if descripcion else (f"{recurso_desc} {producto}" if recurso_desc else producto)

        if lugar_actual:
            sectors_set.add(lugar_actual)

        p_info = priorities.get(of_val, {})
        prioridad_val = p_info.get("prioridad", "NORMAL")

        records.append({
            "id": f"{of_val}_{operacion}_{idx}",
            "of": of_val,
            "estado": estado,
            "fecha_emision": fecha_emision,
            "producto": producto,
            "denominacion": denominacion,
            "fecha_apunte": fecha_apunte,
            "operacion": operacion,
            "descripcion": descripcion,
            "recurso": recurso,
            "recurso_descripcion": recurso_desc,
            "planificado": planificado,
            "producido": producido,
            "scrap": scrap,
            "lugar_actual": lugar_actual,
            "proximo_lugar": prox,
            "prioridad": prioridad_val,
            "prioridad_info": p_info if prioridad_val == "ALTA" else None,
        })

    # Prioridad Alta siempre arriba a la izquierda
    records.sort(key=lambda r: (0 if r.get("prioridad") == "ALTA" else 1))

    result = {
        "records": records,
        "sectors": sorted(list(sectors_set)),
        "priorities_map": priorities,
        "last_updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "source": "google_sheets_live",
        "total_count": len(records),
    }

    _DATA_CACHE = result
    _DATA_CACHE_TIME = now
    return result


class handler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        try:
            data = fetch_kanban_data()
            payload = json.dumps(data, ensure_ascii=False).encode("utf-8")

            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Cache-Control", "public, s-maxage=5, stale-while-revalidate=15")
            self.end_headers()
            self.wfile.write(payload)
        except Exception as e:
            logger.error(f"Error procesando solicitud /api/data: {e}")
            err_payload = json.dumps({"error": str(e)}).encode("utf-8")
            self.send_response(500)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(err_payload)
