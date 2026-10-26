/**
 * KANBAN DIGITAL SAI - TELEVISOR INDUSTRIAL
 * Visualizador de Tablero Muro TV para Pantalla de Planta (Sin scroll ni deformación)
 */

const state = {
  records: [],
  sectors: [],
  selectedSector: "LIMPIEZA DEMET", // Sector modelo
  autoRefreshIntervalSec: 30,
  countdown: 30,
  lastUpdated: null,
};

// Referencias DOM
const dom = {
  clock: document.getElementById("tvClock"),
  sectorName: document.getElementById("tvSectorName"),
  sectorBadge: document.getElementById("tvSectorBadge"),
  sectorSub: document.getElementById("tvSectorSub"),
  metricOrders: document.getElementById("tvMetricOrders"),
  metricPlanned: document.getElementById("tvMetricPlanned"),
  metricProduced: document.getElementById("tvMetricProduced"),
  metricScrap: document.getElementById("tvMetricScrap"),
  sectorTabs: document.getElementById("tvSectorTabs"),
  btnFullscreen: document.getElementById("btnFullscreen"),
  stage: document.getElementById("tvStage"),
};

document.addEventListener("DOMContentLoaded", () => {
  initClock();
  initSectorFromUrl();
  setupEventListeners();
  loadData();
  startAutoRefreshTimer();
});

// Reloj digital TV
function initClock() {
  const update = () => {
    const now = new Date();
    dom.clock.textContent = now.toLocaleTimeString("es-AR", { hour12: false });
  };
  update();
  setInterval(update, 1000);
}

// Parámetro ?sector= en URL
function initSectorFromUrl() {
  const params = new URLSearchParams(window.location.search);
  const sec = params.get("sector");
  if (sec) {
    state.selectedSector = decodeURIComponent(sec);
  }
}

// Cargar datos silenciosamente desde la API local (alimentada por scripts del sistema)
// Validador de regla de negocio: fecha de emisión como máximo del año pasado
function isValidEmissionYear(fechaStr) {
  if (!fechaStr) return true;
  const match = String(fechaStr).match(/\b(19\d{2}|20\d{2})\b/);
  if (match) {
    const year = parseInt(match[1], 10);
    const minYear = new Date().getFullYear() - 1;
    return year >= minYear;
  }
  return true;
}

async function loadData() {
  try {
    const res = await fetch("/api/data");
    if (!res.ok) throw new Error(`HTTP ${res.status}`);

    const data = await res.json();
    const rawRecords = data.records || [];
    state.records = rawRecords.filter((r) => isValidEmissionYear(r.fecha_emision));

    const activeSectors = Array.from(new Set(state.records.map((r) => r.lugar_actual).filter(Boolean)));
    state.sectors = activeSectors.length > 0 ? activeSectors : (data.sectors || []);
    state.lastUpdated = data.last_updated;

    if (!state.sectors.includes(state.selectedSector) && state.sectors.length > 0) {
      state.selectedSector = state.sectors.includes("LIMPIEZA DEMET") ? "LIMPIEZA DEMET" : state.sectors[0];
    }

    renderSectorTabs();
    renderStage();
  } catch (err) {
    console.warn("Aviso al consultar datos locales:", err);
  }
}

// Refresco silencioso periódico para reflejar cambios ejecutados por los scripts del sistema
function startAutoRefreshTimer() {
  setInterval(() => {
    loadData();
  }, 10000); // Consulta cada 10 segundos silenciosamente
}

// Configurar listeners de interfaz y teclado
function setupEventListeners() {
  dom.btnFullscreen.addEventListener("click", toggleFullscreen);

  // Auto-ajustar inmediatamente al cambiar tamaño o entrar a pantalla completa
  window.addEventListener("resize", () => {
    renderStage();
  });

  // Atajos de teclado para planta
  document.addEventListener("keydown", (e) => {
    if (e.key === "f" || e.key === "F") {
      toggleFullscreen();
    }
  });
}

function toggleFullscreen() {
  if (!document.fullscreenElement) {
    document.documentElement.requestFullscreen().catch(() => {});
  } else {
    document.exitFullscreen().catch(() => {});
  }
}

// Renderizar pastillas de sectores
function renderSectorTabs() {
  dom.sectorTabs.innerHTML = "";

  state.sectors.forEach((sec) => {
    const count = state.records.filter((r) => r.lugar_actual === sec).length;
    const btn = document.createElement("button");
    btn.className = `tv-tab-btn ${sec === state.selectedSector ? "active" : ""}`;
    btn.innerHTML = `
      <span>${sec}</span>
      <span style="background: rgba(0,0,0,0.3); padding: 2px 7px; border-radius: 10px; font-size: 11px;">${count}</span>
    `;

    btn.addEventListener("click", () => {
      state.selectedSector = sec;
      const url = new URL(window.location);
      url.searchParams.set("sector", sec);
      window.history.pushState({}, "", url);

      renderSectorTabs();
      renderStage();
    });

    dom.sectorTabs.appendChild(btn);
  });
}

