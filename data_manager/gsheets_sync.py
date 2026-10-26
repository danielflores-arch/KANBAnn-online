import os
import csv
import logging
from typing import Optional, List, Dict, Any

try:
    from dotenv import load_dotenv
    load_dotenv()
    _root_env = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".env"))
    if os.path.exists(_root_env):
        load_dotenv(_root_env)
except Exception:
    pass

logger = logging.getLogger("gsheets-sync")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

# ID de la planilla oficial de Google Sheets
DEFAULT_SPREADSHEET_ID = os.getenv("SPREADSHEET_ID", "1U4LtXEf3WE2Uu3U6V0dhBlsI4iINwUdPITRpXx90qg8")
DEFAULT_WORKSHEET_NAME = os.getenv("WORKSHEET_NAME", "datos limpios")
SERVICE_ACCOUNT_FILE = os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE", os.path.join(os.path.dirname(__file__), "service_account.json"))
GOOGLE_SERVICE_ACCOUNT_JSON = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON", "")


def sync_to_google_sheets(
    csv_file_path: str,
    spreadsheet_id: str = DEFAULT_SPREADSHEET_ID,
    worksheet_name: str = DEFAULT_WORKSHEET_NAME,
    service_account_path: str = SERVICE_ACCOUNT_FILE
) -> bool:
    """
    Sube el CSV procesado a Google Sheets usando gspread si existe el archivo de credenciales o la variable de entorno.
    Si no existe credencial, emite una advertencia con instrucciones y no interrumpe el flujo.
    """
    has_creds = bool(GOOGLE_SERVICE_ACCOUNT_JSON or os.path.exists(service_account_path))
    if not has_creds:
        logger.info("ℹ️ Sincronización automática con Google Sheets: Modo Manual / CSV.")
        logger.info(f"   (Para subida 100% desatendida, coloca tu archivo '{os.path.basename(service_account_path)}' en 'data_manager/').")
        logger.info(f"   El archivo '{csv_file_path}' está disponible para importación.")
        return False

    try:
        import json
        import gspread
        from google.oauth2.service_account import Credentials

        scopes = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive"
        ]

        if GOOGLE_SERVICE_ACCOUNT_JSON:
            info = json.loads(GOOGLE_SERVICE_ACCOUNT_JSON)
            creds = Credentials.from_service_account_info(info, scopes=scopes)
        else:
            creds = Credentials.from_service_account_file(service_account_path, scopes=scopes)

        client = gspread.authorize(creds)

        logger.info(f"Conectando a Google Spreadsheet ID: {spreadsheet_id}...")
        sh = client.open_by_key(spreadsheet_id)

        try:
            ws = sh.worksheet(worksheet_name)
        except Exception:
            logger.info(f"Pestaña '{worksheet_name}' no encontrada, usando la primera disponible...")
            ws = sh.get_worksheet(0)

        # Leer filas del CSV limpio
        with open(csv_file_path, "r", encoding="utf-8") as f:
            reader = csv.reader(f)
            rows = list(reader)

        logger.info(f"Actualizando {len(rows)} filas en Google Sheets ({ws.title})...")
        ws.clear()
        try:
            ws.update("A1", rows)
        except TypeError:
            ws.update(values=rows, range_name="A1")
        logger.info("✅ ¡Google Sheets actualizado exitosamente!")
        return True

    except Exception as e:
        logger.error(f"❌ Error al sincronizar con Google Sheets: {e}")
        return False
