let catalog, configs, state, selectedId, selectedEdge = null, connecting = null;
let positions = new Map();
const STAGE = { width: 1500, height: 670, nodeWidth: 168, nodeHeight: 108 };
const $ = (selector) => document.querySelector(selector);
const clone = (value) => JSON.parse(JSON.stringify(value));

async function request(url, method = "GET", body) {
  const response = await fetch(url, { method, headers: body ? { "Content-Type": "application/json" } : undefined, body: body ? JSON.stringify(body) : undefined });
  if (!response.ok) throw new Error((await response.text()) || `HTTP ${response.status}`);
  return response;
}
function nodes() { return state.pipeline.nodes; }
function nodeMeta(name) { return catalog.nodes.find((node) => node.name === name); }
function selected() { return nodes().find((node) => node.id === selectedId); }
function edgeKey(source, target) { return `${source}→${target}`; }
function blankConfig(meta) { return Object.fromEntries(Object.entries(meta.config_schema.properties || {}).filter(([, schema]) => Object.hasOwn(schema, "default")).map(([name, schema]) => [name, clone(schema.default)])); }

function autoLayout() {
  ensureOutputNode();
  const levels = new Map();
  const levelFor = (node, trail = new Set()) => {
    if (levels.has(node.id)) return levels.get(node.id);
    if (trail.has(node.id)) return 0;
    trail.add(node.id);
    const parents = node.depends_on.filter((id) => id !== "__START__").map((id) => nodes().find((item) => item.id === id)).filter(Boolean);
    const level = parents.length ? Math.max(...parents.map((parent) => levelFor(parent, trail))) + 1 : 0;
    levels.set(node.id, level); return level;
  };
  nodes().forEach((node) => levelFor(node));
  const groups = new Map();
  nodes().forEach((node) => { const level = levels.get(node.id); groups.set(level, [...(groups.get(level) || []), node]); });
  const maxLevel = Math.max(0, ...levels.values());
  const maxRows = Math.max(1, ...[...groups.values()].map((group) => group.length));
  STAGE.width = Math.max(1200, 95 + (maxLevel + 2) * 190 + STAGE.nodeWidth);
  STAGE.height = Math.max(670, 35 + maxRows * 145 + STAGE.nodeHeight + 70);
  positions = new Map();
  [...groups.entries()].forEach(([level, group]) => group.forEach((node, row) => positions.set(node.id, { x: 95 + level * 190, y: 35 + row * 145 })));
  render();
}

function compatibility(source, target) {
  if (source === "__START__") return target.execution_scope === "fanout" ? null : "__START__는 fanout 노드에만 연결할 수 있습니다.";
  const upstream = nodes().find((node) => node.id === source);
  if (!upstream) return `출력 노드 ${source}를 찾을 수 없습니다.`;
  if (upstream.output.type !== target.input.type) return `${upstream.output.type} → ${target.input.type}: DTO type이 맞지 않습니다.`;
  if (upstream.output.is_list !== target.input.is_list) return "입출력 list cardinality가 맞지 않습니다.";
  return null;
}

function updateConnection(source, targetId) {
  const target = nodes().find((node) => node.id === targetId);
  if (!target || source === targetId) return;
  const issue = compatibility(source, target);
  if (issue) return setStatus(issue, false);
  if (source === "__START__") target.depends_on = ["__START__"];
  else if (target.input.is_list) target.depends_on = [...target.depends_on.filter((id) => id !== "__START__" && id !== source), source];
  else target.depends_on = [source];
  selectedEdge = edgeKey(source, targetId); connecting = null; render();
}

function removeConnection(source, target) {
  const node = nodes().find((item) => item.id === target);
  if (node) node.depends_on = node.depends_on.filter((id) => id !== source);
  selectedEdge = null; render();
}