function isHighPriority(record) {
  return true;
}

/**
 * Renderiza el tablero acomodando el 100% de las tarjetas a la pantalla sin scroll ni deformación
 */
function renderStage() {
  const currentSectorRecords = state.records.filter((r) => r.lugar_actual === state.selectedSector);
  const total = currentSectorRecords.length;

  dom.sectorName.textContent = `SECTOR: ${state.selectedSector}`;
  if (state.selectedSector === "LIMPIEZA DEMET") {
    dom.sectorBadge.textContent = "Sector Piloto";
    dom.sectorBadge.style.display = "inline-block";
  } else {
    dom.sectorBadge.textContent = "Sector Planta";
  }

  dom.sectorSub.textContent = `Mostrando ${total} órdenes en este sector`;

  // Métricas
  const totalPlanned = currentSectorRecords.reduce((sum, r) => sum + (r.planificado || 0), 0);
  const totalProduced = currentSectorRecords.reduce((sum, r) => sum + (r.producido || 0), 0);
  const totalScrap = currentSectorRecords.reduce((sum, r) => sum + (r.scrap || 0), 0);

  dom.metricOrders.textContent = total;
  dom.metricPlanned.textContent = totalPlanned;
  dom.metricProduced.textContent = totalProduced;
  dom.metricScrap.textContent = totalScrap;

  dom.stage.innerHTML = "";

  if (total === 0) {
    dom.stage.innerHTML = `
      <div class="tv-empty-box">
        <h2>No hay órdenes en este sector</h2>
        <p>En este momento no hay tarjetas registradas para <strong>${escapeHtml(state.selectedSector)}</strong>.</p>
      </div>
    `;
    return;
  }

  // Dimensiones disponibles en el área visible de la TV
  const stageW = Math.max(300, (dom.stage.clientWidth || window.innerWidth) - 20);
  const stageH = Math.max(200, (dom.stage.clientHeight || (window.innerHeight - 120)) - 20);

  // Dimensiones nativas de la tarjeta (proporción física fija)
  const w0 = 340;
  const h0 = 380;
  let best = null;

  // Probar configuraciones de columnas (C) y filas (R) para maximizar el tamaño sin desbordar
  for (let C = 1; C <= total; C++) {
    const R = Math.ceil(total / C);
    const gap = total <= 4 ? 14 : (total <= 12 ? 10 : 6);
    const wAvail = stageW - (C - 1) * gap;
    const hAvail = stageH - (R - 1) * gap;

    if (wAvail <= 0 || hAvail <= 0) continue;

    const sW = wAvail / (C * w0);
    const sH = hAvail / (R * h0);
    let scale = Math.min(sW, sH);

    // Límite máximo para no sobredimensionar en pantallas 4K con 1 tarjeta
    scale = Math.min(1.25, Math.max(0.18, scale));

    if (!best || scale > best.scale) {
      best = {
        cols: C,
        rows: R,
        scale: scale,
        cardW: Math.floor(w0 * scale),
        cardH: Math.floor(h0 * scale),
        gap: gap
      };
    }
  }

  if (!best) {
    best = { cols: 4, rows: Math.ceil(total / 4), scale: 0.7, cardW: 238, cardH: 266, gap: 8 };
  }

  const gridWrap = document.createElement("div");
  gridWrap.className = "tv-grid-view";
  gridWrap.style.gridTemplateColumns = `repeat(${best.cols}, ${best.cardW}px)`;
  gridWrap.style.gridTemplateRows = `repeat(${best.rows}, ${best.cardH}px)`;
  gridWrap.style.gap = `${best.gap}px`;

  currentSectorRecords.forEach((record, idx) => {
    // Slot con tamaño exacto
    const slot = document.createElement("div");
    slot.className = "tv-card-slot";
    slot.style.width = `${best.cardW}px`;
    slot.style.height = `${best.cardH}px`;

    // Escalador que preserva 100% proporciones y tamaños internos
    const scaler = document.createElement("div");
    scaler.className = "tv-card-scaler";
    scaler.style.transform = `scale(${best.scale})`;

    const cardEl = createTvCardElement(record, `qr_tv_${idx}`);
    scaler.appendChild(cardEl);
    slot.appendChild(scaler);
    gridWrap.appendChild(slot);
  });

  dom.stage.appendChild(gridWrap);

  // Generar códigos QR limpios con tamaño fijo nativo
  currentSectorRecords.forEach((record, idx) => {
    generateOfQrCode(`qr_tv_${idx}`, record.of, 105);
  });
}

/**
 * Crea la tarjeta viajera física con proporciones fijas (340px x 380px)
 */
