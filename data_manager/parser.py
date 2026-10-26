import os
import re
import csv
import io
import json
import logging
from datetime import datetime
from typing import Dict, List, Any, Optional, Tuple

import pandas as pd

logger = logging.getLogger("totvs-parser")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

# Normalizaciones comunes de caracteres del ERP / Windows Latin-1 a UTF-8
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

# Mapeo de sinónimos de columnas posibles entre TOTVS / Protheus y la tabla estándar
COLUMN_SYNONYMS = {
    "of": ["of", "numero op", "op", "orden", "orden fabricacion", "numero_op", "nro op", "nro_op"],
    "estado": ["estado", "status", "situacion", "situacao"],
    "fecha_emision": ["fecha emision of", "fecha emision", "emision", "dt. emissao", "dt emissao", "fecha de emision", "dt_emissao"],
    "producto": ["producto", "codigo", "cod. produto", "codigo producto", "cod_prod", "produto", "cod produto"],
    "fecha_apunte": ["fecha de apunte", "fecha apunte", "apunte", "dt. apontamento", "dt apontamento", "dt_apontamento"],
    "operacion": ["operacion", "operacao", "opr", "oper", "secuencia", "seq"],
    "descripcion": ["descripcion", "descricao", "desc", "denominacion producto"],
    "recurso": ["recurso", "maquina", "centro trabajo", "cod. recurso", "cod recurso"],
    "recurso_descripcion": ["recurso descipcion", "recurso descripcion", "desc. recurso", "descricao recurso", "maquina descripcion", "desc recurso"],
    "planificado": ["planificado", "qtd. planificada", "qtd planif", "cantidad planificada", "cant planif", "cantidad", "quantidade", "qtd prev"],
    "producido": ["producido", "qtd. produzida", "qtd produz", "cantidad producida", "cant prod", "producao", "qtd apuntada"],
    "scrap": ["scrap", "refugo", "desecho", "perdida", "rechazo"],
    "lugar_actual": ["lugar actual", "sector actual", "sector", "centro de trabalho", "loc. atual", "loc atual", "sector destino"],
    "proximo_lugar": ["proximo lugar", "próximo lugar", "prximo lugar", "siguiente lugar", "proximo sector", "prox sector", "prox lugar"],
}


def clean_text(val: Any) -> str:
    """Limpia cadenas y corrige caracteres dañados por codificación."""
    if val is None or pd.isna(val):
        return ""
    s = str(val).strip()
    for bad, good in CHAR_REPLACEMENTS.items():
        if bad in s:
            s = s.replace(bad, good)
    return s


def parse_number(val: Any) -> float:
    """Convierte números formateados con comas o puntos a float."""
    if val is None or pd.isna(val):
        return 0.0
    s = str(val).strip()
    if not s:
        return 0.0
    # Remover posibles puntos de miles y reemplazar coma decimal
    if "." in s and "," in s:
        s = s.replace(".", "").replace(",", ".")
    elif "," in s:
        s = s.replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return 0.0


def parse_emission_year(date_str: Any) -> Optional[int]:
    """Extrae el año de la fecha de emisión en múltiples formatos (DD-MM-YYYY, DD/MM/YYYY, YYYY-MM-DD, etc.)."""
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
    """
    Verifica que la fecha de emisión sea como máximo del año pasado.
    Descarta lotes antiguos (ej: 2022 si el año actual es 2026).
    """
    if min_year is None:
        min_year = datetime.now().year - 1
    year = parse_emission_year(date_str)
    if year is not None and year < min_year:
        return False
    return True


