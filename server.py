import csv
import io
import json
import logging
import os
import urllib.request
from datetime import datetime
from typing import Dict, List, Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("kanban-server")

app = FastAPI(title="Digital Kanban Local Server")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

GOOGLE_SHEET_CSV_URL = (
    "https://docs.google.com/spreadsheets/d/1U4LtXEf3WE2Uu3U6V0dhBlsI4iINwUdPITRpXx90qg8/export?format=csv&gid=234100709"
)
CACHE_FILE = os.path.join(os.path.dirname(__file__), "cached_data.json")

# In-memory storage
current_data: Dict[str, Any] = {
    "records": [],
    "sectors": [],
    "last_updated": None,
    "source": "uninitialized"
}

def clean_str(val: Any) -> str:
    if val is None:
        return ""
    s = str(val).strip()
    # Normalize known artifacts from upstream ERP/Sheets
    replacements = {
        "INSPECCI\ufffdN": "INSPECCIÓN",
        "INSPECCIN": "INSPECCIÓN",
        "PR\ufffdXIMO": "PRÓXIMO",
        "PRXIMO": "PRÓXIMO",
        "M\ufffdQUINA": "MÁQUINA",
        "MQUINA": "MÁQUINA",
        "L\ufffdSER": "LÁSER",
        "LSER": "LÁSER",
        "MET\ufffdLICO": "METÁLICO",
        "METLICO": "METÁLICO",
        "OPERACI\ufffdN": "OPERACIÓN",
        "OPERACIN": "OPERACIÓN",
    }
    for bad, good in replacements.items():
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

def parse_emission_year(date_str: Any) -> Optional[int]:
    """Extrae el año de la fecha de emisión en múltiples formatos."""
    if not date_str:
        return None
    s = str(date_str).strip()
    match_4 = re.search(r'\b(19\d{2}|20\d{2})\b', s)
    if match_4:
        return int(match_4.group(1))
    for fmt in ("%d/%m/%y", "%d-%m-%y", "%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d", "%Y%m%d"):
        try:
            return datetime.strptime(s, fmt).year
        except ValueError:
            pass
    return None

def is_valid_emission_date(date_str: Any, min_year: Optional[int] = None) -> bool:
    """Verifica que la fecha de emisión sea como máximo del año pasado."""
    if min_year is None:
        min_year = datetime.now().year - 1
    year = parse_emission_year(date_str)
    if year is not None and year < min_year:
        return False
    return True

CATALOG_FILE = os.path.join(os.path.dirname(__file__), "product_catalog.json")
CATALOG_SHEET_URL = (
    "https://docs.google.com/spreadsheets/d/1U4LtXEf3WE2Uu3U6V0dhBlsI4iINwUdPITRpXx90qg8/export?format=csv&gid=1379261464"
)
product_catalog: Dict[str, str] = {}

def load_or_fetch_catalog() -> Dict[str, str]:
    global product_catalog
    if product_catalog:
        return product_catalog

    if os.path.exists(CATALOG_FILE):
        try:
            with open(CATALOG_FILE, "r", encoding="utf-8") as f:
                product_catalog = json.load(f)
                logger.info(f"Loaded {len(product_catalog)} product denominations from local catalog.")
                return product_catalog
        except Exception as e:
            logger.warning(f"Error reading local catalog: {e}")

    try:
        logger.info("Downloading product catalog from ULT REV PROC PROD...")
        req = urllib.request.Request(
            CATALOG_SHEET_URL,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) KanbanLocal/1.0"}
        )
        with urllib.request.urlopen(req, timeout=20) as resp:
            text = resp.read().decode("utf-8", errors="replace")
            reader = csv.DictReader(io.StringIO(text))
            cat = {}
            for r in reader:
                prod = clean_str(r.get("Producto"))
                denom = clean_str(r.get("Denominacion"))
                if prod and denom and prod not in cat:
                    cat[prod] = denom
            product_catalog = cat
            with open(CATALOG_FILE, "w", encoding="utf-8") as f:
                json.dump(product_catalog, f, ensure_ascii=False, indent=2)
            logger.info(f"Saved {len(product_catalog)} product denominations to {CATALOG_FILE}")
            return product_catalog
    except Exception as e:
        logger.warning(f"Could not fetch product catalog: {e}")
        return product_catalog

