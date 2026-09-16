"use strict";
const PAYLOAD = JSON.parse(document.getElementById("payload").textContent);
const ROOT = "/home/pyodide/proyecto";
let pyodide = null;
let bridge = null;

/* ---------- utilidades: el texto siempre se inserta como texto, nunca como HTML ---------- */
function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs)) {
    if (key === "class") node.className = value;
    else if (key === "text") node.textContent = value;
    else node.setAttribute(key, value);
  }
  for (const child of children.flat()) {
    if (child == null) continue;
    node.append(child instanceof Node ? child : document.createTextNode(String(child)));
  }
  return node;
}
const clear = (node) => { while (node.firstChild) node.removeChild(node.firstChild); return node; };
const code = (text) => el("code", { text });
const call = (fn, ...args) => JSON.parse(bridge[fn](...args));
function setStatus(kind, text) {
  document.getElementById("status").className = `status ${kind}`;
  document.getElementById("status-text").textContent = text;
}

/* ---------- fecha de hoy (editable) ---------- */
const todayInput = document.getElementById("today");
todayInput.value = new Date(Date.now() - new Date().getTimezoneOffset() * 60000).toISOString().slice(0, 10);
const todayIso = () => todayInput.value;
function formatDate(iso) { const [y, m, d] = iso.split("-"); return `${d}/${m}/${y}`; }
/* Oráculo independiente de la regla «el día N» para comprobar lo que hace Python. */
function expectedDayOfMonth(day, iso) {
  const [y, m, d] = iso.split("-").map(Number);
  let year = y, month = m;
  if (day < d) { month += 1; if (month === 13) { month = 1; year += 1; } }
  const last = new Date(Date.UTC(year, month, 0)).getUTCDate();
  return `${year}-${String(month).padStart(2, "0")}-${String(Math.min(day, last)).padStart(2, "0")}`;
}

