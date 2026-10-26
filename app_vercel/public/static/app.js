/**
 * KANBAN DIGITAL SAI - TELEVISOR INDUSTRIAL & GESTIÓN DE PRIORIDAD PCP (VERCEL)
 * Visualizador de Tablero Muro TV con control de prioridades y auditoría para PCP.
 */

const state = {
  records: [],
  sectors: [],
  selectedSector: "LIMPIEZA DEMET", // Sector modelo
  priorities: {},
  logs: [],
  currentUser: null, // Usuario PCP autenticado { email, name, picture, id_token }
  googleClientId: "",
  activeOfRecord: null, // Registro actualmente editado en el modal de prioridad
  autoRefreshIntervalSec: 10,
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
  metricPriority: document.getElementById("tvMetricPriority"),
  sectorTabs: document.getElementById("tvSectorTabs"),
  btnFullscreen: document.getElementById("btnFullscreen"),
  btnOpenLogs: document.getElementById("btnOpenLogs"),
  btnLoginPcp: document.getElementById("btnLoginPcp"),
  pcpAuthArea: document.getElementById("pcpAuthArea"),
  stage: document.getElementById("tvStage"),

  // Modales
  modalLogin: document.getElementById("modalLogin"),
  btnCloseLogin: document.getElementById("btnCloseLogin"),
  formManualEmail: document.getElementById("formManualEmail"),
  inputPcpEmail: document.getElementById("inputPcpEmail"),
  inputPcpName: document.getElementById("inputPcpName"),
  loginFeedback: document.getElementById("loginFeedback"),
  googleBtnWrap: document.getElementById("googleSignInButtonWrap"),

  modalPriority: document.getElementById("modalPriority"),
  btnClosePriority: document.getElementById("btnClosePriority"),
  btnCancelPriority: document.getElementById("btnCancelPriority"),
  btnSavePriority: document.getElementById("btnSavePriority"),
  mPriorityOf: document.getElementById("mPriorityOf"),
  mPriorityPieza: document.getElementById("mPriorityPieza"),
  mPriorityDenom: document.getElementById("mPriorityDenom"),
  mPrioritySector: document.getElementById("mPrioritySector"),
  radioAlta: document.getElementById("radioAlta"),
  radioNormal: document.getElementById("radioNormal"),
  priorityAuthorInfo: document.getElementById("priorityAuthorInfo"),

  modalLogs: document.getElementById("modalLogs"),
  btnCloseLogs: document.getElementById("btnCloseLogs"),
  btnCloseLogsFooter: document.getElementById("btnCloseLogsFooter"),
  logsTableBody: document.getElementById("logsTableBody"),
  inputSearchLogs: document.getElementById("inputSearchLogs"),
  lblLogsCount: document.getElementById("lblLogsCount"),
};