function removeSelectedEdge() { if (selectedEdge) { const [source, target] = selectedEdge.split("→"); removeConnection(source, target); } }
function addNode() {
  const meta = nodeMeta($("#palette").value); const base = meta.name.replaceAll(/[^a-z0-9]+/g, "_").replace(/^_+|_+$/g, ""); let id = base;
  for (let index = 2; nodes().some((node) => node.id === id); index += 1) id = `${base}_${index}`;
  nodes().push({ id, node: meta.name, execution_scope: meta.execution_scope, input: clone(meta.input), output: clone(meta.output), depends_on: [], node_config: blankConfig(meta) });
  const rightmost = Math.max(95, ...[...positions.values()].map((point) => point.x));
  const x = rightmost + 210;
  STAGE.width = Math.max(STAGE.width, x + STAGE.nodeWidth + 120);
  positions.set(id, { x, y: 80 }); selectedId = id; render();
}
function removeNode(id) {
  state.pipeline.nodes = nodes().filter((node) => node.id !== id); nodes().forEach((node) => { node.depends_on = node.depends_on.filter((dep) => dep !== id); }); positions.delete(id);
  if (state.pipeline.output_node === id) state.pipeline.output_node = [...nodes()].reverse().find(isOutputCandidate)?.id || ""; selectedId = nodes()[0]?.id; render();
}
function isOutputCandidate(node) { return node.output.type === "document_dto@v1" && !node.output.is_list; }
function ensureOutputNode() { if (!nodes().some((node) => node.id === state.pipeline.output_node && isOutputCandidate(node))) state.pipeline.output_node = [...nodes()].reverse().find(isOutputCandidate)?.id || ""; }
function setStatus(text, valid) { const status = $("#status"); status.className = valid ? "valid" : "invalid"; status.textContent = text; }

function renderOverview() {
  $("#pricing-file").value = state.pricing_file ?? "";
  const edgeCount = nodes().reduce((sum, node) => sum + node.depends_on.length, 0);
  const issues = nodes().reduce((sum, node) => sum + node.depends_on.filter((source) => compatibility(source, node)).length, 0);
  $("#overview").replaceChildren(...[`노드 ${nodes().length}개`, `연결 ${edgeCount}개`, `출력 노드: ${state.pipeline.output_node || "미선택"}`, `호환성 오류: ${issues}개`].map((text) => Object.assign(document.createElement("div"), { className: "metric", textContent: text })));
  $("#delete-edge").disabled = !selectedEdge;
}

function makeSvg(tag, attrs = {}) { const element = document.createElementNS("http://www.w3.org/2000/svg", tag); Object.entries(attrs).forEach(([name, value]) => element.setAttribute(name, value)); return element; }
function portCenter(id, output) { if (id === "__START__") return { x: 145, y: 335 }; const point = positions.get(id); return { x: point.x + (output ? STAGE.nodeWidth : 0), y: point.y + 50 }; }
function pathFor(from, to) { const pull = Math.max(55, Math.abs(to.x - from.x) * .45); return `M ${from.x} ${from.y} C ${from.x + pull} ${from.y}, ${to.x - pull} ${to.y}, ${to.x} ${to.y}`; }

function renderGraph() {
  const graph = $("#graph"); graph.style.width = `${STAGE.width}px`; graph.style.height = `${STAGE.height}px`; graph.replaceChildren();
  const svg = makeSvg("svg", { class: "edge-svg", width: STAGE.width, height: STAGE.height });
  const defs = makeSvg("defs"); const marker = makeSvg("marker", { id: "arrow", viewBox: "0 0 10 10", refX: "8", refY: "5", markerWidth: "6", markerHeight: "6", orient: "auto" }); marker.append(makeSvg("path", { d: "M 0 0 L 10 5 L 0 10 z", fill: "#6888a3" })); defs.append(marker); svg.append(defs);
  nodes().forEach((target) => target.depends_on.forEach((source) => {
    if (!positions.has(target.id) || (source !== "__START__" && !positions.has(source))) return;
    const key = edgeKey(source, target.id); const edge = makeSvg("path", { class: `edge ${key === selectedEdge ? "selected" : ""}`, d: pathFor(portCenter(source, true), portCenter(target.id, false)), "marker-end": "url(#arrow)" });
    edge.onclick = (event) => { event.stopPropagation(); selectedEdge = key; selectedId = undefined; render(); }; svg.append(edge);
  }));
  if (connecting) svg.append(makeSvg("path", { class: "edge-preview", d: pathFor(portCenter(connecting.source, true), connecting.point) }));
  graph.append(svg);
  const start = document.createElement("div"); start.className = "start-node"; start.style.left = "20px"; start.style.top = "305px"; start.textContent = "START"; start.append(makePort("__START__", true)); graph.append(start);
  nodes().forEach((node) => graph.append(makeNode(node)));
  graph.onclick = () => { selectedId = undefined; selectedEdge = null; render(); };
}

