import os
import sys
import time
import glob
import json
import logging
import argparse
from datetime import datetime
from typing import Optional, List, Dict

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait, Select
from selenium.webdriver.support import expected_conditions as EC

# ==============================================================================
# CONFIGURACIÓN GENERAL (Cargada desde .env o variables de entorno)
# ==============================================================================
try:
    from dotenv import load_dotenv
    load_dotenv()
    _root_env = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".env"))
    if os.path.exists(_root_env):
        load_dotenv(_root_env)
except Exception:
    pass

BASE_URL = os.getenv("TOTVS_URL", "https://sai-protheus.totvs.ar/webapp/")
DEFAULT_USER = os.getenv("TOTVS_USER", "")
DEFAULT_PASS = os.getenv("TOTVS_PASS", "")

# Ruta de destino indicada por el usuario
TARGET_DIR = os.getenv("TOTVS_TARGET_DIR", r"D:\Daniel Flores\TOTVS")
SCREENSHOTS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "logs_descarga"))
os.makedirs(SCREENSHOTS_DIR, exist_ok=True)
LOG_FILE = os.path.join(SCREENSHOTS_DIR, "totvs_descarga.log")
PID_FILE = os.path.join(SCREENSHOTS_DIR, "downloader.pid")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
    ],
)
logger = logging.getLogger("totvs-downloader")

# ==============================================================================
# XPATHS SECUENCIALES EXACTOS
# ==============================================================================
XPATH_USUARIO = (
    "/html/body/ld-root/ng-component/pro-login/po-page-login/po-page-background"
    "/div/div/div[2]/div/form/div/div[1]/div[1]/po-login/po-field-container/div/div[2]/input"
)

XPATH_PASSWORD = (
    "/html/body/ld-root/ng-component/pro-login/po-page-login/po-page-background"
    "/div/div/div[2]/div/form/div/div[2]/div[1]/po-password/po-field-container/div/div[2]/input"
)

XPATH_BTN_LOGIN_SUBMIT = (
    "//po-page-login//button[@type='submit'] | //po-page-login//po-button//button"
)

XPATH_BTN_ENTRAR_SETTINGS = (
    "/html/body/ld-root/ng-component/pro-session-settings/pro-page-background"
    "/div/div/div[1]/div/form/div/div[3]/po-button[2]"
)

XPATH_FAVORITOS = (
    "/html/body/wa-dialog/wa-panel/wa-panel[1]/wa-panel[2]/wa-panel[2]/wa-panel"
    "/wa-panel/wa-panel[1]/wa-panel/wa-panel/wa-panel[2]/wa-panel/wa-panel/wa-panel"
    "/wa-panel/wa-menu/wa-menu-item[1]//span[1]"
)

XPATH_PRODUC_PCP_MOD2 = (
    "/html/body/wa-dialog/wa-panel/wa-panel[1]/wa-panel[2]/wa-panel[2]/wa-panel"
    "/wa-panel/wa-panel[1]/wa-panel/wa-panel/wa-panel[2]/wa-panel/wa-panel/wa-panel"
    "/wa-panel/wa-menu/wa-menu-item[1]/wa-menu-item[5]//span[1]"
)

XPATH_IMPRIMIR_BROWSE = (
    "/html/body/wa-dialog/wa-panel/wa-panel[2]/wa-tab-view/wa-tab-page/wa-dialog"
    "/wa-panel[3]/wa-panel[3]/wa-panel/wa-button[2]//button"
)

XPATH_PLANILLAS = (
    "/html/body/wa-dialog/wa-panel/wa-panel[2]/wa-tab-view/wa-tab-page/wa-dialog[2]"
    "/wa-panel[2]/wa-panel/wa-panel/wa-panel/wa-panel[1]/wa-panel/wa-panel/wa-panel"
    "/wa-panel/wa-panel/wa-button[3]//button"
)

XPATH_COMBO_DONDE_DESCARGA = (
    "/html/body/wa-dialog/wa-panel/wa-panel[2]/wa-tab-view/wa-tab-page/wa-dialog[2]"
    "/wa-panel[2]/wa-panel/wa-panel/wa-panel/wa-panel[2]/wa-panel/wa-panel/wa-panel"
    "/wa-panel/wa-combobox[2]//select"
)

XPATH_BTN_IMPRIMIR = (
    "/html/body/wa-dialog/wa-panel/wa-panel[2]/wa-tab-view/wa-tab-page/wa-dialog[2]"
    "/wa-panel[3]/wa-panel/wa-panel/wa-button[1]//button"
)