def normalize_col_name(col: str) -> str:
    """Normaliza un nombre de columna a minúsculas y sin acentos ni signos raros."""
    s = clean_text(col).lower()
    s = re.sub(r"[áàäâ]", "a", s)
    s = re.sub(r"[éèëê]", "e", s)
    s = re.sub(r"[íìïî]", "i", s)
    s = re.sub(r"[óòöô]", "o", s)
    s = re.sub(r"[úùüû]", "u", s)
    s = re.sub(r"[^a-z0-9]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def find_matching_column(columns: List[str], target_field: str) -> Optional[str]:
    """Busca cuál de las columnas disponibles en la planilla corresponde al campo."""
    synonyms = COLUMN_SYNONYMS.get(target_field, [])
    norm_cols = {col: normalize_col_name(col) for col in columns}

    for col_orig, col_norm in norm_cols.items():
        if col_norm in synonyms:
            return col_orig
    for col_orig, col_norm in norm_cols.items():
        for syn in synonyms:
            if syn in col_norm:
                return col_orig
    return None


def read_file_to_dataframe(file_path: str) -> pd.DataFrame:
    """
    Lee archivos de exportación de TOTVS en múltiples formatos:
    - Excel OpenXML (.xlsx)
    - Excel binario o HTML table (.xls)
    - CSV / TSV / Archivo delimitado (.csv, .txt)
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"No existe el archivo: {file_path}")

    ext = os.path.splitext(file_path)[1].lower()
    logger.info(f"Cargando archivo '{file_path}' (extensión: {ext})...")

    # 1. Archivo .xlsx
    if ext == ".xlsx":
        try:
            return pd.read_excel(file_path, engine="openpyxl")
        except Exception as e:
            logger.warning(f"Falla con openpyxl ({e}), intentando como CSV por si es texto...")

    # 2. Archivo .xls (en TOTVS muchas veces es HTML o XML Spreadsheet)
    if ext == ".xls":
        # Intentar leer primero como HTML (muy habitual en Protheus web)
        try:
            tables = pd.read_html(file_path)
            if tables:
                logger.info("Archivo .xls detectado exitosamente como tabla HTML.")
                return tables[0]
        except Exception:
            pass

        try:
            return pd.read_excel(file_path)
        except Exception as e:
            logger.warning(f"No se pudo leer con pandas excel ({e}), probando CSV...")

    # 3. CSV / Texto delimitado (o fallback de .xls/.xlsx)
    encodings_to_try = ["utf-8", "latin-1", "cp1252", "iso-8859-1"]
    separators_to_try = [";", ",", "\t", "|"]

    for enc in encodings_to_try:
        for sep in separators_to_try:
            try:
                df = pd.read_csv(file_path, sep=sep, encoding=enc, nrows=10)
                if len(df.columns) > 3:
                    # Delimitador y encoding encontrados
                    logger.info(f"Leído exitosamente como delimitado con sep='{sep}' y encoding='{enc}'")
                    return pd.read_csv(file_path, sep=sep, encoding=enc)
            except Exception:
                continue

    raise ValueError(f"No se pudo interpretar el archivo {file_path} en ningún formato conocido.")


def parse_totvs_export(
    file_path: str,
    catalog_path: Optional[str] = None
) -> Tuple[List[Dict[str, Any]], List[str]]:
    """
    Parsea el archivo exportado por TOTVS y devuelve la lista de registros normalizados y sectores.
    """
    df = read_file_to_dataframe(file_path)

    # Cargar catálogo si existe
    catalog: Dict[str, str] = {}
    if catalog_path and os.path.exists(catalog_path):
        try:
            with open(catalog_path, "r", encoding="utf-8") as f:
                catalog = json.load(f)
            logger.info(f"Catálogo cargado con {len(catalog)} artículos.")
        except Exception as e:
            logger.warning(f"No se pudo cargar el catálogo: {e}")

    # Mapear columnas
    cols = list(df.columns)
    col_map = {field: find_matching_column(cols, field) for field in COLUMN_SYNONYMS.keys()}
    logger.info(f"Mapeo de columnas detectado: {col_map}")

    if not col_map.get("of"):
        raise ValueError("No se pudo detectar la columna de OF / Orden de Fabricación en el archivo.")

    records: List[Dict[str, Any]] = []
    sectors_set = set()

    # Optimización: to_dict('records') es hasta 50x más veloz que df.iterrows()
    raw_rows = df.to_dict(orient="records")
    col_of = col_map["of"]
    col_estado = col_map.get("estado")
    col_fecha_emision = col_map.get("fecha_emision")
    col_producto = col_map.get("producto")
    col_fecha_apunte = col_map.get("fecha_apunte")
    col_operacion = col_map.get("operacion")
    col_descripcion = col_map.get("descripcion")
    col_recurso = col_map.get("recurso")
    col_recurso_desc = col_map.get("recurso_descripcion")
    col_planificado = col_map.get("planificado")
    col_producido = col_map.get("producido")
    col_scrap = col_map.get("scrap")
    col_lugar = col_map.get("lugar_actual")
    col_prox = col_map.get("proximo_lugar")

    for idx, row in enumerate(raw_rows):
        of_val = clean_text(row.get(col_of))
        if not of_val:
            continue

        fecha_emision = clean_text(row.get(col_fecha_emision)) if col_fecha_emision else ""
        # REGLA: La fecha de emisión debe ser como máximo del año pasado (descarta 2022 y años anteriores)
        if not is_valid_emission_date(fecha_emision):
            continue

        estado = clean_text(row.get(col_estado)) if col_estado else "PENDIENTE"
        if not estado:
            estado = "PENDIENTE"
        # REGLA: Excluir órdenes finalizadas (Kanban solo muestra producción activa)
        if "FINALIZAD" in estado.upper():
            continue

        lugar_actual = clean_text(row.get(col_lugar)) if col_lugar else "SIN SECTOR"
        if not lugar_actual:
            lugar_actual = "SIN SECTOR"
        if lugar_actual.lower() == "finalizado":
            continue

        producto = clean_text(row.get(col_producto)) if col_producto else ""
        fecha_apunte = clean_text(row.get(col_fecha_apunte)) if col_fecha_apunte else ""
        operacion = clean_text(row.get(col_operacion)) if col_operacion else ""
        descripcion = clean_text(row.get(col_descripcion)) if col_descripcion else ""
        recurso = clean_text(row.get(col_recurso)) if col_recurso else ""
        recurso_desc = clean_text(row.get(col_recurso_desc)) if col_recurso_desc else ""

        planificado = parse_number(row.get(col_planificado)) if col_planificado else 0.0
        producido = parse_number(row.get(col_producido)) if col_producido else 0.0
        scrap = parse_number(row.get(col_scrap)) if col_scrap else 0.0

        prox_lugar = clean_text(row.get(col_prox)) if col_prox else ""

        # Asignar denominación desde el catálogo oficial o descripción
        denominacion = catalog.get(producto, "")
        if not denominacion:
            denominacion = descripcion if descripcion else (f"{recurso_desc} {producto}" if recurso_desc else producto)

        sectors_set.add(lugar_actual)

        record = {
            "id": f"{of_val}_{operacion}_{idx}",
            "of": of_val,
            "estado": estado.upper(),
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
            "proximo_lugar": prox_lugar,
        }
        records.append(record)

    sectors = sorted(list(sectors_set))
    logger.info(f"Procesadas {len(records)} órdenes de fabricación en {len(sectors)} sectores.")
    return records, sectors


def export_clean_csv(records: List[Dict[str, Any]], output_csv_path: str):
    """Genera el CSV limpio con los nombres de columna oficiales de la hoja de Google Sheets."""
    headers = [
        "OF", "ESTADO", "FECHA EMISION OF", "PRODUCTO", "FECHA DE APUNTE",
        "OPERACION", "DESCRIPCION", "RECURSO", "RECURSO DESCIPCION",
        "PLANIFICADO", "PRODUCIDO", "SCRAP", "LUGAR ACTUAL", "PRÓXIMO LUGAR"
    ]
    with open(output_csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(headers)
        for r in records:
            writer.writerow([
                r["of"],
                r["estado"],
                r["fecha_emision"],
                r["producto"],
                r["fecha_apunte"],
                r["operacion"],
                r["descripcion"],
                r["recurso"],
                r["recurso_descripcion"],
                r["planificado"],
                r["producido"],
                r["scrap"],
                r["lugar_actual"],
                r["proximo_lugar"],
            ])
    logger.info(f"CSV limpio guardado en: {output_csv_path}")


def save_cached_json(records: List[Dict[str, Any]], sectors: List[str], output_json_path: str, source: str = "totvs_export"):
    """Guarda el archivo JSON estructurado para el consumo de la app."""
    payload = {
        "records": records,
        "sectors": sectors,
        "last_updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "source": source,
        "total_count": len(records),
    }
    with open(output_json_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    logger.info(f"JSON estructurado guardado en: {output_json_path}")