function makePort(id, output) {
  const port = document.createElement("span"); port.className = `port ${output ? "output" : "input"}`;
  if (output) port.onpointerdown = (event) => { event.stopPropagation(); event.preventDefault(); connecting = { source: id, point: graphPoint(event) }; renderGraph(); highlightTargets(id); };
  else { port.onpointerup = (event) => { if (!connecting) return; event.stopPropagation(); updateConnection(connecting.source, id); }; }
  return port;
}
function makeNode(node) {
  const point = positions.get(node.id) || { x: 400, y: 120 }; positions.set(node.id, point);
  const card = document.createElement("article"); card.className = `graph-node ${node.id === selectedId ? "selected" : ""}`; card.style.left = `${point.x}px`; card.style.top = `${point.y}px`;
  card.innerHTML = `<strong>${escapeHtml(node.id)}</strong><small class="node-type">${escapeHtml(node.node)} · ${node.execution_scope}</small><small>${escapeHtml(node.input.type)}${node.input.is_list ? "[]" : ""} → ${escapeHtml(node.output.type)}${node.output.is_list ? "[]" : ""}</small>`;
  card.append(makePort(node.id, false), makePort(node.id, true)); card.onpointerdown = (event) => beginDrag(event, node.id); card.onclick = (event) => { event.stopPropagation(); if (!connecting) { selectedId = node.id; selectedEdge = null; render(); } }; return card;
}
function graphPoint(event) { const rect = $("#graph").getBoundingClientRect(); return { x: event.clientX - rect.left, y: event.clientY - rect.top }; }
function beginDrag(event, id) {
  if (event.target.classList.contains("port")) return; event.preventDefault(); const origin = graphPoint(event); const point = positions.get(id); const offset = { x: origin.x - point.x, y: origin.y - point.y };
  const move = (moveEvent) => { const mouse = graphPoint(moveEvent); const next = { x: Math.max(8, mouse.x - offset.x), y: Math.max(8, mouse.y - offset.y) }; STAGE.width = Math.max(STAGE.width, next.x + STAGE.nodeWidth + 120); STAGE.height = Math.max(STAGE.height, next.y + STAGE.nodeHeight + 90); positions.set(id, next); renderGraph(); };
  const stop = () => { window.removeEventListener("pointermove", move); window.removeEventListener("pointerup", stop); }; window.addEventListener("pointermove", move); window.addEventListener("pointerup", stop);
}
function highlightTargets(source) {
  document.querySelectorAll(".port.input").forEach((port) => { const target = port.closest(".graph-node")?.querySelector("strong")?.textContent; if (!target) return; const issue = compatibility(source, nodes().find((node) => node.id === target)); port.classList.add(issue ? "invalid" : "connectable"); });
}
window.addEventListener("pointermove", (event) => { if (!connecting) return; connecting.point = graphPoint(event); renderGraph(); highlightTargets(connecting.source); });
window.addEventListener("pointerup", () => { if (connecting) { connecting = null; renderGraph(); } });

