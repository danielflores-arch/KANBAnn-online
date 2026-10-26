# Sistema Kanban Digital - SAI Planta Industrial

Arquitectura modular para la visualización de órdenes de fabricación (OF) tanto en pantallas locales de planta como en la nube a través de Vercel.

---

## 🏗️ Arquitectura del Proyecto

El sistema se compone de 3 módulos independientes pero perfectamente sincronizados:

```
D:\KANBAN online\
├── data_manager/        # 1. MOTOR DE DESCARGA Y GESTIÓN DE DATOS (TOTVS Protheus)
│   ├── totvs_downloader.py
│   ├── parser.py
│   ├── gsheets_sync.py
│   ├── run_pipeline.py
│   ├── actualizar_datos.bat
│   └── bucle_actualizacion.bat
│
├── app_local/           # 2. APLICACIÓN KANBAN LOCAL (Puestos de trabajo / TVs de Planta)
│   ├── server.py        (FastAPI en http://localhost:8000)
│   ├── cached_data.json (Autonomía offline)
│   ├── run_local.bat
│   └── static/          (HTML, CSS, JS idénticos)
│
└── app_vercel/          # 3. APLICACIÓN KANBAN VERCEL (Nube / Acceso remoto)
    ├── api/data.py      (Serverless Function ultra-rápida)
    ├── vercel.json
    ├── public/          (Mismos archivos HTML, CSS, JS)
    └── README.md        (Guía de despliegue en Vercel)
```

---

## ⚡ Cómo Usar Cada Módulo

### 1. Módulo de Datos (`data_manager/`)
* **Actualización en 1 clic**: ejecuta `data_manager/actualizar_datos.bat`. Descarga la planilla de TOTVS, la parsea (Excel/CSV), normaliza denominaciones con el catálogo, actualiza la app local y sincroniza con Google Sheets para alimentar Vercel.
* **Bucle desatendido**: ejecuta `data_manager/bucle_actualizacion.bat` para mantener los datos al día cada 10 minutos.

### 2. App Local (`app_local/`)
* Ejecuta `app_local/run_local.bat` o navega a `http://localhost:8000`.
* Funciona con o sin conexión a internet gracias a la caché local generada por el `data_manager`.

### 3. App Vercel (`app_vercel/`)
* Subir la carpeta `app_vercel` a GitHub o desplegar directamente con `vercel`.
* Visualmente y funcionalmente **100% idéntica a la app local**.
* Consulta los datos en tiempo real a través de Google Sheets.