function createTvCardElement(record, qrId) {
  const container = document.createElement("div");
  container.className = "kanban-tag";

  const denominacion = record.denominacion || record.descripcion || `PRODUCTO ${record.producto}`;
  const hasPriority = isHighPriority(record);

  // Cantidad programada descontando solo si hubo scraps
  const planificado = record.planificado || 0;
  const scrap = record.scrap || 0;
  const cantidadEfectiva = scrap > 0 ? Math.max(0, planificado - scrap) : planificado;

  container.innerHTML = `
    <!-- ETIQUETA ROJA DE PRIORIDAD ALTA -->
    ${hasPriority ? `<div class="tag-priority-badge">PRIORIDAD ALTA</div>` : ""}

    <div class="tag-inner-grid">
      
      <!-- ROW 1: HEADER SAI & REVISIÓN -->
      <div class="tag-row tag-row-header">
        <div class="tag-cell tag-header-brand">SAI</div>
        <div class="tag-cell tag-header-rev">R-16/01 Rev.: 13</div>
      </div>

      <!-- ROW 2: LOTE / OF & FECHA -->
      <div class="tag-row tag-row-of">
        <div class="tag-cell tag-col-of">
          <span class="tag-lbl">Lote / OF</span>
          <span class="tag-val-of">${escapeHtml(record.of)}</span>
        </div>
        <div class="tag-cell tag-col-fecha">
          <span class="tag-lbl">Fecha de Emisión</span>
          <span class="tag-val-fecha">${escapeHtml(record.fecha_emision || "N/A")}</span>
        </div>
      </div>

      <!-- ROW 3: DENOMINACIÓN (ULT REV PROC PROD - FILA C) -->
      <div class="tag-row tag-row-denom">
        <span class="tag-lbl">Denominación</span>
        <div class="tag-val-denom">${escapeHtml(denominacion)}</div>
      </div>

      <!-- ROW 4: CÓDIGO DE PIEZA & CANTIDAD -->
      <div class="tag-row tag-row-prod">
        <div class="tag-cell tag-col-prod">
          <span class="tag-lbl">Código de Pieza</span>
          <span class="tag-val-prod">${escapeHtml(record.producto)}</span>
        </div>
        <div class="tag-cell tag-col-cant">
          <span class="tag-lbl">Cantidad</span>
          <div class="tag-val-cant">
            <span>${cantidadEfectiva}</span>
            ${scrap > 0 ? `<span class="tag-cant-scrap">(-${scrap})</span>` : ""}
          </div>
        </div>
      </div>

      <!-- ROW 5: PM & MARCA -->
      <div class="tag-row tag-row-pm">
        <div class="tag-cell tag-col-pm-lbl">PM</div>
        <div class="tag-cell tag-col-pm-val">OP ${escapeHtml(record.operacion || "10")}</div>
        <div class="tag-cell tag-col-marca-lbl">Marca</div>
        <div class="tag-cell tag-col-marca-val">SAI</div>
      </div>

      <!-- SECCIÓN INFERIOR: DETALLES TÉCNICOS + QR -->
      <div class="tag-bottom-split">
        
        <!-- LADO IZQUIERDO -->
        <div class="tag-split-left">
          <div class="split-row">
            <span class="split-lbl">MP</span>
            <span class="split-val">-</span>
          </div>
          <div class="split-row">
            <span class="split-lbl">CMP</span>
            <span class="split-val">-</span>
          </div>
          <div class="split-row">
            <span class="split-lbl">Lote MP</span>
            <span class="split-val">-</span>
          </div>
          <div class="split-row" title="${escapeHtml(record.recurso_descripcion)}">
            <span class="split-lbl">SISTEMA</span>
            <span class="split-val">${escapeHtml(record.recurso_descripcion || record.recurso || "-")}</span>
          </div>
          <div class="split-row">
            <span class="split-lbl">PRIORIDAD</span>
            <span class="split-val" style="color: #dc2626; font-weight: 900;">${hasPriority ? "ALTA" : "NORMAL"}</span>
          </div>
        </div>

        <!-- LADO DERECHO: QR CODE -->
        <div class="tag-split-right">
          <div class="qr-box" id="${qrId}"></div>
        </div>

      </div>

    </div>
  `;

  return container;
}

/**
 * Genera el QR Code conteniendo exclusivamente la OF de la Columna A
 */
function generateOfQrCode(containerId, ofValue, size = 105) {
  const container = document.getElementById(containerId);
  if (!container) return;
  container.innerHTML = "";

  const qrText = String(ofValue || "").trim();

  try {
    new QRCode(container, {
      text: qrText,
      width: size,
      height: size,
      colorDark: "#000000",
      colorLight: "#ffffff",
      correctLevel: QRCode.CorrectLevel.M
    });
  } catch (err) {
    console.error("Error generando QR para OF:", ofValue, err);
  }
}

function escapeHtml(str) {
  if (!str) return "";
  return str
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}