XPATH_FILE_PICKER_INPUT = "/html/body/wa-dialog[2]/wa-file-picker//div/input"
XPATH_FILE_PICKER_BTN_ABRIR = "/html/body/wa-dialog[2]/wa-file-picker//button[1]"


# ==============================================================================
# UTILIDADES DE AUTOMATIZACIÓN
# ==============================================================================
def take_screenshot(driver: webdriver.Chrome, name: str):
    os.makedirs(SCREENSHOTS_DIR, exist_ok=True)
    filepath = os.path.join(SCREENSHOTS_DIR, f"{datetime.now().strftime('%H%M%S')}_{name}.png")
    try:
        driver.save_screenshot(filepath)
        logger.info(f"📸 Captura guardada: {filepath}")
    except Exception as e:
        logger.warning(f"No se pudo guardar captura: {e}")


def safe_click(driver: webdriver.Chrome, xpath: str, timeout: int = 40, desc: str = "elemento"):
    """Espera que el elemento sea clickeable y lo presiona."""
    logger.info(f"⏳ Buscando: {desc}...")
    element = WebDriverWait(driver, timeout).until(
        EC.presence_of_element_located((By.XPATH, xpath))
    )
    try:
        driver.execute_script("arguments[0].scrollIntoView({block: 'center', inline: 'center'});", element)
    except Exception:
        pass

    time.sleep(0.5)
    try:
        element.click()
    except Exception as e:
        logger.warning(f"Click nativo en {desc} requirió JS click ({e})")
        driver.execute_script("arguments[0].click();", element)

    logger.info(f"✅ Click realizado en: {desc}")
    return element


def safe_type(driver: webdriver.Chrome, xpath: str, text: str, timeout: int = 40, desc: str = "campo"):
    """Espera que el campo sea visible, lo limpia e ingresa el texto."""
    logger.info(f"⏳ Buscando campo: {desc}...")
    element = WebDriverWait(driver, timeout).until(
        EC.visibility_of_element_located((By.XPATH, xpath))
    )
    element.click()
    element.clear()
    element.send_keys(text)
    logger.info(f"✅ Texto ingresado en: {desc}")
    return element


def create_chrome_driver(
    headless: bool = False,
    use_guest: bool = True,
    profile_directory: Optional[str] = None,
    user_data_dir: Optional[str] = None,
) -> webdriver.Chrome:
    """Crea una instancia de Chrome en Modo Invitado o con perfil específico."""
    os.makedirs(TARGET_DIR, exist_ok=True)

    options = Options()
    if headless:
        options.add_argument("--headless=new")
        options.add_argument("--window-size=1920,1080")
        options.add_argument("--disable-gpu")

    # MODO INVITADO: Se salta completamente la ventana de selección de usuarios
    if use_guest:
        logger.info("Activando MODO INVITADO (--guest): sin selector de perfiles.")
        options.add_argument("--guest")
    elif profile_directory:
        if user_data_dir and os.path.exists(user_data_dir):
            options.add_argument(f"--user-data-dir={user_data_dir}")
        options.add_argument(f"--profile-directory={profile_directory}")
        options.add_argument("--disable-features=ProfilePickerOnStartup")

    options.add_argument("--no-first-run")
    options.add_argument("--no-default-browser-check")

    # Flags para evitar bloqueos del broker y compatibilidad Win 7
    options.add_argument("--ignore-certificate-errors")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument(
        "--user-agent=Mozilla/5.0 (Windows NT 6.1; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/109.0.0.0 Safari/537.36"
    )

    # Configuración de descargas automáticas
    prefs = {
        "download.default_directory": TARGET_DIR,
        "download.prompt_for_download": False,
        "download.directory_upgrade": True,
        "safebrowsing.enabled": True,
    }
    options.add_experimental_option("prefs", prefs)

    logger.info("Iniciando Google Chrome...")
    driver = webdriver.Chrome(options=options)
    try:
        driver.maximize_window()
    except Exception:
        pass
    return driver


