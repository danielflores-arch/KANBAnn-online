# Módulo de Descarga y Gestión de Datos (TOTVS -> Local / Vercel)

Este módulo es el motor central de datos. Se encarga de:
1. Conectarse y descargar automáticamente la planilla de producción desde **TOTVS Protheus** vía Selenium.
2. Soportar múltiples formatos de exportación de TOTVS: Excel (`.xlsx`, `.xls`) y delimitados (`.csv`, `.txt`).
3. Normalizar codificación, tildes y mapear columnas automáticamente.
4. Cruzar el código de pieza con el catálogo oficial `product_catalog.json` para obtener la denominación oficial.
5. Alimentar **automáticamente la App Local** actualizando su archivo `cached_data.json`.
6. Generar `datos_limpios.csv` y sincronizarlo con **Google Sheets** para alimentar en tiempo real la **App en Vercel**.

---

## 🚀 Archivos y Scripts

* `run_pipeline.py`: Script maestro orquestador.
* `actualizar_datos.bat`: Doble clic para ejecutar una actualización completa (descarga TOTVS + procesa + actualiza local + sube a Google Sheets).
* `bucle_actualizacion.bat`: Mantiene el sistema actualizado automáticamente en bucle cada 10 minutos en segundo plano.
* `procesar_archivo_existente.bat`: Procesa el último archivo que ya tengas descargado en `D:\Daniel Flores\TOTVS` sin abrir el navegador.
* `totvs_downloader.py`: Robot de Selenium para la WebApp de TOTVS.
* `parser.py`: Parser inteligente de Excel / CSV y catálogo de productos.
* `gsheets_sync.py`: Sincronizador con Google Sheets usando `gspread`.

---

## ⚙️ Sincronización Automática con Google Sheets (Opcional)

Si deseas que la subida a Google Sheets sea 100% desatendida sin intervención humana:
1. Crea una cuenta de servicio en Google Cloud Console y descarga el archivo JSON de credenciales.
2. Nómbralo `service_account.json` y colócalo en esta carpeta (`data_manager/service_account.json`).
3. Comparte tu hoja de Google Sheets con el email de la cuenta de servicio (con permisos de Editor).
Si no colocas el archivo, el módulo genera `datos_limpios.csv` que puedes importar o pegar cuando gustes.