/* ---------- navegación ---------- */
const sections = [...document.querySelectorAll("section.step")];
const stepper = document.getElementById("stepper");
sections.forEach((s, i) => stepper.append(el("button", { type: "button", "data-go": String(i) }, el("span", { class: "n", text: String(i + 1) }), s.dataset.title)));
function go(index) {
  sections.forEach((s, i) => s.classList.toggle("active", i === index));
  [...stepper.children].forEach((b, i) => b.setAttribute("aria-current", i === index ? "step" : "false"));
  window.scrollTo({ top: 0, behavior: "smooth" });
  history.replaceState(null, "", `#paso-${index + 1}`);
}
document.addEventListener("click", (event) => { const t = event.target.closest("[data-go]"); if (t) go(Number(t.dataset.go)); });
go(Math.min(Math.max(Number((location.hash.match(/^#paso-(\d)$/) || [])[1] || 1) - 1, 0), sections.length - 1));
document.querySelectorAll(".commit").forEach((n) => { n.textContent = PAYLOAD.commit; });

/* ---------- representación de un turno ---------- */
const STATUS = {
  sin_accion: ["none", "Sin acción"],
  ejecutada: ["ok", "Acción ejecutada"],
  duplicada: ["info", "Ya registrada: no se reenvía"],
  fallida: ["bad", "Fallo: se reintentará"],
};
const FIXED = new Set(["Authorization", "Content-Type"]);
function renderDetail(container, result, explanation) {
  clear(container);
  const parsed = Object.entries(result.parsed);
  container.append(el("div", {}, el("div", { class: "label", text: "Datos extraídos" }),
    el("dl", { class: "kv" }, parsed.flatMap(([k, v]) => [el("dt", { text: k }), el("dd", { text: v })]))));
  const [kind, text] = STATUS[result.status];
  container.append(el("div", {}, el("div", { class: "label", text: "Decisión" }), el("span", { class: `badge ${kind}`, text })));
  if (result.reason) container.append(el("p", { class: "explain", text: `Motivo: ${result.reason}.` }));
  if (explanation) container.append(el("p", { class: "explain", text: explanation }));
  if (result.request) {
    const r = result.request;
    container.append(el("div", {}, el("div", { class: "label", text: "Request construida (no se envía)" }),
      el("div", { class: "request" },
        el("div", { class: "line" }, el("span", { class: "method", text: r.method }), r.url,
          result.response_status != null ? el("span", { class: "tag nowrap", text: `${result.response_status === 200 ? "200 OK" : result.response_status} simulado` }) : null),
        el("table", {}, el("tbody", {}, Object.entries(r.headers).map(([n, v]) =>
          el("tr", {}, el("td", {}, n, FIXED.has(n) ? null : el("span", { class: "tag", text: "del parser" })), el("td", { text: v }))))),
        el("pre", { text: r.body }))));
  }
}
const bubble = (role, label, text) => el("div", { class: `bubble ${role}` }, el("small", { text: label }), text);

/* ---------- conversaciones guiadas ---------- */
const GUIDED = {
  cobros: {
    expected: ["sin_accion", "sin_accion", "ejecutada", "duplicada"],
    // Cada explicación se calcula solo en su turno: antes del tercero no hay fecha que formatear.
    explain: (i, r) => [
      () => "Todavía no hay fecha ni importe: el agente pregunta por los dos.",
      () => "Ya sabe el importe, pero falta la fecha.",
      () => `«el 4»: hoy es ${formatDate(todayIso())}, así que la regla elige el ${formatDate(JSON.parse(r.parsed.commitment_date))}. Con fecha e importe, construye la request y registra el compromiso.`,
      () => "El usuario corrige el importe, pero el compromiso ya se registró en esta conversación: no se vuelve a enviar.",
    ][i](),
    checks: (t) => [
      ["No actúa sin fecha e importe", t[0].status === "sin_accion" && t[1].status === "sin_accion"],
      ["Resuelve «el 4» con la regla de fechas", JSON.parse(t[2].parsed.commitment_date) === expectedDayOfMonth(4, todayIso())],
      ["Registra con URL, Bearer token y los datos como cabeceras", t[2].status === "ejecutada" && t[2].request?.url === "https://api.ringr.debt/v1/commitment"
        && t[2].request.headers.Authorization === "Bearer ringr_test_token_9f3a2c1d" && t[2].request.headers.committed_amount === "200.0"
        && t[2].request.headers.commitment_date === JSON.parse(t[2].parsed.commitment_date)],
      ["No registra dos veces en la misma conversación", t[3].status === "duplicada" && !t[3].request],
    ],
  },
  atencion: {
    expected: ["sin_accion", "ejecutada", "duplicada"],
    explain: (i) => [
      "Es una duda, no una solicitud: no hay nada que registrar.",
      "Pide algo («quiero…»): el agente registra la solicitud para un compañero.",
      "Da las gracias. La solicitud ya se registró en esta conversación y no se reenvía.",
    ][i],
    checks: (t) => [
      ["Una duda no genera ninguna solicitud", t[0].status === "sin_accion"],
      ["Registra la solicitud con URL, Bearer token y la solicitud como cabecera", t[1].status === "ejecutada"
        && t[1].request?.url === "https://api.ringr.assistance/v1/request" && t[1].request.headers.Authorization === "Bearer ringr_test_token_9f3a2c1d"
        && t[1].request.headers.request === "Quiero cambiar mi dirección postal"],
      ["No la registra dos veces", t[2].status === "duplicada" && !t[2].request],
    ],
  },
};
const guided = {};
function startGuided(kind) {
  const { script } = call("start", `guion-${kind}`, kind, todayIso());
  guided[kind] = { script, results: [] };
  const box = document.querySelector(`[data-scenario="${kind}"]`);
  clear(box.querySelector(".chat")).append(el("p", { class: "empty", text: "Pulsa «Siguiente turno»." }));
  clear(box.querySelector(".detail")).append(el("p", { class: "empty", text: "Aquí verás los datos, la decisión y la request." }));
  const conclusion = document.querySelector(`[data-conclusion="${kind}"]`); conclusion.hidden = true; clear(conclusion);
  updateGuidedButton(kind);
}
function updateGuidedButton(kind) {
  const g = guided[kind]; const button = document.querySelector(`[data-next="${kind}"]`);
  const done = g.results.length >= g.script.length;
  button.disabled = done;
  button.textContent = done ? "Conversación terminada" : `Siguiente turno (${g.results.length + 1} de ${g.script.length})`;
  document.querySelector(`[data-reset="${kind}"]`).disabled = false;
}
function nextGuided(kind) {
  const g = guided[kind]; const i = g.results.length; const message = g.script[i];
  const result = call("turn", `guion-${kind}`, message); g.results.push(result);
  const box = document.querySelector(`[data-scenario="${kind}"]`); const chat = box.querySelector(".chat");
  if (i === 0) clear(chat);
  chat.append(bubble("user", `Usuario · turno ${i + 1}`, message), bubble("agent", "Agente", result.answer));
  const spec = GUIDED[kind];
  renderDetail(box.querySelector(".detail"), result, result.status === spec.expected[i] ? spec.explain(i, result) : "Resultado inesperado para este turno.");
  updateGuidedButton(kind);
  if (g.results.length === g.script.length) {
    const checks = spec.checks(g.results); const ok = checks.every(([, passed]) => passed);
    const c = clear(document.querySelector(`[data-conclusion="${kind}"]`));
    c.append(el("h3", { text: ok ? "✅ Comprobado en esta conversación" : "❌ Algo no ha salido como se esperaba" }),
      el("ul", { class: "checks" }, checks.map(([t, p]) => el("li", {}, el("span", { class: "icon", text: p ? "✅" : "❌" }), t))));
    c.hidden = false;
  }
}
document.querySelectorAll("[data-next]").forEach((b) => b.addEventListener("click", () => nextGuided(b.dataset.next)));
document.querySelectorAll("[data-reset]").forEach((b) => b.addEventListener("click", () => startGuided(b.dataset.reset)));

/* ---------- chat libre ---------- */
const IDEAS = {
  cobros: ["el 4 pago 200 euros", "Pagaré 150,50 €", "el 31", "mejor 250 euros", "el 2026-01-10", "pagaré -20 euros"],
  atencion: ["¿Tenéis horario de tarde?", "Quiero cambiar mi dirección", "No quiero darme de baja", "Necesito una factura", "Gracias"],
};
let chatKind = "cobros";
const chatLog = document.getElementById("chat-log");
const chatInput = document.getElementById("chat-input");
function resetChat() {
  call("start", "chat", chatKind, todayIso());
  clear(chatLog).append(el("p", { class: "empty", text: "Conversación nueva. Escribe un mensaje o usa una idea." }));
  clear(document.getElementById("chat-detail")).append(el("p", { class: "empty", text: "El último turno aparecerá aquí." }));
}
function selectChat(kind) {
  chatKind = kind;
  document.querySelectorAll(".tabs [data-kind]").forEach((b) => b.setAttribute("aria-selected", String(b.dataset.kind === kind)));
  const ideas = clear(document.getElementById("chat-ideas"));
  IDEAS[kind].forEach((text) => {
    const b = el("button", { type: "button", text });
    b.addEventListener("click", () => { chatInput.value = text; chatInput.focus(); });
    ideas.append(b);
  });
  if (bridge) resetChat();
}
function sendChat(event) {
  event.preventDefault();
  const message = chatInput.value.trim();
  if (!message || !bridge) return;
  const result = call("turn", "chat", message);
  if (chatLog.querySelector(".empty")) clear(chatLog);
  const [, statusText] = STATUS[result.status];
  chatLog.append(bubble("user", "Tú", message), bubble("agent", `Agente · ${statusText}`, result.answer));
  chatLog.scrollTop = chatLog.scrollHeight;
  renderDetail(document.getElementById("chat-detail"), result, null);
  chatInput.value = "";
}
document.querySelectorAll(".tabs [data-kind]").forEach((b) => b.addEventListener("click", () => selectChat(b.dataset.kind)));
document.getElementById("chat-form").addEventListener("submit", sendChat);
document.getElementById("chat-reset").addEventListener("click", resetChat);
selectChat("cobros");

todayInput.addEventListener("change", () => { if (!bridge || !todayIso()) return; startGuided("cobros"); startGuided("atencion"); resetChat(); });

/* ---------- tests ---------- */
const TEST_GROUPS = {
  "tests/test_dates.py": "Regla de fechas",
  "tests/test_debt.py": "Agente de cobros: lectura de datos, validación y registro",
  "tests/test_assistance.py": "Agente de atención: solicitudes, rechazos y reintentos",
  "tests/test_agent.py": "Motor del turno: orden, duplicados y reintentos",
  "tests/test_http.py": "Request HTTP: cabeceras, cuerpo y cliente simulado",
  "tests/test_demo.py": "Demo por consola",
};
/* El nombre de cada test ya describe el comportamiento: «test_un_importe_negativo_no_se_registra». */
function testSentence(name) {
  const text = name.replace(/^test_/, "").replaceAll("_", " ");
  return text.charAt(0).toUpperCase() + text.slice(1);
}
function renderTests(box, result) {
  const groups = new Map();
  for (const test of result.tests) {
    if (!groups.has(test.file)) groups.set(test.file, []);
    groups.get(test.file).push(test);
  }
  const ok = result.exit_code === 0 && result.failed === 0 && result.passed > 0;
  box.append(el("div", { class: "summary-big" },
    el("span", { class: `badge ${ok ? "ok" : "bad"}`, text: ok ? "✅ Todo en verde" : "❌ Hay fallos" }),
    el("span", {}, el("span", { class: "n", text: String(result.passed) }), " comprobaciones superadas"),
    el("span", {}, el("span", { class: "n", text: String(result.tests.length) }), " tests"),
    el("span", { class: "subtitle", text: `${result.seconds.toLocaleString("es-ES")} s` })));
  box.append(el("p", { class: "explain", style: "margin-top:10px", text:
    "Cada línea es un test que se acaba de ejecutar aquí, con la descripción que lleva en el código. Un test que se ejecuta con varios juegos de datos lo indica entre paréntesis." }));
  for (const [file, tests] of groups) {
    const passed = tests.reduce((n, t) => n + t.passed, 0);
    const cases = tests.reduce((n, t) => n + t.cases, 0);
    box.append(el("div", { class: "card", style: "margin-top:14px" },
      el("h3", {}, TEST_GROUPS[file] || file, el("span", { class: "tag nowrap", text: `${passed}/${cases}` })),
      el("div", { class: "label", text: file }),
      el("ul", { class: "checks" }, tests.map((t) => el("li", {},
        el("span", { class: "icon", text: t.passed === t.cases ? "✅" : "❌" }),
        el("span", {}, t.doc || testSentence(t.test), t.cases > 1 ? el("span", { class: "subtitle", text: ` (${t.cases} casos)` }) : null))))));
  }
  box.append(el("details", {}, el("summary", { text: "Ver la salida de pytest" }), el("pre", { text: result.output })));
}
document.getElementById("run-tests").addEventListener("click", async () => {
  const button = document.getElementById("run-tests"); const progress = document.getElementById("tests-progress");
  const box = clear(document.getElementById("tests-result"));
  button.disabled = true;
  clear(progress).append(el("span", { class: "spinner" }), " Cargando pytest y ejecutando la suite…");
  try {
    await pyodide.loadPackage("pytest", { messageCallback: () => {} });
    await new Promise((resolve) => setTimeout(resolve, 30));
    renderTests(box, call("run_tests"));
    clear(progress);
    button.textContent = "Tests ejecutados";
  } catch (error) {
    clear(progress); box.append(el("div", { class: "error-box", text: `No se pudieron ejecutar los tests: ${error.message}` })); button.disabled = false;
  }
});

/* ---------- arranque ---------- */
(async function boot() {
  const started = performance.now();
  try {
    if (typeof loadPyodide !== "function") throw new Error("no se pudo descargar Pyodide (¿sin conexión?)");
    pyodide = await loadPyodide();
    for (const [rel, content] of Object.entries(PAYLOAD.files)) {
      const full = `${ROOT}/${rel}`;
      pyodide.FS.mkdirTree(full.slice(0, full.lastIndexOf("/")));
      pyodide.FS.writeFile(full, content);
    }
    pyodide.FS.writeFile("/home/pyodide/bridge.py", PAYLOAD.bridge);
    await pyodide.runPythonAsync(`import sys\nsys.path[:0] = ["${ROOT}/src", "/home/pyodide"]\nimport bridge`);
    bridge = pyodide.globals.get("bridge");
    const seconds = ((performance.now() - started) / 1000).toLocaleString("es-ES", { maximumFractionDigits: 1 });
    setStatus("ready", `Listo: Python en tu navegador · ${seconds} s`);
    startGuided("cobros"); startGuided("atencion"); resetChat();
    ["chat-send", "chat-reset", "run-tests"].forEach((id) => { document.getElementById(id).disabled = false; });
  } catch (error) {
    setStatus("error", "No se pudo cargar Python en el navegador");
    document.querySelector(".wrap").insertBefore(el("div", { class: "error-box", style: "margin-bottom:16px" },
      `No se pudo preparar la demo: ${error.message}. Alternativa: `, code("git clone https://github.com/pepedrm17/ringr-agents-lite.git && cd ringr-agents-lite && uv sync && uv run python -m ringr_agents.demo")), stepper);
  }
})();