# ==============================================================================
# FLUJO PRINCIPAL DE DESCARGA
# ==============================================================================
def execute_totvs_download(
    username: str = DEFAULT_USER,
    password: str = DEFAULT_PASS,
    headless: bool = False,
    use_guest: bool = True,
    profile_dir: Optional[str] = None,
    user_data_dir: Optional[str] = None,
    target_folder: str = TARGET_DIR,
) -> Optional[str]:
    """
    Ejecuta la secuencia completa con tiempos ajustados para computadoras lentas.
    """
    if not username or not password:
        logger.error("❌ Credenciales TOTVS no configuradas. Por favor define TOTVS_USER y TOTVS_PASS en tu archivo .env")
        return None

    os.makedirs(target_folder, exist_ok=True)
    initial_files = set(glob.glob(os.path.join(target_folder, "*")))

    driver = create_chrome_driver(
        headless=headless,
        use_guest=use_guest,
        profile_directory=profile_dir,
        user_data_dir=user_data_dir,
    )

    try:
        # 1. Navegar a la WebApp
        logger.info(f"1. Conectando a {BASE_URL}...")
        driver.get(BASE_URL)
        time.sleep(5)  # Pausa inicial de 5s

        # 2. Completar Usuario y Contraseña
        logger.info("2. Ingresando credenciales...")
        safe_type(driver, XPATH_USUARIO, username, timeout=45, desc="Campo Usuario")
        pass_el = safe_type(driver, XPATH_PASSWORD, password, timeout=20, desc="Campo Contraseña")

        try:
            pass_el.send_keys(Keys.ENTER)
            logger.info("Enviado ENTER en campo contraseña.")
        except Exception:
            pass

        time.sleep(5)  # Pausa de 5s
        try:
            login_btn = driver.find_elements(By.XPATH, XPATH_BTN_LOGIN_SUBMIT)
            if login_btn and login_btn[0].is_displayed():
                login_btn[0].click()
                logger.info("Clic en botón login de po-page-login.")
        except Exception:
            pass

        # 3. Confirmar pantalla de parámetros iniciales (Botón Entrar)
        logger.info("3. Confirmando parámetros iniciales (Botón Entrar)...")
        time.sleep(5)  # Pausa de 5s
        safe_click(driver, XPATH_BTN_ENTRAR_SETTINGS, timeout=45, desc="Botón Entrar (Parámetros)")

        # 4. Clic en Favoritos
        logger.info("4. Accediendo a Menú Favoritos...")
        time.sleep(5)  # Pausa de 5s
        safe_click(driver, XPATH_FAVORITOS, timeout=45, desc="Favoritos")

        # 5. Clic en Produc. Pcp Mod2
        logger.info("5. Seleccionando 'Produc. Pcp Mod2'...")
        time.sleep(5)  # Pausa de 5s
        safe_click(driver, XPATH_PRODUC_PCP_MOD2, timeout=45, desc="Produc. Pcp Mod2")

        # ======================================================================
        # PAUSA ESPECIAL DE 15 SEGUNDOS TRAS ABRIR PRODUC. PCP MOD2
        # ======================================================================
        logger.info("⏳ Esperando 15 segundos para carga pesada de Produc. Pcp Mod2...")
        time.sleep(15)

        # 6. Clic en Imprimir browse
        logger.info("6. Seleccionando 'Imprimir browse'...")
        safe_click(driver, XPATH_IMPRIMIR_BROWSE, timeout=45, desc="Imprimir browse")
        time.sleep(5)  # Pausa de 5s

        # 7. Clic en Planillas
        logger.info("7. Seleccionando 'Planillas'...")
        safe_click(driver, XPATH_PLANILLAS, timeout=40, desc="Botón Planillas")
        time.sleep(5)  # Pausa de 5s

        # 8. Revisar/Seleccionar Dónde se descarga (wa-combobox[2]//select)
        logger.info("8. Verificando combobox 'Dónde se descarga'...")
        try:
            combo_el = WebDriverWait(driver, 20).until(
                EC.presence_of_element_located((By.XPATH, XPATH_COMBO_DONDE_DESCARGA))
            )
            select_obj = Select(combo_el)
            opciones = [opt.text for opt in select_obj.options]
            logger.info(f"Opciones en combobox: {opciones}")
            logger.info(f"Opción seleccionada: {select_obj.first_selected_option.text}")
        except Exception as ce:
            logger.warning(f"Aviso al inspeccionar combobox: {ce}")
        time.sleep(5)  # Pausa de 5s

        # 9. Clic en Imprimir
        logger.info("9. Presionando 'Imprimir'...")
        safe_click(driver, XPATH_BTN_IMPRIMIR, timeout=30, desc="Botón Imprimir")
        time.sleep(5)  # Pausa de 5s

        # 10. En el file-picker, ingresar path de descarga
        logger.info(f"10. Ingresando ruta de descarga: {target_folder}...")
        safe_type(
            driver,
            XPATH_FILE_PICKER_INPUT,
            target_folder,
            timeout=30,
            desc="Ruta en File Picker",
        )
        time.sleep(5)  # Pausa de 5s

        # 11. Clic en botón Abrir del file-picker
        logger.info("11. Confirmando en 'Abrir' del selector...")
        safe_click(driver, XPATH_FILE_PICKER_BTN_ABRIR, timeout=25, desc="Botón Abrir (File Picker)")
        time.sleep(5)  # Pausa de 5s

        # 12. Monitorear carpeta destino esperando el archivo nuevo
        logger.info(f"12. Esperando que TOTVS genere el archivo en '{target_folder}'...")
        detected_file = None
        for seg in range(90):
            time.sleep(1)
            current_files = set(glob.glob(os.path.join(target_folder, "*")))
            new_files = [f for f in (current_files - initial_files) if not f.endswith(".tmp") and not f.endswith(".crdownload")]
            if new_files:
                detected_file = max(new_files, key=os.path.getctime)
                logger.info(f"🎉 ¡Archivo nuevo detectado con éxito!: {detected_file}")
                logger.info(f"Tamaño: {os.path.getsize(detected_file)} bytes")
                break

        if not detected_file:
            logger.warning("No se detectó un archivo nuevo automáticamente tras 90s.")
            take_screenshot(driver, "post_descarga_timeout")

        return detected_file

    except Exception as e:
        logger.error(f"❌ Error en la automatización: {e}")
        take_screenshot(driver, "error_paso")
        raise
    finally:
        try:
            if not headless:
                time.sleep(2)
            driver.quit()
        except Exception:
            pass


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Descargador automático de TOTVS Protheus")
    parser.add_argument("--no-guest", action="store_true", help="Desactiva el modo invitado")
    parser.add_argument("--profile", default=None, help="Nombre de perfil específico (si no usas invitado)")
    parser.add_argument("--headless", action="store_true", help="Ejecutar sin ventana gráfica")
    parser.add_argument("--loop", action="store_true", help="Ejecutar en bucle continuo")
    parser.add_argument("--interval", type=int, default=600, help="Intervalo en segundos entre descargas (por defecto 600 = 10 min)")

    args = parser.parse_args()
    use_guest_mode = not args.no_guest

    # Registrar PID del proceso para facilitar detenerlo
    try:
        with open(PID_FILE, "w", encoding="utf-8") as pf:
            pf.write(str(os.getpid()))
    except Exception as e:
        logger.debug(f"No se pudo escribir PID: {e}")

    print("\n" + "=" * 65)
    print(" INICIANDO DESCARGADOR AUTOMÁTICO DE TOTVS PROTHEUS")
    print(f" Modo: {'Invitado (Guest Mode)' if use_guest_mode else f'Perfil ({args.profile})'}")
    print(f" Visual: {'Segundo plano (Headless)' if args.headless else 'Ventana abierta'}")
    if args.loop:
        print(f" Ejecución: BUCLE cada {args.interval // 60} minutos ({args.interval}s)")
    else:
        print(" Ejecución: Descarga única")
    print("=" * 65 + "\n")

    try:
        if args.loop:
            logger.info(f"🔁 Modo bucle activado: se ejecutará cada {args.interval}s ({args.interval // 60} min).")
            ciclo = 1
            while True:
                logger.info(f"--- 🚀 INICIANDO CICLO #{ciclo} ({datetime.now().strftime('%Y-%m-%d %H:%M:%S')}) ---")
                try:
                    archivo = execute_totvs_download(
                        headless=args.headless,
                        use_guest=use_guest_mode,
                        profile_dir=args.profile,
                    )
                    if archivo:
                        logger.info(f"✅ Ciclo #{ciclo} completado: {archivo}")
                    else:
                        logger.warning(f"⚠️ Ciclo #{ciclo} finalizó sin detectar archivo nuevo.")
                except Exception as err:
                    logger.error(f"❌ Error en ciclo #{ciclo}: {err}")

                proximo = datetime.now().timestamp() + args.interval
                proximo_str = datetime.fromtimestamp(proximo).strftime('%H:%M:%S')
                logger.info(f"💤 Esperando {args.interval // 60} minutos hasta el próximo ciclo ({proximo_str})...\n")
                time.sleep(args.interval)
                ciclo += 1
        else:
            archivo = execute_totvs_download(
                headless=args.headless,
                use_guest=use_guest_mode,
                profile_dir=args.profile,
            )
            if archivo:
                print(f"\n[OK] Descarga completada con éxito: {archivo}\n")
            else:
                print(f"\n[!] Finalizó. Revisa la carpeta {TARGET_DIR}\n")
    except KeyboardInterrupt:
        logger.info("🛑 Proceso detenido manualmente por el usuario.")
    except Exception as err:
        logger.error(f"❌ Falló el proceso principal: {err}")
    finally:
        if os.path.exists(PID_FILE):
            try:
                os.remove(PID_FILE)
            except Exception:
                pass
