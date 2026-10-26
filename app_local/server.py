import csv
import io
import json
import logging
import os
import time
import urllib.request
from datetime import datetime
from typing import Dict, List, Any, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("kanban-local-app")

app = FastAPI(title="Kanban Digital Local - SAI Planta")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CACHE_FILE = os.path.join(BASE_DIR, "cached_data.json")
CATALOG_FILE = os.path.join(BASE_DIR, "product_catalog.json")

GOOGLE_SHEET_CSV_URL = os.getenv(
    "GOOGLE_SHEET_CSV_URL",
    "https://docs.google.com/spreadsheets/d/1U4LtXEf3WE2Uu3U6V0dhBlsI4iINwUdPITRpXx90qg8/export?format=csv&gid=234100709"
)

# Estado en memoria
current_data: Dict[str, Any] = {
    "records": [],
    "sectors": [],
    "last_updated": None,
    "source": "uninitialized"
}

# Cachés en memoria con verificación de mtime
_CATALOG_CACHE: Optional[Dict[str, str]] = None
_CATALOG_MTIME: float = 0.0

_LOCAL_CACHE_MEM: Optional[Dict[str, Any]] = None
_LOCAL_CACHE_MTIME: float = 0.0

# Normalizaciones comunes de caracteres dañados por codificaciones
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
    """Carga el catálogo en memoria y solo vuelve a leer el disco si el archivo fue modificado."""
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


def load_local_cache() -> Optional[Dict[str, Any]]:
    """Carga los datos provistos por data_manager evitando lecturas a disco redundantes."""
    global _LOCAL_CACHE_MEM, _LOCAL_CACHE_MTIME
    if not os.path.exists(CACHE_FILE):
        return None
    try:
        mtime = os.path.getmtime(CACHE_FILE)
        if _LOCAL_CACHE_MEM is not None and mtime == _LOCAL_CACHE_MTIME:
            return _LOCAL_CACHE_MEM
        with open(CACHE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            if data.get("records"):
                _LOCAL_CACHE_MEM = data
                _LOCAL_CACHE_MTIME = mtime
                return _LOCAL_CACHE_MEM
    except Exception as e:
        logger.warning(f"Error leyendo caché local: {e}")
    return _LOCAL_CACHE_MEM


def fetch_and_parse_sheets() -> Dict[str, Any]:
    """Fallback en caso de requerir sincronización directa desde Google Sheets."""
    catalog = load_catalog()

    try:
        req = urllib.request.Request(
            GOOGLE_SHEET_CSV_URL,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) KanbanLocal/2.0"}
        )
        with urllib.request.urlopen(req, timeout=12) as response:
            csv_bytes = response.read()
    except Exception as e:
        logger.warning(f"No se pudo consultar Google Sheets: {e}")
        cached = load_local_cache()
        if cached:
            return cached
        raise HTTPException(status_code=502, detail=f"No hay conexión ni caché local: {e}")

    csv_text = csv_bytes.decode("utf-8", errors="replace")
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
        })

    payload = {
        "records": records,
        "sectors": sorted(list(sectors_set)),
        "last_updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "source": "google_sheets_live",
        "total_count": len(records),
    }

    # Escritura atómica para evitar colisiones con hilos de lectura
    try:
        temp_file = f"{CACHE_FILE}.tmp"
        with open(temp_file, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        os.replace(temp_file, CACHE_FILE)
    except Exception as e:
        logger.debug(f"Aviso guardando caché local: {e}")

    return payload


@app.get("/api/data")
def get_data(force_remote: bool = False):
    """Devuelve los datos del Kanban: prioridad caché local (actualizada por data_manager), o Google Sheets."""
    global current_data

    if not force_remote:
        local_data = load_local_cache()
        if local_data:
            current_data = local_data
            return current_data

    # Fallback o forzado remoto
    current_data = fetch_and_parse_sheets()
    return current_data


@app.post("/api/refresh")
def refresh_data():
    """Fuerza actualización desde Google Sheets."""
    global current_data
    current_data = fetch_and_parse_sheets()
    return current_data


STATIC_DIR = os.path.join(BASE_DIR, "static")

@app.get("/")
def serve_index():
    index_file = os.path.join(STATIC_DIR, "index.html")
    if os.path.exists(index_file):
        return FileResponse(index_file)
    return JSONResponse({"message": "Coloca index.html en /static"})

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

if __name__ == "__main__":
    import uvicorn

    # Precargar datos
    cached = load_local_cache()
    if cached:
        current_data = cached
        logger.info(f"Cargados {len(cached['records'])} registros desde caché local.")
    else:
        try:
            current_data = fetch_and_parse_sheets()
            logger.info(f"Cargados {len(current_data['records'])} registros desde Google Sheets.")
        except Exception as e:
            logger.warning(f"Inicialización diferida: {e}")

    print("\n" + "=" * 60)
    print("  KANBAN DIGITAL LOCAL (PLANTA INDUSTRIAL)")
    print("  URL: http://localhost:8000")
    print("=" * 60 + "\n")

    uvicorn.run(app, host="0.0.0.0", port=8000)
