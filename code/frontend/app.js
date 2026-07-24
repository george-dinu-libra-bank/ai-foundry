/* Libra Assist — Admin Console
 * Talks ONLY to the local RAG Teaching API. No secrets ever live here.
 * Plain browser JS (no build step, no framework) — open index.html and go.
 */
(() => {
  "use strict";

  // ── tiny DOM helpers ─────────────────────────────────────────────────
  const $ = (sel, root = document) => root.querySelector(sel);
  const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];
  const esc = (s) =>
    String(s ?? "").replace(/[&<>"']/g, (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

  // ── persisted settings (base URL + last-used knobs) ──────────────────
  const LS = "libra-admin.settings";
  const store = Object.assign(
    { baseUrl: "http://localhost:7799", strategy: "dynamic", topK: "", useRag: true, temp: "" },
    JSON.parse(localStorage.getItem(LS) || "{}")
  );
  const save = () => localStorage.setItem(LS, JSON.stringify(store));

  const EXAMPLE =
    "Libra Bank blocks a card after three failed PIN attempts. " +
    "A blocked card can be unblocked in the branch after identity verification. " +
    "Mortgage early repayment is free of charge in the variable-rate period.";

  // ── API layer: always throw {status, detail} so the UI can be honest ─
  const baseUrl = () => $("#base-url").value.trim().replace(/\/+$/, "");
  const TIMEOUT_MS = 90000; // don't spin forever if the backend hangs (e.g. Azure auth)

  async function api(path, { method = "GET", body } = {}) {
    const ctrl = new AbortController();
    const timer = setTimeout(() => ctrl.abort(), TIMEOUT_MS);
    let res;
    try {
      res = await fetch(baseUrl() + path, {
        method,
        headers: body ? { "Content-Type": "application/json" } : undefined,
        body: body ? JSON.stringify(body) : undefined,
        signal: ctrl.signal,
      });
    } catch (e) {
      if (e.name === "AbortError") {
        throw { status: 0, detail:
          `Request to ${path} timed out after ${TIMEOUT_MS / 1000}s — the backend didn't respond. ` +
          `If this is /ingest, /search or /ask, the API is likely hanging on its Azure call ` +
          `(inside Docker use AZURE_AI_AUTH=key, not identity).` };
      }
      // Network-level failure: server down, wrong port, CORS, DNS…
      throw { status: 0, detail: `Cannot reach the API at ${baseUrl()} — is the backend running? (${e.message})` };
    } finally {
      clearTimeout(timer);
    }
    const text = await res.text();
    let data = null;
    try { data = text ? JSON.parse(text) : null; } catch { data = text; }
    if (!res.ok) {
      // FastAPI puts the message in `detail`; it may be a string or a list.
      let detail = data && data.detail !== undefined ? data.detail : (data || res.statusText);
      if (Array.isArray(detail)) detail = detail.map((d) => d.msg || JSON.stringify(d)).join("\n");
      else if (typeof detail === "object") detail = JSON.stringify(detail, null, 2);
      throw { status: res.status, detail: String(detail) };
    }
    return data;
  }

  // ── error / state rendering ──────────────────────────────────────────
  function showError(box, err) {
    box.hidden = false;
    const label = err.status === 0 ? "NETWORK" : `HTTP ${err.status}`;
    box.innerHTML =
      `<span class="err-status">${esc(label)}</span>` +
      `<p class="err-detail">${esc(err.detail)}</p>`;
  }
  const clearError = (box) => { box.hidden = true; box.innerHTML = ""; };

  function busy(btn, on) {
    if (!btn) return;
    if (on) {
      btn.dataset.label = btn.dataset.label || btn.textContent;
      btn.disabled = true;
      btn.innerHTML = `<span class="spin"></span>${btn.dataset.label}`;
    } else {
      btn.disabled = false;
      btn.textContent = btn.dataset.label || btn.textContent;
    }
  }

  // Wrap a panel action: manage busy state + error box uniformly.
  async function run(btn, errBox, fn) {
    clearError(errBox);
    busy(btn, true);
    try { await fn(); }
    catch (err) { showError(errBox, err); throw err !== undefined ? err : new Error("failed"); }
    finally { busy(btn, false); }
  }
  const safeRun = (btn, errBox, fn) => run(btn, errBox, fn).catch(() => {});

  // ── small renderers ──────────────────────────────────────────────────
  const stat = (num, lbl) => `<div class="stat"><div class="num">${esc(num)}</div><div class="lbl">${esc(lbl)}</div></div>`;
  const kv = (k, v) => `<div class="kv"><span class="k">${esc(k)}</span><span class="v">${esc(v)}</span></div>`;

  function vecChips(arr) {
    if (!arr || !arr.length) return "";
    return `<div class="vec">${arr.map((n) => `<span class="n">${esc(n)}</span>`).join("")}<span class="ell">…</span></div>`;
  }

  function chunkItems(chunks) {
    if (!chunks || !chunks.length) return `<p class="empty">No chunks.</p>`;
    return chunks.map((c) => `
      <div class="item">
        <div class="item-head">
          <span class="badge badge-brand">#${esc(c.index)}</span>
          <span class="badge">${esc(c.chars)} chars</span>
          <span class="badge">~${esc(c.approx_tokens)} tok</span>
        </div>
        <div class="item-text">${esc(c.text)}</div>
      </div>`).join("");
  }

  function hitItems(hits) {
    if (!hits || !hits.length) return `<p class="empty">No hits.</p>`;
    // Defensive: show highest score first regardless of server order.
    return [...hits].sort((a, b) => b.score - a.score).map((h) => {
      const pct = Math.max(0, Math.min(100, h.score * 100));
      const meta = [h.source && `src: ${h.source}`, h.strategy, h.index != null && `#${h.index}`]
        .filter(Boolean).join(" · ");
      return `
      <div class="item">
        <div class="item-head">
          <span class="score-num">${h.score.toFixed(4)}</span>
          <div class="score-wrap"><div class="score-track"><div class="score-fill" style="width:${pct}%"></div></div></div>
          ${meta ? `<span class="badge">${esc(meta)}</span>` : ""}
        </div>
        <div class="item-text">${esc(h.text)}</div>
      </div>`;
    }).join("");
  }

  // ── STATUS ───────────────────────────────────────────────────────────
  function setPill(state, text) {
    const pill = $("#health-pill");
    pill.className = "pill " + (state === "ok" ? "pill-ok" : state === "bad" ? "pill-bad" : "pill-muted");
    $(".pill-text", pill).textContent = text;
  }

  async function refreshStatus() {
    const errBox = $("#status-error");
    await safeRun($("#btn-status"), errBox, async () => {
      const [health, cfg] = await Promise.all([api("/health"), api("/config")]);
      const qOk = health.qdrant === "ok";
      setPill(qOk ? "ok" : "bad", qOk ? "healthy" : "Qdrant down");

      const cards = [
        `<div class="card"><h3>Service</h3>
           ${kv("status", health.status)}
           ${kv("qdrant", health.qdrant)}
           ${kv("qdrant_url", health.qdrant_url)}</div>`,
        `<div class="card"><h3>Chat model</h3>
           ${kv("provider", health.llm?.provider)}
           ${kv("model", health.llm?.model)}
           ${kv("temperature", cfg.generation?.temperature)}
           ${kv("max_tokens", cfg.generation?.max_tokens)}</div>`,
        `<div class="card"><h3>Embeddings</h3>
           ${kv("provider", health.embeddings?.provider)}
           ${kv("model", health.embeddings?.model)}</div>`,
        `<div class="card"><h3>Chunking defaults</h3>
           ${kv("strategy", cfg.chunking?.strategy)}
           ${kv("chunk_size", cfg.chunking?.chunk_size)}
           ${kv("chunk_overlap", cfg.chunking?.chunk_overlap)}
           ${kv("sentences_per_chunk", cfg.chunking?.sentences_per_chunk)}
           ${kv("semantic_threshold", cfg.chunking?.semantic_threshold)}</div>`,
        `<div class="card"><h3>Retrieval</h3>
           ${kv("top_k", cfg.retrieval?.top_k)}
           ${kv("collection", cfg.retrieval?.collection)}</div>`,
        `<div class="card"><h3>Azure Foundry</h3>
           ${kv("endpoint", cfg.providers?.azure?.endpoint)}
           ${kv("auth", cfg.providers?.azure?.auth)}
           ${kv("api_key", cfg.providers?.azure?.api_key)}
           ${kv("chat_deployment", cfg.providers?.azure?.chat_deployment)}
           ${kv("embedding_deployment", cfg.providers?.azure?.embedding_deployment)}</div>`,
      ];
      $("#status-cards").innerHTML = cards.join("");
      $("#status-raw").textContent = JSON.stringify(cfg, null, 2);
    });
    // If the health call itself failed, reflect that on the pill.
    if (!errBox.hidden) setPill("bad", "unreachable");
  }

  // Lightweight top-bar "Check" — just the pill, no full render.
  async function ping() {
    try {
      const h = await api("/health");
      const qOk = h.qdrant === "ok";
      setPill(qOk ? "ok" : "bad", qOk ? "healthy" : "Qdrant down");
    } catch { setPill("bad", "unreachable"); }
  }

  // ── build chunk/ingest request from the form (only send set fields) ──
  function chunkBody(prefix) {
    // The ingest form omits the fine-grained params, so tolerate missing fields.
    const val = (id) => { const el = $(prefix + id); return el ? el.value.trim() : ""; };
    const num = (id) => (val(id) === "" ? undefined : Number(val(id)));
    const strategy = $(prefix + "-strategy").value;
    const body = { text: $(prefix + "-text").value, strategy };
    const size = num("-size"), overlap = num("-overlap"), spc = num("-spc"), th = num("-threshold");
    if (size !== undefined) body.chunk_size = size;
    if (overlap !== undefined) body.chunk_overlap = overlap;
    if (spc !== undefined) body.sentences_per_chunk = spc;
    if (th !== undefined) body.semantic_threshold = th;
    return body;
  }

  // ── CHUNK ────────────────────────────────────────────────────────────
  async function doChunk() {
    store.strategy = $("#chunk-strategy").value; save();
    await safeRun($("#btn-chunk"), $("#chunk-error"), async () => {
      const data = await api("/chunk", { method: "POST", body: chunkBody("#chunk") });
      $("#chunk-result").innerHTML = `
        <div class="summary">
          ${stat(data.count, "chunks")}
          ${stat(data.strategy, "strategy")}
        </div>
        <details class="raw" open><summary>params_used</summary>
          <pre class="code">${esc(JSON.stringify(data.params_used, null, 2))}</pre></details>
        ${chunkItems(data.chunks)}`;
    });
  }

  // ── INGEST ───────────────────────────────────────────────────────────
  async function doIngest() {
    await safeRun($("#btn-ingest"), $("#ingest-error"), async () => {
      const body = chunkBody("#ingest");
      const src = $("#ingest-source").value.trim();
      if (src) body.source = src;
      const data = await api("/ingest", { method: "POST", body });
      $("#ingest-result").innerHTML = `
        <div class="summary">
          ${stat(data.count, "chunks stored")}
          ${stat(data.vector_dimension, "vector dimension")}
          ${stat(data.strategy, "strategy")}
        </div>
        <div class="card">
          <h3>Embedding</h3>
          ${kv("model", data.embedding_model?.model || JSON.stringify(data.embedding_model))}
          ${kv("provider", data.embedding_model?.provider || "—")}
          <div class="block-label">preview · first 8 of ${esc(data.vector_dimension)} dims</div>
          ${vecChips(data.embedding_preview)}
        </div>
        <div class="block-label">stored chunks</div>
        ${chunkItems(data.chunks)}`;
    });
  }

  // ── COLLECTION ───────────────────────────────────────────────────────
  async function doCollection() {
    await safeRun($("#btn-collection"), $("#collection-error"), async () => {
      const c = await api("/collection");
      $("#collection-result").innerHTML = `
        <div class="summary">
          ${stat(c.exists ? "yes" : "no", "exists")}
          ${stat(c.points_count, "points")}
          ${stat(c.vector_dimension ?? "—", "dimension")}
        </div>
        <div class="card">
          ${kv("name", c.name)}
          ${kv("exists", c.exists)}
          ${kv("points_count", c.points_count)}
          ${kv("vector_dimension", c.vector_dimension ?? "—")}
          ${kv("distance", c.distance ?? "—")}
        </div>`;
    });
  }

  async function doCollectionDelete() {
    if (!confirm("Delete the whole collection? This wipes every stored vector. This cannot be undone.")) return;
    await safeRun($("#btn-collection-del"), $("#collection-error"), async () => {
      const r = await api("/collection", { method: "DELETE" });
      $("#collection-result").innerHTML = `
        <div class="summary">${stat(r.deleted ? "deleted" : "nothing", "result")}</div>
        <div class="card">${kv("deleted", r.deleted)}${kv("collection", r.collection)}</div>`;
    });
  }

  // ── SEARCH ───────────────────────────────────────────────────────────
  async function doSearch() {
    const topk = $("#search-topk").value.trim();
    store.topK = topk; save();
    await safeRun($("#btn-search"), $("#search-error"), async () => {
      const body = { query: $("#search-query").value };
      if (topk !== "") body.top_k = Number(topk);
      const data = await api("/search", { method: "POST", body });
      $("#search-result").innerHTML = `
        <div class="summary">
          ${stat(data.hits.length, "hits")}
          ${stat(data.top_k, "top_k")}
        </div>
        <div class="card">
          <h3>Query embedding</h3>
          ${kv("model", data.embedding_model?.model || JSON.stringify(data.embedding_model))}
          <div class="block-label">preview · first 8 dims</div>
          ${vecChips(data.query_embedding_preview)}
        </div>
        <div class="block-label">results · highest similarity first</div>
        ${hitItems(data.hits)}`;
    });
  }

  // ── ASK ──────────────────────────────────────────────────────────────
  function askBody(useRag) {
    const body = { question: $("#ask-question").value, use_rag: useRag };
    const topk = $("#ask-topk").value.trim();
    const temp = $("#ask-temp").value.trim();
    if (topk !== "") body.top_k = Number(topk);
    if (temp !== "") body.temperature = Number(temp);
    return body;
  }

  function askCard(data) {
    const tokens = data.usage
      ? `${data.usage.prompt_tokens ?? "?"} in / ${data.usage.completion_tokens ?? "?"} out`
      : "—";
    return `
      <div class="summary">
        ${stat(data.augmented ? "on" : "off", "use_rag")}
        ${stat(data.retrieved?.length ?? 0, "retrieved")}
        ${stat(tokens, "tokens")}
      </div>
      <div class="block-label">answer · ${esc(data.provider)} / ${esc(data.model)}</div>
      <div class="answer">${esc(data.answer)}</div>
      <div class="block-label">prompt_sent — the exact user prompt the model received</div>
      <pre class="code">${esc(data.prompt_sent)}</pre>
      <details class="raw"><summary>system_prompt</summary>
        <pre class="code">${esc(data.system_prompt)}</pre></details>
      <div class="block-label">retrieved chunks</div>
      ${hitItems(data.retrieved)}`;
  }

  async function doAsk() {
    const useRag = $("#ask-userag").checked;
    store.useRag = useRag; store.temp = $("#ask-temp").value.trim(); save();
    await safeRun($("#btn-ask"), $("#ask-error"), async () => {
      const data = await api("/ask", { method: "POST", body: askBody(useRag) });
      $("#ask-result").innerHTML = askCard(data);
    });
  }

  // Stretch goal: same question, use_rag off vs on, side by side.
  async function doAskCompare() {
    await safeRun($("#btn-ask-compare"), $("#ask-error"), async () => {
      const [off, on] = await Promise.all([
        api("/ask", { method: "POST", body: askBody(false) }),
        api("/ask", { method: "POST", body: askBody(true) }),
      ]);
      $("#ask-result").innerHTML = `
        <div class="compare">
          <div><div class="block-label">use_rag = false (plain LLM)</div>${askCard(off)}</div>
          <div><div class="block-label">use_rag = true (RAG)</div>${askCard(on)}</div>
        </div>`;
    });
  }

  // ── tabs ─────────────────────────────────────────────────────────────
  function activateTab(name) {
    $$(".tab").forEach((t) => t.classList.toggle("is-active", t.dataset.tab === name));
    $$(".panel").forEach((p) => p.classList.toggle("is-active", p.id === "tab-" + name));
  }

  // Show only the chunk params relevant to the chosen strategy.
  function syncStrategyFields() {
    const s = $("#chunk-strategy").value;
    $$('#tab-chunk [data-when]').forEach((el) => {
      el.style.display = el.dataset.when.split(" ").includes(s) ? "" : "none";
    });
  }

  // ── wire up ──────────────────────────────────────────────────────────
  function init() {
    // restore persisted settings into the inputs
    $("#base-url").value = store.baseUrl;
    $("#chunk-strategy").value = store.strategy;
    $("#ingest-strategy").value = store.strategy;
    $("#search-topk").value = store.topK;
    $("#ask-topk").value = store.topK;
    $("#ask-temp").value = store.temp;
    $("#ask-userag").checked = store.useRag;
    $("#chunk-text").value = EXAMPLE;
    $("#ingest-text").value = EXAMPLE;
    $("#ingest-source").value = "retail-faq";
    $("#ask-question").placeholder = "What fee does Libra Bank charge for early mortgage repayment?";

    $("#base-url").addEventListener("change", () => { store.baseUrl = $("#base-url").value.trim(); save(); ping(); });
    $$(".tab").forEach((t) => t.addEventListener("click", () => activateTab(t.dataset.tab)));

    $("#btn-ping").addEventListener("click", ping);
    $("#btn-status").addEventListener("click", refreshStatus);
    $("#chunk-strategy").addEventListener("change", syncStrategyFields);
    $("#btn-chunk").addEventListener("click", doChunk);
    $("#btn-ingest").addEventListener("click", doIngest);
    $("#btn-collection").addEventListener("click", doCollection);
    $("#btn-collection-del").addEventListener("click", doCollectionDelete);
    $("#btn-search").addEventListener("click", doSearch);
    $("#btn-ask").addEventListener("click", doAsk);
    $("#btn-ask-compare").addEventListener("click", doAskCompare);

    // Enter-to-submit on the single-line query/question inputs.
    $("#search-query").addEventListener("keydown", (e) => { if (e.key === "Enter") doSearch(); });
    $("#ask-question").addEventListener("keydown", (e) => { if (e.key === "Enter") doAsk(); });

    syncStrategyFields();
    refreshStatus(); // auto-load status on open
  }

  document.addEventListener("DOMContentLoaded", init);
})();