def fetch_and_parse_sheet() -> Dict[str, Any]:
    global current_data
    csv_bytes = None
    source = "live"

    catalog = load_or_fetch_catalog()

    try:
        logger.info(f"Downloading data from Google Sheets: {GOOGLE_SHEET_CSV_URL}")
        req = urllib.request.Request(
            GOOGLE_SHEET_CSV_URL,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) KanbanLocal/1.0"}
        )
        with urllib.request.urlopen(req, timeout=12) as response:
            csv_bytes = response.read()
    except Exception as e:
        logger.warning(f"Failed to fetch live sheet: {e}. Trying local cache...")
        if os.path.exists(CACHE_FILE):
            try:
                with open(CACHE_FILE, "r", encoding="utf-8") as f:
                    cached = json.load(f)
                    if isinstance(cached, dict) and "records" in cached:
                        cached["records"] = [
                            r for r in cached["records"]
                            if is_valid_emission_date(r.get("fecha_emision"))
                        ]
                    current_data = cached
                    current_data["source"] = "offline_cache"
                    return current_data
            except Exception as ce:
                logger.error(f"Failed to read cache file: {ce}")
        raise HTTPException(status_code=502, detail=f"No se pudo obtener datos de Google Sheets: {e}")

    # Decode CSV
    csv_text = csv_bytes.decode("utf-8", errors="replace")
    reader = csv.DictReader(io.StringIO(csv_text))

    records: List[Dict[str, Any]] = []
    sectors_set = set()

    for idx, row in enumerate(reader):
        if idx >= 5000:
            break
        # Extract fields matching headers
        of = clean_str(row.get("OF"))
        if not of:
            continue

        fecha_emision = clean_str(row.get("FECHA EMISION OF", ""))
        # Regla: fecha de emisión como máximo del año pasado
        if not is_valid_emission_date(fecha_emision):
            continue

        estado = clean_str(row.get("ESTADO", "PENDIENTE")).upper()
        # Regla: Excluir órdenes finalizadas
        if "FINALIZAD" in estado:
            continue

        lugar_actual = clean_str(row.get("LUGAR ACTUAL", "SIN SECTOR"))
        if lugar_actual.lower() == "finalizado":
            continue

        producto = clean_str(row.get("PRODUCTO", ""))
        fecha_apunte = clean_str(row.get("FECHA DE APUNTE", ""))
        operacion = clean_str(row.get("OPERACION", ""))
        descripcion = clean_str(row.get("DESCRIPCION", ""))
        recurso = clean_str(row.get("RECURSO", ""))
        recurso_desc = clean_str(row.get("RECURSO DESCIPCION", ""))
        planificado = parse_num(row.get("PLANIFICADO", 0))
        producido = parse_num(row.get("PRODUCIDO", 0))
        scrap = parse_num(row.get("SCRAP", 0))
        
        # Check potential variation of PRÓXIMO LUGAR
        prox = clean_str(row.get("PRÓXIMO LUGAR") or row.get("PRXIMO LUGAR") or row.get("PROXIMO LUGAR") or "")

        # Lookup official denomination from ULT REV PROC PROD
        denominacion = catalog.get(producto, "")
        if not denominacion:
            denominacion = descripcion if descripcion else (f"{recurso_desc} {producto}" if recurso_desc else producto)

        if lugar_actual:
            sectors_set.add(lugar_actual)

        record = {
            "id": f"{of}_{operacion}_{idx}",
            "of": of,
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
        }
        records.append(record)

    sectors = sorted(list(sectors_set))
    now_iso = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    current_data = {
        "records": records,
        "sectors": sectors,
        "last_updated": now_iso,
        "source": source,
        "total_count": len(records),
    }

    # Save to local cache
    try:
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(current_data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.warning(f"Could not write cache file: {e}")

    return current_data


@app.get("/api/data")
def get_data(force: bool = False):
    """Devuelve los datos actuales del Kanban; si force=True o no hay datos, consulta Google Sheets."""
    global current_data
    if force or not current_data.get("records"):
        try:
            return fetch_and_parse_sheet()
        except HTTPException:
            if current_data.get("records"):
                return current_data
            raise
    return current_data


@app.post("/api/refresh")
def refresh_data():
    """Fuerza la actualización desde Google Sheets."""
    return fetch_and_parse_sheet()


# Serve static files
STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")
if not os.path.exists(STATIC_DIR):
    os.makedirs(STATIC_DIR, exist_ok=True)

@app.get("/")
def serve_index():
    index_file = os.path.join(STATIC_DIR, "index.html")
    if os.path.exists(index_file):
        return FileResponse(index_file)
    return JSONResponse({"message": "Coloca index.html en /static"})

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

if __name__ == "__main__":
    import uvicorn
    # Inicializar datos al arrancar
    try:
        fetch_and_parse_sheet()
        logger.info(f"Cargados {len(current_data['records'])} registros y {len(current_data['sectors'])} sectores.")
    except Exception as e:
        logger.warning(f"No se pudo cargar al inicio: {e}")

    print("\n" + "="*60)
    print("  KANBAN DIGITAL LOCAL INICIADO")
    print("  Accede desde tu navegador en:")
    print("  >>> http://localhost:8000")
    print("="*60 + "\n")
    uvicorn.run(app, host="0.0.0.0", port=8000)
