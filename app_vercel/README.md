# Kanban Digital - Despliegue en Vercel (con Módulo PCP de Prioridad Alta)

Esta aplicación en la nube cuenta con un sistema exclusivo para el equipo de **PCP (Planificación y Control de la Producción)** con autenticación vía **Gmail / Google Workspace**, asignación de **Prioridad Alta**, ordenación automática y **registro de auditoría de logs**.

---

## 🎯 Características Exclusivas de la Versión Vercel

1. **Cartel de Prioridad Alta**:
   * Las órdenes marcadas por PCP muestran un cartel superior llamativo: `PRIORIDAD ALTA` y borde resaltado.
   * Si una orden no tiene prioridad asignada, permanece como `NORMAL` sin cartel.
2. **Ordenación Automática Superior**:
   * Las órdenes con **Prioridad Alta** se posicionan automáticamente **arriba a la izquierda** del tablero en cada sector.
3. **Autenticación con Gmail / Google Identity**:
   * Botón `Acceso PCP` en el encabezado.
   * Permite iniciar sesión mediante Google Identity Services (GSI) con cuentas autorizadas.
   * Los usuarios autenticados de PCP disponen de un botón directo en cada tarjeta para alternar entre `ALTA` y `NORMAL`.
4. **Registro de Auditoría (Logs de PCP)**:
   * Cada asignación o cambio de prioridad registra:
     * Fecha y hora exacta.
     * Número de Lote / OF y Denominación de la pieza.
     * Sector actual.
     * Cambio de estado (`NORMAL ➔ ALTA` o `ALTA ➔ NORMAL`).
     * Nombre y correo de Gmail del responsable de PCP.
   * Panel visual consultable mediante el botón `📋 Logs PCP` con buscador en tiempo real.

---

## ⚙️ Variables de Entorno en Vercel (Project Settings)

Puedes configurar estas variables en el panel de Vercel:

| Variable | Descripción | Valor por defecto |
| :--- | :--- | :--- |
| `ALLOWED_PCP_EMAILS` | Lista de correos autorizados de PCP separados por coma (admite comodines como `*@sai.com.ar`) | `*@sai.com.ar,danielflores@gmail.com,pcp@sai.com.ar` |
| `GOOGLE_CLIENT_ID` | Client ID de Google Cloud OAuth (para el botón oficial de Google) | *(Opcional, incluye fallback de validación directa)* |
| `GOOGLE_SHEET_CSV_URL` | URL de exportación CSV de la hoja oficial de Google Sheets | Configurada con la hoja oficial de SAI |
| `GSHEETS_PRIORITIES_URL` | URL del Webhook de Google Apps Script para persistencia 100% gratuita de prioridades en Google Sheets | *(Opcional, recomendada para costo cero)* |
| `GSHEETS_PRIORITIES_CSV_URL` | URL CSV para lectura de la pestaña `prioridades_pcp` | Configurada por defecto con Google Sheets oficial |
| `GOOGLE_SERVICE_ACCOUNT_JSON` | Credencial JSON de cuenta de servicio de Google para gspread | *(Opcional)* |
| `KV_REST_API_URL` y `KV_REST_API_TOKEN` | Almacenamiento persistente en la nube (Vercel KV o Upstash Redis) | *(Opcional)* |

---

## 📊 Persistencia de Prioridades PCP en Google Sheets (Costo $0)

Para que las prioridades asignadas por PCP se guarden permanentemente en una pestaña de tu Google Sheet (`prioridades_pcp`) y `logs_pcp` sin necesidad de pagar bases de datos:

1. Abre tu planilla de Google Sheets oficial.
2. Ve al menú **Extensiones > Apps Script**.
3. Pega el siguiente código en el editor:

```javascript
function doGet(e) {
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  var sheet = ss.getSheetByName("prioridades_pcp");
  var logsSheet = ss.getSheetByName("logs_pcp");
  var priorities = {};
  var logs = [];
  
  if (sheet && sheet.getLastRow() > 1) {
    var data = sheet.getDataRange().getValues();
    for (var i = 1; i < data.length; i++) {
      var row = data[i];
      var of = String(row[0]).trim();
      if (!of) continue;
      priorities[of] = {
        prioridad: String(row[1] || "ALTA").trim(),
        denominacion: String(row[2] || ""),
        sector: String(row[3] || ""),
        user_email: String(row[4] || ""),
        user_name: String(row[5] || ""),
        updated_at: String(row[6] || "")
      };
    }
  }
  
  if (logsSheet && logsSheet.getLastRow() > 1) {
    var logData = logsSheet.getDataRange().getValues();
    for (var j = 1; j < logData.length; j++) {
      var l = logData[j];
      logs.push({
        id: String(l[0] || ""),
        timestamp: String(l[1] || ""),
        of: String(l[2] || ""),
        denominacion: String(l[3] || ""),
        sector: String(l[4] || ""),
        old_priority: String(l[5] || ""),
        new_priority: String(l[6] || ""),
        user_email: String(l[7] || ""),
        user_name: String(l[8] || "")
      });
    }
  }
  
  return ContentService.createTextOutput(JSON.stringify({
    status: "ok",
    priorities: priorities,
    logs: logs
  })).setMimeType(ContentService.MimeType.JSON);
}

function doPost(e) {
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  var sheet = ss.getSheetByName("prioridades_pcp");
  if (!sheet) {
    sheet = ss.insertSheet("prioridades_pcp");
    sheet.appendRow(["OF", "PRIORIDAD", "DENOMINACION", "SECTOR", "USER_EMAIL", "USER_NAME", "UPDATED_AT"]);
  }
  
  var payload = JSON.parse(e.postData.contents);
  if (payload.action === "save_priorities" && payload.priorities) {
    sheet.clearContents();
    sheet.appendRow(["OF", "PRIORIDAD", "DENOMINACION", "SECTOR", "USER_EMAIL", "USER_NAME", "UPDATED_AT"]);
    var rows = [];
    for (var of in payload.priorities) {
      var p = payload.priorities[of];
      rows.push([of, p.prioridad, p.denominacion || "", p.sector || "", p.user_email || "", p.user_name || "", p.updated_at || ""]);
    }
    if (rows.length > 0) {
      sheet.getRange(2, 1, rows.length, 7).setValues(rows);
    }
  }
  
  if (payload.log) {
    var logsSheet = ss.getSheetByName("logs_pcp");
    if (!logsSheet) {
      logsSheet = ss.insertSheet("logs_pcp");
      logsSheet.appendRow(["ID", "TIMESTAMP", "OF", "DENOMINACION", "SECTOR", "OLD_PRIORITY", "NEW_PRIORITY", "USER_EMAIL", "USER_NAME"]);
    }
    var l = payload.log;
    logsSheet.insertRowAfter(1);
    logsSheet.getRange(2, 1, 1, 9).setValues([[
      l.id || "", l.timestamp || "", l.of || "", l.denominacion || "", l.sector || "",
      l.old_priority || "", l.new_priority || "", l.user_email || "", l.user_name || ""
    ]]);
  }
  
  return ContentService.createTextOutput(JSON.stringify({ status: "success" }))
    .setMimeType(ContentService.MimeType.JSON);
}
```

4. Haz clic en **Implementar > Nueva implementación**.
5. Tipo: **Aplicación web**.
6. Acceso: **Cualquier usuario** (Anyone).
7. Copia la URL generada y agrégala en Vercel con el nombre `GSHEETS_PRIORITIES_URL`.

¡Listo! Las prioridades quedarán 100% guardadas en tu propia planilla de Google Sheets.

---

## 🚀 Cómo desplegar en Vercel

1. Sube el contenido de la carpeta `app_vercel` a un repositorio de GitHub (o corre `vercel` en la terminal).
2. Conecta el repositorio en [vercel.com](https://vercel.com).
3. Si deseas persistencia en base de datos global de 1 clic:
   * En la pestaña **Storage** de tu proyecto en Vercel, crea una base de datos gratuita **KV** (Upstash) y conéctala al proyecto. Las variables `KV_REST_API_URL` y `KV_REST_API_TOKEN` se configuran solas automáticamente.
4. Haz clic en **Deploy**. ¡Listo!
