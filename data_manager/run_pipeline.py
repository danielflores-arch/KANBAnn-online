import os
import sys
import glob
import time
import shutil
import logging
import argparse
from datetime import datetime
from typing import Optional

from parser import parse_totvs_export, export_clean_csv, save_cached_json
from gsheets_sync import sync_to_google_sheets

# Importar descargador de TOTVS
try:
    from totvs_downloader import execute_totvs_download, TARGET_DIR
except ImportError:
    TARGET_DIR = r"D:\Daniel Flores\TOTVS"
    execute_totvs_download = None

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("pipeline-orchestrator")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CATALOG_PATH = os.path.join(BASE_DIR, "product_catalog.json")
CLEAN_CSV_PATH = os.path.join(BASE_DIR, "datos_limpios.csv")
LOCAL_CACHE_PATH = os.path.join(BASE_DIR, "cached_data.json")

# Ruta de la app local a alimentar automáticamente
APP_LOCAL_DIR = os.path.abspath(os.path.join(BASE_DIR, "..", "app_local"))
APP_LOCAL_CACHE = os.path.join(APP_LOCAL_DIR, "cached_data.json")


def get_latest_totvs_file(folder: str) -> Optional[str]:
    """Encuentra el archivo más reciente (.xlsx, .xls, .csv, .txt) en la carpeta indicada."""
    if not os.path.exists(folder):
        return None
    patterns = ["*.xlsx", "*.xls", "*.csv", "*.txt"]
    candidates = []
    for pat in patterns:
        candidates.extend(glob.glob(os.path.join(folder, pat)))
    candidates = [f for f in candidates if not f.endswith(".tmp") and not f.endswith(".crdownload")]
    if not candidates:
        return None
    return max(candidates, key=os.path.getmtime)


def run_pipeline_step(
    download: bool = True,
    headless: bool = True,
    use_guest: bool = True,
    target_folder: str = TARGET_DIR,
    specific_file: Optional[str] = None
) -> bool:
    """
    Ejecuta el pipeline completo de principio a fin:
    1. Descarga TOTVS (si download=True)
    2. Procesa y normaliza los datos
    3. Alimenta la App Local
    4. Sincroniza con Google Sheets (para la App en Vercel)
    """
    file_to_process = specific_file

    if download:
        if execute_totvs_download is None:
            logger.error("No se pudo importar 'totvs_downloader.py'.")
            return False
        logger.info("==================================================")
        logger.info("PASO 1: Descargando última planilla desde TOTVS Protheus...")
        logger.info("==================================================")
        try:
            downloaded = execute_totvs_download(
                headless=headless,
                use_guest=use_guest,
                target_folder=target_folder
            )
            if downloaded and os.path.exists(downloaded):
                file_to_process = downloaded
        except Exception as e:
            logger.error(f"Error durante la descarga de TOTVS: {e}")
            logger.info("Intentando continuar con el último archivo existente...")

    if not file_to_process or not os.path.exists(file_to_process):
        file_to_process = get_latest_totvs_file(target_folder)

    if not file_to_process:
        logger.warning(f"No se encontró ningún archivo de TOTVS para procesar en '{target_folder}'.")
        return False

    logger.info("==================================================")
    logger.info(f"PASO 2: Procesando archivo: {file_to_process}")
    logger.info("==================================================")

    try:
        records, sectors = parse_totvs_export(file_to_process, catalog_path=CATALOG_PATH)
    except Exception as e:
        logger.error(f"Error procesando exportación de TOTVS: {e}")
        return False

    # Exportar CSV limpio
    export_clean_csv(records, CLEAN_CSV_PATH)

    # Guardar JSON local
    save_cached_json(records, sectors, LOCAL_CACHE_PATH, source="totvs_pipeline")

    # Alimentar App Local directamente
    if os.path.exists(APP_LOCAL_DIR):
        try:
            shutil.copy2(LOCAL_CACHE_PATH, APP_LOCAL_CACHE)
            logger.info(f"✅ App Local actualizada con éxito en: {APP_LOCAL_CACHE}")
        except Exception as e:
            logger.warning(f"No se pudo copiar a la app local: {e}")

    logger.info("==================================================")
    logger.info("PASO 3: Sincronizando con Google Sheets (App Vercel)...")
    logger.info("==================================================")
    synced = sync_to_google_sheets(CLEAN_CSV_PATH)
    if synced:
        logger.info("✅ Google Sheets sincronizado -> Vercel consumirá los datos nuevos.")
    else:
        logger.info("ℹ️ Recuerda que puedes subir 'datos_limpios.csv' a Google Sheets para refrescar Vercel.")

    return True


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Orquestador del Módulo de Datos Kanban (TOTVS -> Local -> Vercel)")
    parser.add_argument("--no-download", action="store_true", help="No descargar de TOTVS; usar el archivo más reciente ya existente")
    parser.add_argument("--file", default=None, help="Procesar un archivo específico directamente")
    parser.add_argument("--visible", action="store_true", help="Mostrar ventana de Chrome durante la descarga")
    parser.add_argument("--loop", action="store_true", help="Ejecutar en bucle continuo")
    parser.add_argument("--interval", type=int, default=600, help="Segundos entre ejecuciones en bucle (default: 600s = 10 min)")

    args = parser.parse_args()

    should_download = not args.no_download
    is_headless = not args.visible

    print("\n" + "=" * 60)
    print("  MÓDULO DE GESTIÓN Y SINCRONIZACIÓN DE DATOS KANBAN")
    print(f"  Descarga TOTVS: {'ACTIVADA' if should_download else 'DESACTIVADA (archivo existente)'}")
    print(f"  Modo: {'BUCLE cada ' + str(args.interval // 60) + ' min' if args.loop else 'EJECUCIÓN ÚNICA'}")
    print("=" * 60 + "\n")

    if args.loop:
        ciclo = 1
        while True:
            logger.info(f"--- 🚀 INICIANDO CICLO #{ciclo} ({datetime.now().strftime('%Y-%m-%d %H:%M:%S')}) ---")
            try:
                run_pipeline_step(
                    download=should_download,
                    headless=is_headless,
                    specific_file=args.file,
                )
            except Exception as e:
                logger.error(f"Fallo en ciclo #{ciclo}: {e}")

            logger.info(f"Esperando {args.interval // 60} minutos para el siguiente ciclo...\n")
            time.sleep(args.interval)
            ciclo += 1
    else:
        run_pipeline_step(
            download=should_download,
            headless=is_headless,
            specific_file=args.file,
        )