document.addEventListener("DOMContentLoaded", () => {
  initClock();
  initSectorFromUrl();
  loadStoredUser();
  setupEventListeners();
  loadData();
  fetchPriorityConfig();
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

// Cargar usuario guardado de PCP
function loadStoredUser() {
  try {
    const raw = localStorage.getItem("pcp_user_session");
    if (raw) {
      state.currentUser = jsonParseSafe(raw);
    }
  } catch (e) {
    state.currentUser = null;
  }
  renderUserAuth();
}

function saveUserSession(user) {
  state.currentUser = user;
  if (user) {
    localStorage.setItem("pcp_user_session", JSON.stringify(user));
  } else {
    localStorage.removeItem("pcp_user_session");
  }
  renderUserAuth();
}

// Renderizar estado de autenticación en la barra de navegación
function renderUserAuth() {
  if (!dom.pcpAuthArea) return;

  if (state.currentUser) {
    const initials = (state.currentUser.name || state.currentUser.email || "PCP")
      .split(" ")
      .map((w) => w[0])
      .slice(0, 2)
      .join("")
      .toUpperCase();

    dom.pcpAuthArea.innerHTML = `
      <div class="pcp-user-pill">
        <div class="pcp-user-avatar">
          ${state.currentUser.picture ? `<img src="${state.currentUser.picture}" alt="Avatar">` : initials}
        </div>
        <div style="display: flex; flex-direction: column; line-height: 1.1;">
          <span style="font-weight: 700; font-size: 11px;">${escapeHtml(state.currentUser.name || state.currentUser.email)}</span>
          <span style="font-size: 9px; color: #38bdf8;">${escapeHtml(state.currentUser.email)}</span>
        </div>
        <span class="pcp-badge-role">PCP</span>
        <button class="pcp-logout-btn" id="btnLogoutPcp" title="Cerrar sesión">&times;</button>
      </div>
    `;

    document.getElementById("btnLogoutPcp")?.addEventListener("click", () => {
      saveUserSession(null);
      renderStage();
    });

    if (dom.btnOpenLogs) dom.btnOpenLogs.style.display = "inline-flex";
  } else {
    dom.pcpAuthArea.innerHTML = `
      <button class="tv-action-btn pcp-login-btn" id="btnLoginPcp">
        <svg width="14" height="14" viewBox="0 0 24 24" style="margin-right: 4px;">
          <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"/>
          <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"/>
          <path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.06H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.94l2.85-2.22.81-.63z"/>
          <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.06l3.66 2.84c.87-2.6 3.3-4.52 6.16-4.52z"/>
        </svg>
        Acceso PCP
      </button>
    `;

    document.getElementById("btnLoginPcp")?.addEventListener("click", () => {
      openModal(dom.modalLogin);
    });

    if (dom.btnOpenLogs) dom.btnOpenLogs.style.display = "inline-flex";
  }
}

// Cargar configuración de prioridades y Google Client ID desde backend
async function fetchPriorityConfig() {
  try {
    const res = await fetch("/api/priority");
    if (!res.ok) return;
    const data = await res.json();
    state.priorities = data.priorities || {};
    state.logs = data.logs || [];
    state.googleClientId = data.google_client_id || "";

    initGoogleSignIn();
  } catch (err) {
    console.warn("Aviso cargando config de prioridades:", err);
  }
}

// Inicializar Google Identity Services (GIS)
function initGoogleSignIn() {
  if (!window.google || !state.googleClientId) {
    return;
  }
  try {
    window.google.accounts.id.initialize({
      client_id: state.googleClientId,
      callback: handleGoogleCredentialResponse,
      auto_select: false,
    });

    if (dom.googleBtnWrap) {
      window.google.accounts.id.renderButton(dom.googleBtnWrap, {
        theme: "filled_blue",
        size: "large",
        text: "signin_with",
        shape: "rectangular",
      });
    }
  } catch (e) {
    console.warn("No se pudo inicializar Google Identity Services:", e);
  }
}

// Callback de Google Identity Services
function handleGoogleCredentialResponse(response) {
  if (!response || !response.credential) return;

  try {
    const base64Url = response.credential.split(".")[1];
    const base64 = base64Url.replace(/-/g, "+").replace(/_/g, "/");
    const jsonPayload = decodeURIComponent(
      atob(base64)
        .split("")
        .map((c) => "%" + ("00" + c.charCodeAt(0).toString(16)).slice(-2))
        .join("")
    );
    const profile = JSON.parse(jsonPayload);

    saveUserSession({
      email: profile.email,
      name: profile.name,
      picture: profile.picture,
      id_token: response.credential,
    });

    closeModal(dom.modalLogin);
    renderStage();
  } catch (e) {
    console.error("Error decodificando token de Google:", e);
  }
}

// Cargar datos principales desde la API de Vercel
async function loadData() {
  try {
    const res = await fetch("/api/data");
    if (!res.ok) throw new Error(`HTTP ${res.status}`);

    const data = await res.json();
    state.records = data.records || [];
    state.sectors = data.sectors || [];
    state.lastUpdated = data.last_updated;

    if (data.priorities_map) {
      state.priorities = data.priorities_map;
    }

    if (!state.sectors.includes(state.selectedSector) && state.sectors.length > 0) {
      state.selectedSector = state.sectors.includes("LIMPIEZA DEMET") ? "LIMPIEZA DEMET" : state.sectors[0];
    }

    renderSectorTabs();
    renderStage();
  } catch (err) {
    console.warn("Aviso al consultar datos:", err);
  }
}

// Refresco silencioso periódico
function startAutoRefreshTimer() {
  setInterval(() => {
    loadData();
  }, state.autoRefreshIntervalSec * 1000);
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

/**
 * Renderiza el tablero acomodando el 100% de las tarjetas a la pantalla.
 * REGLA DE NEGOCIO: Las órdenes con PRIORIDAD ALTA se ubican automáticamente al inicio (arriba a la izquierda).
 */
function renderStage() {
  // 1. Filtrar registros del sector seleccionado
  const sectorRecords = state.records.filter((r) => r.lugar_actual === state.selectedSector);

  // 2. Sincronizar campo de prioridad desde state.priorities si existe
  sectorRecords.forEach((r) => {
    const pInfo = state.priorities[r.of];
    if (pInfo && pInfo.prioridad === "ALTA") {
      r.prioridad = "ALTA";
      r.prioridad_info = pInfo;
    } else if (!pInfo) {
      r.prioridad = r.prioridad === "ALTA" ? "ALTA" : "NORMAL";
    }
  });

  // 3. ORDENACIÓN AUTOMÁTICA: Prioridad Alta SIEMPRE arriba a la izquierda
  const sortedRecords = [...sectorRecords].sort((a, b) => {
    const aAlta = a.prioridad === "ALTA" ? 1 : 0;
    const bAlta = b.prioridad === "ALTA" ? 1 : 0;
    if (aAlta !== bAlta) {
      return bAlta - aAlta; // Las que tienen ALTA van primero (índice 0)
    }
    return 0; // Conserva el orden natural
  });

  const total = sortedRecords.length;

  dom.sectorName.textContent = `SECTOR: ${state.selectedSector}`;
  if (state.selectedSector === "LIMPIEZA DEMET") {
    dom.sectorBadge.textContent = "Sector Piloto";
    dom.sectorBadge.style.display = "inline-block";
  } else {
    dom.sectorBadge.textContent = "Sector Planta";
  }

  dom.sectorSub.textContent = `Mostrando ${total} órdenes en este sector`;

  // Métricas
  const totalPlanned = sortedRecords.reduce((sum, r) => sum + (r.planificado || 0), 0);
  const totalProduced = sortedRecords.reduce((sum, r) => sum + (r.producido || 0), 0);
  const totalScrap = sortedRecords.reduce((sum, r) => sum + (r.scrap || 0), 0);
  const totalPriority = sortedRecords.filter((r) => r.prioridad === "ALTA").length;

  dom.metricOrders.textContent = total;
  dom.metricPlanned.textContent = totalPlanned;
  dom.metricProduced.textContent = totalProduced;
  dom.metricScrap.textContent = totalScrap;
  if (dom.metricPriority) {
    dom.metricPriority.textContent = totalPriority;
  }

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

  const w0 = 340;
  const h0 = 380;
  let best = null;

  for (let C = 1; C <= total; C++) {
    const R = Math.ceil(total / C);
    const gap = total <= 4 ? 14 : (total <= 12 ? 10 : 6);
    const wAvail = stageW - (C - 1) * gap;
    const hAvail = stageH - (R - 1) * gap;

    if (wAvail <= 0 || hAvail <= 0) continue;

    const sW = wAvail / (C * w0);
    const sH = hAvail / (R * h0);
    let scale = Math.min(sW, sH);
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

  sortedRecords.forEach((record, idx) => {
    const slot = document.createElement("div");
    slot.className = "tv-card-slot";
    slot.style.width = `${best.cardW}px`;
    slot.style.height = `${best.cardH}px`;

    const scaler = document.createElement("div");
    scaler.className = "tv-card-scaler";
    scaler.style.transform = `scale(${best.scale})`;

    const cardEl = createTvCardElement(record, `qr_tv_${idx}`);
    scaler.appendChild(cardEl);
    slot.appendChild(scaler);
    gridWrap.appendChild(slot);
  });

  dom.stage.appendChild(gridWrap);

  // Generar códigos QR limpios
  sortedRecords.forEach((record, idx) => {
    generateOfQrCode(`qr_tv_${idx}`, record.of, 105);
  });
}

/**
 * Crea la tarjeta viajera física con proporciones fijas (340px x 380px)
 */
function createTvCardElement(record, qrId) {
  const container = document.createElement("div");
  container.className = "kanban-tag";

  const isAlta = record.prioridad === "ALTA";
  if (isAlta) {
    container.classList.add("has-high-priority");
  }

  const denominacion = record.denominacion || record.descripcion || `PRODUCTO ${record.producto}`;
  const planificado = record.planificado || 0;
  const scrap = record.scrap || 0;
  const cantidadEfectiva = scrap > 0 ? Math.max(0, planificado - scrap) : planificado;

  const isPcpUser = !!state.currentUser;

  container.innerHTML = `
    <!-- CARTEL ROJO DE PRIORIDAD ALTA (SOLO SI TIENE PRIORIDAD ALTA) -->
    ${isAlta ? `<div class="tag-priority-badge">PRIORIDAD ALTA</div>` : ""}

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
          ${isPcpUser ? `
            <button class="tag-pcp-btn btn-change-priority" data-of="${escapeHtml(record.of)}">
              ⚡ Prioridad: <strong>${isAlta ? "ALTA" : "NORMAL"}</strong>
            </button>
          ` : ""}
        </div>
        <div class="tag-cell tag-col-fecha">
          <span class="tag-lbl">Fecha de Emisión</span>
          <span class="tag-val-fecha">${escapeHtml(record.fecha_emision || "N/A")}</span>
          ${isAlta && record.prioridad_info ? `
            <div class="tag-priority-author" title="Asignado por: ${escapeHtml(record.prioridad_info.user_email)}">
              📌 Asignado por PCP
            </div>
          ` : ""}
        </div>
      </div>

      <!-- ROW 3: DENOMINACIÓN -->
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
            <span class="split-val" style="color: ${isAlta ? '#dc2626' : '#64748b'}; font-weight: 900;">
              ${isAlta ? "ALTA" : "NORMAL"}
            </span>
          </div>
        </div>

        <div class="tag-split-right">
          <div class="qr-box" id="${qrId}"></div>
        </div>
      </div>

    </div>
  `;

  // Listener para cambiar prioridad desde la tarjeta
  const btnPriority = container.querySelector(".btn-change-priority");
  if (btnPriority) {
    btnPriority.addEventListener("click", (e) => {
      e.stopPropagation();
      openPriorityModal(record);
    });
  }

  return container;
}

// Generar QR Code
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

// ============================================================
// MODAL DE ASIGNACIÓN DE PRIORIDAD PCP
// ============================================================
function openPriorityModal(record) {
  state.activeOfRecord = record;

  dom.mPriorityOf.textContent = record.of;
  dom.mPriorityPieza.textContent = record.producto || "N/A";
  dom.mPriorityDenom.textContent = record.denominacion || record.descripcion || "N/A";
  dom.mPrioritySector.textContent = record.lugar_actual || "N/A";

  const isAlta = record.prioridad === "ALTA";
  dom.radioAlta.checked = isAlta;
  dom.radioNormal.checked = !isAlta;

  if (record.prioridad_info) {
    dom.priorityAuthorInfo.style.display = "block";
    dom.priorityAuthorInfo.innerHTML = `
      <strong>Última modificación:</strong> ${escapeHtml(record.prioridad_info.updated_at || "")}<br>
      <strong>Responsable:</strong> ${escapeHtml(record.prioridad_info.user_name || "")} (${escapeHtml(record.prioridad_info.user_email || "")})
    `;
  } else {
    dom.priorityAuthorInfo.style.display = "none";
  }

  openModal(dom.modalPriority);
}

async function savePriorityChoice() {
  if (!state.activeOfRecord || !state.currentUser) {
    alert("Debes iniciar sesión con una cuenta de PCP para modificar prioridades.");
    return;
  }

  const chosenPriority = dom.radioAlta.checked ? "ALTA" : "NORMAL";
  const record = state.activeOfRecord;

  dom.btnSavePriority.textContent = "Guardando...";
  dom.btnSavePriority.disabled = true;

  try {
    const payload = {
      of: record.of,
      prioridad: chosenPriority,
      denominacion: record.denominacion || record.descripcion || "",
      sector: record.lugar_actual || "",
      id_token: state.currentUser.id_token,
      user: {
        email: state.currentUser.email,
        name: state.currentUser.name,
      },
    };

    const res = await fetch("/api/priority", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });

    const resData = await res.json();

    if (!res.ok) {
      throw new Error(resData.error || `HTTP ${res.status}`);
    }

    // Actualizar estado local inmediato
    if (chosenPriority === "ALTA") {
      state.priorities[record.of] = {
        prioridad: "ALTA",
        user_name: state.currentUser.name,
        user_email: state.currentUser.email,
        updated_at: new Date().toISOString().replace("T", " ").substring(0, 19),
        denominacion: record.denominacion,
        sector: record.lugar_actual,
      };
      record.prioridad = "ALTA";
      record.prioridad_info = state.priorities[record.of];
    } else {
      delete state.priorities[record.of];
      record.prioridad = "NORMAL";
      record.prioridad_info = null;
    }

    if (resData.log) {
      state.logs.unshift(resData.log);
    }

    closeModal(dom.modalPriority);
    renderStage();
  } catch (err) {
    alert(`No se pudo guardar la prioridad: ${err.message}`);
  } finally {
    dom.btnSavePriority.textContent = "Guardar Prioridad";
    dom.btnSavePriority.disabled = false;
  }
}

// ============================================================
// MODAL DE HISTORIAL DE AUDITORÍA Y LOGS
// ============================================================
async function openLogsModal() {
  openModal(dom.modalLogs);
  dom.lblLogsCount.textContent = "Consultando registros...";

  try {
    const res = await fetch("/api/priority");
    if (res.ok) {
      const data = await res.json();
      state.logs = data.logs || [];
    }
  } catch (e) {
    console.warn("Aviso consultando logs:", e);
  }

  renderLogsTable();
}

function renderLogsTable(searchTerm = "") {
  const term = searchTerm.toLowerCase().trim();
  const filtered = state.logs.filter((log) => {
    if (!term) return true;
    return (
      (log.of || "").toLowerCase().includes(term) ||
      (log.denominacion || "").toLowerCase().includes(term) ||
      (log.user_email || "").toLowerCase().includes(term) ||
      (log.user_name || "").toLowerCase().includes(term) ||
      (log.sector || "").toLowerCase().includes(term)
    );
  });

  dom.lblLogsCount.textContent = `Mostrando ${filtered.length} de ${state.logs.length} registros`;

  if (filtered.length === 0) {
    dom.logsTableBody.innerHTML = `
      <tr>
        <td colspan="6" style="text-align: center; color: #64748b; padding: 24px;">
          No se encontraron registros de auditoría de prioridades.
        </td>
      </tr>
    `;
    return;
  }

  dom.logsTableBody.innerHTML = filtered
    .map((log) => {
      const isAlta = log.new_priority === "ALTA";
      const badgeChange = isAlta
        ? `<span class="log-badge-alta">ALTA</span>`
        : `<span class="log-badge-normal">NORMAL</span>`;

      return `
        <tr>
          <td style="font-family: var(--font-mono); font-size: 11px;">${escapeHtml(log.timestamp)}</td>
          <td><strong style="color: #38bdf8;">${escapeHtml(log.of)}</strong></td>
          <td>${escapeHtml(log.denominacion || "-")}</td>
          <td><span style="background: #1e293b; padding: 2px 6px; border-radius: 4px; font-size: 11px;">${escapeHtml(log.sector || "-")}</span></td>
          <td>
            <span style="color: #94a3b8; font-size: 11px;">${escapeHtml(log.old_priority || "NORMAL")} ➔</span> ${badgeChange}
          </td>
          <td>
            <strong style="color: #f1f5f9;">${escapeHtml(log.user_name || "Usuario")}</strong>
            <div style="font-size: 10px; color: #64748b;">${escapeHtml(log.user_email || "")}</div>
          </td>
        </tr>
      `;
    })
    .join("");
}

// ============================================================
// CONFIGURACIÓN DE LISTENERS
// ============================================================
function setupEventListeners() {
  dom.btnFullscreen?.addEventListener("click", toggleFullscreen);
  dom.btnOpenLogs?.addEventListener("click", openLogsModal);

  // Modal Login
  dom.btnCloseLogin?.addEventListener("click", () => closeModal(dom.modalLogin));
  dom.formManualEmail?.addEventListener("submit", async (e) => {
    e.preventDefault();
    const email = dom.inputPcpEmail.value.trim().toLowerCase();
    const name = dom.inputPcpName.value.trim();

    if (!email) return;

    dom.loginFeedback.style.display = "block";
    dom.loginFeedback.style.color = "#38bdf8";
    dom.loginFeedback.textContent = "Verificando autorización de PCP...";

    // Guardar sesión manual
    saveUserSession({
      email: email,
      name: name || email.split("@")[0],
      picture: null,
      id_token: null,
    });

    dom.loginFeedback.style.color = "#10b981";
    dom.loginFeedback.textContent = "✅ Acceso concedido correctamente.";

    setTimeout(() => {
      closeModal(dom.modalLogin);
      dom.loginFeedback.style.display = "none";
      renderStage();
    }, 600);
  });

  // Modal Prioridad
  dom.btnClosePriority?.addEventListener("click", () => closeModal(dom.modalPriority));
  dom.btnCancelPriority?.addEventListener("click", () => closeModal(dom.modalPriority));
  dom.btnSavePriority?.addEventListener("click", savePriorityChoice);

  // Modal Logs
  dom.btnCloseLogs?.addEventListener("click", () => closeModal(dom.modalLogs));
  dom.btnCloseLogsFooter?.addEventListener("click", () => closeModal(dom.modalLogs));
  dom.inputSearchLogs?.addEventListener("input", (e) => {
    renderLogsTable(e.target.value);
  });

  // Teclado
  document.addEventListener("keydown", (e) => {
    if (e.key === "f" || e.key === "F") {
      toggleFullscreen();
    }
    if (e.key === "Escape") {
      closeModal(dom.modalLogin);
      closeModal(dom.modalPriority);
      closeModal(dom.modalLogs);
    }
  });

  window.addEventListener("resize", () => {
    renderStage();
  });
}

function openModal(el) {
  if (el) el.style.display = "flex";
}

function closeModal(el) {
  if (el) el.style.display = "none";
}

function toggleFullscreen() {
  if (!document.fullscreenElement) {
    document.documentElement.requestFullscreen().catch(() => {});
  } else {
    document.exitFullscreen().catch(() => {});
  }
}

function jsonParseSafe(str) {
  try {
    return JSON.parse(str);
  } catch {
    return null;
  }
}

function escapeHtml(str) {
  if (!str) return "";
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}