function renderNodeForm() {
  const container = $("#node-form"); const node = selected(); if (!node) { container.textContent = selectedEdge ? "연결을 선택했습니다. 상단의 ‘선택 연결 삭제’를 누르세요." : "노드를 선택하면 설정을 편집할 수 있습니다."; return; }
  container.replaceChildren(); addTextField(container, "ID", node.id, (value) => renameNode(node, value.trim()), "node ID는 고유해야 합니다.");
  const summary = document.createElement("p"); summary.className = "selected-summary"; summary.textContent = `${node.node} · ${node.execution_scope} · ${node.input.type}${node.input.is_list ? "[]" : ""} → ${node.output.type}${node.output.is_list ? "[]" : ""}`; container.append(summary);
  const outputLabel = document.createElement("label"); outputLabel.className = "field"; outputLabel.innerHTML = "<span>최종 출력 노드 (필수·하나)</span><small>CLI가 최종 결과로 반환할 document_dto@v1 node입니다. 해제할 수 없으며, 후보 중 하나를 선택합니다.</small>"; const output = document.createElement("input"); output.type = "radio"; output.name = "output-node"; output.disabled = !isOutputCandidate(node); output.checked = isOutputCandidate(node) && state.pipeline.output_node === node.id; output.onchange = () => { state.pipeline.output_node = node.id; renderOverview(); }; outputLabel.append(output); if (!isOutputCandidate(node)) outputLabel.querySelector("small").textContent += " 이 node는 document 결과를 내지 않아 선택할 수 없습니다."; container.append(outputLabel);
  const connections = document.createElement("div"); connections.innerHTML = "<h3>입력 연결</h3>"; const list = document.createElement("ul"); list.className = "connection-list";
  if (!node.depends_on.length) list.innerHTML = "<li>연결 없음 — canvas의 입력 포트로 연결하세요.</li>";
  node.depends_on.forEach((source) => { const item = document.createElement("li"); item.append(document.createTextNode(source)); const remove = document.createElement("button"); remove.textContent = "해제"; remove.onclick = () => removeConnection(source, node.id); item.append(remove); list.append(item); }); connections.append(list); container.append(connections);
  const heading = document.createElement("h3"); heading.textContent = "Strict node_config"; container.append(heading); const meta = nodeMeta(node.node); Object.entries(meta.config_schema.properties || {}).forEach(([name, schema]) => addConfigField(container, node, name, schema, meta.secret_fields.includes(name)));
  const remove = document.createElement("button"); remove.className = "danger"; remove.textContent = "노드 삭제"; remove.onclick = () => removeNode(node.id); container.append(remove);
}
function renameNode(node, value) { const old = node.id; if (!value || nodes().some((item) => item !== node && item.id === value)) return setStatus("node ID는 비어 있거나 중복될 수 없습니다.", false); node.id = value; selectedId = value; nodes().forEach((item) => { item.depends_on = item.depends_on.map((dep) => dep === old ? value : dep); }); if (state.pipeline.output_node === old) state.pipeline.output_node = value; const point = positions.get(old); positions.delete(old); positions.set(value, point); render(); }
function addTextField(container, title, value, change, help) { const label = $("#field-template").content.firstElementChild.cloneNode(true); label.querySelector("span").textContent = title; label.querySelector("small").textContent = help || ""; const input = document.createElement("input"); input.value = value; input.onchange = () => change(input.value); label.querySelector("div").append(input); container.append(label); }
function addConfigField(container, node, name, schema, secret) {
  const required = isRequired(node.node, name); const label = $("#field-template").content.firstElementChild.cloneNode(true); label.querySelector("span").textContent = `${name} ${required ? "(필수)" : "(선택)"}`; label.querySelector("small").textContent = describeSchema(schema, secret); const holder = label.querySelector("div"); const current = node.node_config[name]; const set = (value) => { if (value === undefined || value === "") delete node.node_config[name]; else node.node_config[name] = value; };
  if (secret) { const env = typeof current === "string" && /^\$\{[^}]+\}$/.test(current); const mode = document.createElement("select"); mode.innerHTML = '<option value="env">환경변수 참조</option><option value="direct">직접 입력</option>'; mode.value = env || current === undefined ? "env" : "direct"; const input = document.createElement("input"); input.type = mode.value === "direct" ? "password" : "text"; input.placeholder = mode.value === "direct" ? "실제 값 (저장하지 않음)" : "${ENVIRONMENT_VARIABLE}"; input.value = current || ""; mode.onchange = () => { input.type = mode.value === "direct" ? "password" : "text"; }; input.onchange = () => set(input.value); holder.append(mode, input); }
  else if (schema.enum) { const input = document.createElement("select"); input.append(new Option("(unset)", ""), ...schema.enum.map((value) => new Option(value, value))); input.value = current ?? ""; input.onchange = () => set(input.value); holder.append(input); }
  else if (isBoolean(schema) && typeof current === "string" && /^\$\{[^}]+\}$/.test(current)) { const input = document.createElement("input"); input.type = "text"; input.value = current; input.onchange = () => set(input.value); holder.append(input); label.querySelector("small").textContent += " 환경변수 참조를 유지합니다. 편집기 검증은 기본값을, 실행은 환경변수 값을 사용합니다."; }
  else if (isBoolean(schema)) { const input = document.createElement("input"); input.type = "checkbox"; input.checked = current ?? schema.default ?? false; input.onchange = () => set(input.checked); holder.append(input); }
  else if (name === "user_prompt") { const input = document.createElement("textarea"); input.value = current ?? ""; input.placeholder = "추가 요청 (8,192 code points / UTF-8 32 KiB)"; const count = document.createElement("small"); const update = () => { const chars = [...input.value].length; const bytes = new TextEncoder().encode(input.value).length; count.textContent = `${chars} code points · ${bytes} UTF-8 bytes`; input.setCustomValidity(chars > 8192 || bytes > 32768 ? "추가 요청의 기본 상한을 초과했습니다." : ""); }; input.oninput = update; input.onchange = () => { update(); set(input.value); }; update(); holder.append(input, count); }
  else if (isComplex(schema)) { const input = document.createElement("textarea"); input.value = current === undefined ? "" : JSON.stringify(current, null, 2); input.placeholder = "JSON"; input.onchange = () => { try { set(input.value ? JSON.parse(input.value) : undefined); input.setCustomValidity(""); } catch { input.setCustomValidity("유효한 JSON이어야 합니다."); input.reportValidity(); } }; holder.append(input); }
  else { const input = document.createElement("input"); input.type = isNumber(schema) ? "number" : "text"; input.value = current ?? ""; input.onchange = () => set(input.type === "number" && input.value !== "" ? Number(input.value) : input.value); holder.append(input); } container.append(label);
}
function isRequired(nodeName, field) { return nodeMeta(nodeName).config_schema.properties[field]?.["x-editor"]?.required ?? false; } function isBoolean(schema) { return schema.type === "boolean" || schema.anyOf?.some((item) => item.type === "boolean"); } function isNumber(schema) { return ["number", "integer"].includes(schema.type) || schema.anyOf?.some((item) => ["number", "integer"].includes(item.type)); } function isComplex(schema) { return ["array", "object"].includes(schema.type) || schema.anyOf?.some((item) => ["array", "object"].includes(item.type)); } function describeSchema(schema, secret) { const description = schema["x-editor"]?.description || ""; const type = schema.enum ? `허용값: ${schema.enum.join(", ")}` : schema.type || schema.anyOf?.map((item) => item.type).filter(Boolean).join(" | ") || ""; const secretHelp = secret ? " 환경변수 참조 또는 직접 입력(직접 입력은 browser/request 메모리에만 유지)." : ""; return `${description}${type ? ` · ${type}` : ""}${secretHelp}`; } function escapeHtml(value) { return String(value).replace(/[&<>"]/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[char]); }
function render() { renderOverview(); renderGraph(); renderNodeForm(); }
async function validate() { try { const result = await (await request("/api/validate", "POST", { config: state })).json(); setStatus(result.valid ? `검증 통과 · 실행 순서: ${result.topological_order.join(" → ")}` : `검증 실패\n${result.message}`, result.valid); } catch (error) { setStatus(error.message, false); } }
async function exportYaml() { try { const response = await request("/api/export", "POST", { config: state }); const url = URL.createObjectURL(await response.blob()); const link = Object.assign(document.createElement("a"), { href: url, download: "pipeline.yaml" }); link.click(); URL.revokeObjectURL(url); } catch (error) { setStatus(error.message, false); } }
async function importFile(file) { const response = await request("/api/import", "POST", { yaml: await file.text() }); const result = await response.json(); if (!result.config) throw new Error(result.message); state = result.config; selectedId = undefined; selectedEdge = null; autoLayout(); await validate(); }
async function boot() { try { const data = await (await request("/api/catalog")).json(); catalog = data.catalog; configs = data.configs; Object.keys(configs).forEach((name) => $("#config-select").append(new Option(name, name))); catalog.nodes.forEach((node) => $("#palette").append(new Option(`${node.name}${node.optional ? " (optional)" : ""}`, node.name))); state = clone(configs[$("#config-select").value]); $("#pricing-file").oninput = (event) => { const value = event.target.value; if (value.trim()) state.pricing_file = value; else delete state.pricing_file; }; autoLayout(); setStatus("준비됨. 출력 포트에서 입력 포트로 드래그해 연결하세요.", true); $("#load-config").onclick = () => { state = clone(configs[$("#config-select").value]); selectedId = undefined; selectedEdge = null; autoLayout(); }; $("#add-node").onclick = addNode; $("#auto-layout").onclick = autoLayout; $("#delete-edge").onclick = removeSelectedEdge; $("#validate").onclick = validate; $("#export").onclick = exportYaml; $("#yaml-file").onchange = (event) => event.target.files[0] && importFile(event.target.files[0]); } catch (error) { setStatus(`초기화 실패: ${error.message}`, false); } }
boot();
