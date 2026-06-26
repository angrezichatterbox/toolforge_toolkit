/* ============================================================
   Deployr — frontend logic
   Talks to the Toolforge Manager API:
     GET  /                        → health + endpoint list
     GET  /api/config              → { username, tool_name, ssh_key, bastion_host }
     POST /api/config              → save global creds / active tool_name
     POST /api/test-connection     → { success, message }
     POST /api/deploy              → { success, logs:[{message,category}], url? }
     GET  /api/webservice/status   → { success, status }   (status is free text)
     POST /api/webservice/control  → { success, message, output?, error? }
   ============================================================ */

(() => {
  "use strict";

  // ── State ──────────────────────────────────────────────
  const LS = {
    apiBase: "deployr.apiBase",
    tools: "deployr.tools",
    theme: "deployr.theme",
  };

  const state = {
    apiBase: localStorage.getItem(LS.apiBase) || "",
    tools: loadTools(),
    activeTool: null,      // tool_name currently set in backend config
    filter: "all",
    search: "",
    drawerToolId: null,
    apiOnline: false,
    addDraft: null,
  };

  // ── Tiny DOM helpers ───────────────────────────────────
  const $ = (sel, root = document) => root.querySelector(sel);
  const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];

  // ── Persistence of per-tool edits ──────────────────────
  function loadTools() {
    const seed = (window.DEPLOYR_TOOLS || []).map((t) => ({ ...t }));
    try {
      const saved = JSON.parse(localStorage.getItem(LS.tools) || "{}");
      seed.forEach((t) => {
        if (saved[t.id]) Object.assign(t, saved[t.id]);
      });
    } catch (_) { /* ignore */ }
    return seed;
  }
  function persistTool(tool) {
    let saved = {};
    try { saved = JSON.parse(localStorage.getItem(LS.tools) || "{}"); } catch (_) {}
    saved[tool.id] = {
      tool: tool.tool, git_url: tool.git_url, branch: tool.branch,
      entry_file: tool.entry_file, app_var_name: tool.app_var_name,
      python_version: tool.python_version,
    };
    localStorage.setItem(LS.tools, JSON.stringify(saved));
  }

  // ── API layer ──────────────────────────────────────────
  function apiUrl(path) {
    const base = state.apiBase.replace(/\/$/, "");
    return base + path;
  }
  async function api(path, { method = "GET", body } = {}) {
    const res = await fetch(apiUrl(path), {
      method,
      headers: body ? { "Content-Type": "application/json" } : undefined,
      body: body ? JSON.stringify(body) : undefined,
    });
    const text = await res.text();
    let data;
    try { data = text ? JSON.parse(text) : {}; }
    catch (_) { data = { raw: text }; }
    if (!res.ok && data.success === undefined) {
      throw new Error(data.message || `HTTP ${res.status}`);
    }
    return data;
  }

  async function pingApi() {
    setPill("unknown", "LINK…");
    try {
      // /api/config always returns JSON when the backend is up — and unlike "/",
      // it isn't shadowed when the UI is served same-origin.
      const data = await api("/api/config");
      if (data && typeof data === "object" && !("raw" in data)) {
        state.apiOnline = true;
        setPill("ok", "LINK OK");
        return true;
      }
      throw new Error("unexpected response");
    } catch (_) {
      state.apiOnline = false;
      setPill("down", "NO LINK");
      return false;
    }
  }
  function setPill(kind, label) {
    const pill = $("#apiStatus");
    pill.className = `api-pill api-pill--${kind}`;
    $(".api-pill__label", pill).textContent = label;
  }

  // Catalogue comes from the backend DB; data.js is only an offline fallback.
  async function loadToolsFromApi() {
    if (!state.apiOnline) return;
    try {
      const data = await api("/api/tools");
      if (Array.isArray(data.tools) && data.tools.length) {
        let saved = {};
        try { saved = JSON.parse(localStorage.getItem(LS.tools) || "{}"); } catch (_) {}
        state.tools = data.tools.map((t) => (saved[t.id] ? { ...t, ...saved[t.id] } : t));
        renderTools();
      } else if (data.error) {
        toast("warn", "Catalogue offline", "Showing bundled fallback list.");
      }
    } catch (e) {
      console.warn("tools load failed", e);
    }
  }

  async function loadBackendConfig() {
    if (!state.apiOnline) return;
    try {
      const cfg = await api("/api/config");
      $("#cfgUsername").value = cfg.username || "";
      $("#cfgSshKey").value = cfg.ssh_key || "";
      $("#cfgBastion").value = cfg.bastion_host || "login.toolforge.org";
      state.activeTool = cfg.tool_name || null;
      renderTools();
      if (state.activeTool) refreshStatusByName(state.activeTool);
    } catch (e) {
      console.warn("config load failed", e);
    }
  }

  // Set a tool as the backend's active tool (so status/control target it)
  async function ensureActive(tool) {
    if (state.activeTool === tool.tool) return;
    await api("/api/config", { method: "POST", body: { tool_name: tool.tool } });
    state.activeTool = tool.tool;
    renderTools();
  }

  function parseStatus(text, success) {
    const s = (text || "").toLowerCase();
    if (s.includes("not running") || s.includes("is not") || s.includes("stopped") || s.includes("no webservice")) return "stopped";
    if (s.includes("running") || s.includes("up")) return "running";
    return success ? "running" : "unknown";
  }

  async function refreshStatusByName(name) {
    const tool = state.tools.find((t) => t.tool === name);
    if (tool) refreshStatus(tool, true);
  }

  async function refreshStatus(tool, silent = false) {
    if (!state.apiOnline) { if (!silent) toast("error", "API offline", "Set the backend URL in Settings."); return; }
    try {
      await ensureActive(tool);
      const data = await api("/api/webservice/status");
      tool.status = parseStatus(data.status, data.success);
      renderTools();
      if (state.drawerToolId === tool.id) {
        appendLog(`webservice status → ${tool.status}`, "info");
        appendLog((data.status || "").trim(), "remote");
      }
    } catch (e) {
      if (!silent) toast("error", "Status check failed", e.message);
    }
  }

  // ── Deploy ─────────────────────────────────────────────
  async function deploy(tool) {
    if (!state.apiOnline) { toast("error", "API offline", "Start the backend and set its URL in Settings."); return; }
    if (!tool.git_url) { toast("warn", "No source URL", "Add a git/archive URL in the Configuration tab."); return; }

    const btn = $("#deployBtn");
    const prev = btn.innerHTML;
    btn.disabled = true;
    btn.innerHTML = `${spinnerSvg()} Deploying…`;
    tool.status = "deploying";
    renderTools();
    clearConsole();
    $("#console").classList.add("launching");
    setConsoleTitle(`launch · ${tool.tool}`);
    appendLog(`$ launch ${tool.repo} → tools.${tool.tool}`, "cmd");
    appendLog("ignition sequence start…", "warning");

    try {
      const data = await api("/api/deploy", {
        method: "POST",
        body: {
          url: tool.git_url,
          tool_name: tool.tool,
          entry_file: tool.entry_file || "app.py",
          app_var_name: tool.app_var_name || "app",
          python_version: tool.python_version || "python3.11",
        },
      });
      state.activeTool = tool.tool;
      await streamLogs(data.logs || []);
      if (data.success) {
        tool.status = "running";
        tool.lastDeploy = new Date().toISOString();
        toast("ok", "Deployed", `${tool.name} is live${data.url ? "" : ""}.`);
        if (data.url) appendLog(`★ ${data.url}`, "success");
      } else {
        tool.status = "error";
        toast("error", "Deploy failed", "See the console for details.");
      }
    } catch (e) {
      tool.status = "error";
      appendLog(`fatal: ${e.message}`, "error");
      toast("error", "Deploy failed", e.message);
    } finally {
      btn.disabled = false;
      btn.innerHTML = prev;
      $("#console").classList.remove("launching");
      renderTools();
    }
  }

  async function streamLogs(logs) {
    for (const entry of logs) {
      appendLog(entry.message, entry.category || "info");
      // small delay for a live-tail feel, capped for long logs
      await sleep(logs.length > 40 ? 8 : 45);
    }
  }

  // ── Webservice control ─────────────────────────────────
  async function control(tool, action) {
    if (!state.apiOnline) { toast("error", "API offline", "Set the backend URL in Settings."); return; }
    setConsoleTitle(`${action} ${tool.tool}`);
    appendLog(`$ toolforge webservice ${action}`, "cmd");
    if (action !== "stop") tool.status = "deploying";
    renderTools();
    try {
      await ensureActive(tool);
      const data = await api("/api/webservice/control", {
        method: "POST",
        body: { action, type: tool.python_version || "python3.11" },
      });
      appendLog((data.output || data.message || data.error || "").trim(), data.success ? "info" : "error");
      if (data.success) {
        tool.status = action === "stop" ? "stopped" : "running";
        toast("ok", `Webservice ${action}`, data.message || "Done.");
      } else {
        tool.status = "error";
        toast("error", `${action} failed`, data.message || data.error || "Unknown error.");
      }
    } catch (e) {
      tool.status = "error";
      appendLog(`error: ${e.message}`, "error");
      toast("error", `${action} failed`, e.message);
    } finally {
      renderTools();
    }
  }

  // ── Rendering ──────────────────────────────────────────
  const STATUS_LABEL = { running: "Running", stopped: "Stopped", deploying: "Deploying", unknown: "Unknown", error: "Error" };

  function filteredTools() {
    const q = state.search.trim().toLowerCase();
    return state.tools.filter((t) => {
      const matchesFilter = state.filter === "all" || t.status === state.filter;
      const matchesSearch = !q ||
        t.name.toLowerCase().includes(q) ||
        t.repo.toLowerCase().includes(q) ||
        t.tool.toLowerCase().includes(q);
      return matchesFilter && matchesSearch;
    });
  }

  function renderTools() {
    const grid = $("#toolGrid");
    const list = filteredTools();
    grid.innerHTML = list.map((t, i) => cardHtml(t, i)).join("");
    $("#emptyState").hidden = list.length > 0;

    // stats over ALL tools (not filtered) — animated count-up
    const count = (s) => state.tools.filter((t) => t.status === s).length;
    setStat("#statTotal", state.tools.length);
    setStat("#statRunning", count("running"));
    setStat("#statStopped", count("stopped"));
    setStat("#statDeploying", count("deploying"));

    // wire card buttons
    $$(".js-deploy", grid).forEach((b) => b.addEventListener("click", (e) => {
      e.stopPropagation();
      const tool = byId(b.dataset.id);
      openDrawer(tool, "deploy");
      deploy(tool);
    }));
    $$(".js-manage", grid).forEach((b) => b.addEventListener("click", () => openDrawer(byId(b.dataset.id), "deploy")));
    $$(".card", grid).forEach((c) => c.addEventListener("click", () => openDrawer(byId(c.dataset.id), "deploy")));
    $$(".card__link", grid).forEach((a) => a.addEventListener("click", (e) => e.stopPropagation()));
  }

  function cardHtml(t, i = 0) {
    const isActive = state.activeTool && state.activeTool === t.tool;
    const st = t.status || "unknown";
    const code = "TF-" + String(t.tool || t.id).slice(0, 6).toUpperCase();
    return `
      <article class="card ${isActive ? "card--active" : ""}" data-id="${t.id}" style="--i:${i}">
        <span class="card__sheen"></span>
        <div class="card__top">
          <div class="card__title">
            <span class="card__id">${escapeHtml(code)} · BAY ${String(i + 1).padStart(2, "0")}</span>
            <span class="card__name">
              ${escapeHtml(t.name)}
              ${t.live ? `<span class="tag" title="Connected to backend">live</span>` : ""}
            </span>
            <span class="card__repo">${escapeHtml(t.repo)}</span>
          </div>
          <span class="badge badge--${st}"><span class="badge__dot"></span>${STATUS_LABEL[st]}</span>
        </div>
        <p class="card__desc">${escapeHtml(t.description || "")}</p>
        <div class="card__meta">
          <span class="tag tag--lang">${escapeHtml(t.language || "")}</span>
          <span class="tag tag--lang">tools.${escapeHtml(t.tool)}</span>
          ${isActive ? `<span class="card__active-flag">active</span>` : ""}
        </div>
        <div class="card__footer">
          <a class="card__link" href="${escapeAttr(t.url)}" target="_blank" rel="noopener">
            <svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/><polyline points="15 3 21 3 21 9"/><line x1="10" y1="14" x2="21" y2="3"/></svg>
            ${prettyHost(t.url)}
          </a>
          <div class="card__actions">
            <button class="btn btn--ghost btn--sm js-manage" data-id="${t.id}">Manage</button>
            <button class="btn btn--primary btn--sm js-deploy" data-id="${t.id}">Deploy</button>
          </div>
        </div>
      </article>`;
  }

  // ── Drawer ─────────────────────────────────────────────
  function openDrawer(tool, tab = "deploy") {
    if (!tool) return;
    state.drawerToolId = tool.id;
    $("#drawerTitle").textContent = tool.name;
    $("#drawerSub").textContent = `${tool.repo} → tools.${tool.tool}`;
    fillConfigForm(tool);
    switchTab(tab);
    setConsoleTitle(`${tool.tool} console`);
    $("#overlay").hidden = false;
    const drawer = $("#drawer");
    drawer.classList.add("open");
    drawer.setAttribute("aria-hidden", "false");
  }
  function closeDrawer() {
    const drawer = $("#drawer");
    drawer.classList.remove("open");
    drawer.setAttribute("aria-hidden", "true");
    $("#overlay").hidden = true;
    state.drawerToolId = null;
  }
  function currentTool() { return byId(state.drawerToolId); }

  function switchTab(tab) {
    $$(".drawer__tab").forEach((b) => b.classList.toggle("drawer__tab--active", b.dataset.tab === tab));
    $$(".drawer__panel").forEach((p) => (p.hidden = p.dataset.panel !== tab));
  }

  function fillConfigForm(tool) {
    const f = $("#configForm");
    f.tool.value = tool.tool || "";
    f.git_url.value = tool.git_url || "";
    f.entry_file.value = tool.entry_file || "";
    f.app_var_name.value = tool.app_var_name || "";
    f.python_version.value = tool.python_version || "python3.11";
    f.branch.value = tool.branch || "";
  }

  // ── Console ────────────────────────────────────────────
  function clearConsole() { $("#consoleBody").innerHTML = ""; }
  function setConsoleTitle(t) { $("#consoleTitle").textContent = t; }
  function appendLog(message, category = "info") {
    if (!message) return;
    const body = $("#consoleBody");
    const empty = $(".console__empty", body);
    if (empty) empty.remove();
    const line = document.createElement("span");
    line.className = `log-line log-${category}`;
    line.dataset.cat = catTag(category);
    line.textContent = message;
    body.appendChild(line);
    body.scrollTop = body.scrollHeight;
  }
  function catTag(c) {
    return ({ info: "›", remote: "⟫", success: "✔", error: "✖", warning: "!", cmd: "$" })[c] || "›";
  }

  // ── Toasts ─────────────────────────────────────────────
  function toast(kind, title, msg = "") {
    const wrap = $("#toasts");
    const el = document.createElement("div");
    el.className = `toast toast--${kind}`;
    el.innerHTML = `
      <span class="toast__icon">${toastIcon(kind)}</span>
      <div class="toast__body">
        <div class="toast__title">${escapeHtml(title)}</div>
        ${msg ? `<div class="toast__msg">${escapeHtml(msg)}</div>` : ""}
      </div>`;
    wrap.appendChild(el);
    setTimeout(() => {
      el.classList.add("hide");
      setTimeout(() => el.remove(), 220);
    }, 4200);
  }
  function toastIcon(kind) {
    const s = (d) => `<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">${d}</svg>`;
    if (kind === "ok") return s(`<path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/>`);
    if (kind === "error") return s(`<circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/>`);
    if (kind === "warn") return s(`<path d="M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/>`);
    return s(`<circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/>`);
  }

  // ── Settings modal ─────────────────────────────────────
  function openSettings() {
    $("#apiBaseInput").value = state.apiBase;
    $("#settingsOverlay").hidden = false;
    $("#settingsModal").hidden = false;
  }
  function closeSettings() {
    $("#settingsOverlay").hidden = true;
    $("#settingsModal").hidden = true;
  }
  async function saveSettings() {
    state.apiBase = $("#apiBaseInput").value.trim();
    localStorage.setItem(LS.apiBase, state.apiBase);
    const online = await pingApi();
    if (online) {
      try {
        await api("/api/config", {
          method: "POST",
          body: {
            username: $("#cfgUsername").value.trim(),
            ssh_key: $("#cfgSshKey").value.trim(),
            bastion_host: $("#cfgBastion").value.trim() || "login.toolforge.org",
          },
        });
        toast("ok", "Settings saved", "Connection details stored on the backend.");
      } catch (e) {
        toast("error", "Save failed", e.message);
      }
    } else {
      toast("warn", "Saved locally", "Backend not reachable at that URL yet.");
    }
    closeSettings();
  }

  // ── Animated stat count-up ─────────────────────────────
  function setStat(sel, target) {
    const el = $(sel);
    if (!el) return;
    const from = parseInt(el.dataset.count || "0", 10) || 0;
    if (from === target) { el.textContent = target; return; }
    el.dataset.count = target;
    const start = performance.now();
    const dur = 480;
    function step(now) {
      const p = Math.min(1, (now - start) / dur);
      const eased = 1 - Math.pow(1 - p, 3);
      el.textContent = Math.round(from + (target - from) * eased);
      if (p < 1 && el.dataset.count == String(target)) requestAnimationFrame(step);
      else el.textContent = target;
    }
    requestAnimationFrame(step);
  }

  // ── Mission clock (UTC) ────────────────────────────────
  function startClock() {
    const el = $("#missionClock");
    if (!el) return;
    const tick = () => {
      const d = new Date();
      const p = (n) => String(n).padStart(2, "0");
      el.textContent = `${p(d.getUTCHours())}:${p(d.getUTCMinutes())}:${p(d.getUTCSeconds())}`;
    };
    tick();
    setInterval(tick, 1000);
  }

  // ── Add payload (paste repo → inspect → save) ──────────
  function openAdd() {
    $("#addUrl").value = "";
    $("#addDetails").hidden = true;
    $("#addSave").disabled = true;
    state.addDraft = null;
    $("#addOverlay").hidden = false;
    $("#addModal").hidden = false;
    setTimeout(() => $("#addUrl").focus(), 50);
  }
  function closeAdd() { $("#addOverlay").hidden = true; $("#addModal").hidden = true; }

  async function inspectRepo() {
    if (!state.apiOnline) { toast("error", "No link", "Start the backend and set its URL in Config."); return; }
    const url = $("#addUrl").value.trim();
    if (!url) { toast("warn", "Paste a URL", "A git repo or archive URL is required."); return; }
    const btn = $("#inspectBtn");
    btn.disabled = true; const prev = btn.textContent; btn.textContent = "Inspecting…";
    try {
      const data = await api("/api/tools/inspect", { method: "POST", body: { url } });
      if (!data.success) throw new Error(data.message || "inspect failed");
      const t = data.tool;
      state.addDraft = t;
      $("#addName").value = t.name || "";
      $("#addTool").value = t.tool || "";
      $("#addBranch").value = t.branch || "main";
      $("#addPy").value = t.python_version || "python3.11";
      $("#addEntry").value = t.entry_file || "app.py";
      $("#addAppVar").value = t.app_var_name || "app";
      $("#addLang").value = t.language || "";
      $("#addDesc").value = t.description || "";
      $("#addDetails").hidden = false;
      $("#addSave").disabled = false;
      toast("ok", "Repo inspected", `${t.repo} — review and add.`);
    } catch (e) {
      toast("error", "Inspect failed", e.message);
    } finally {
      btn.disabled = false; btn.textContent = prev;
    }
  }

  async function saveNewTool() {
    if (!state.addDraft) { toast("warn", "Inspect first", "Paste a URL and inspect it."); return; }
    const tool = $("#addTool").value.trim();
    const payload = {
      git_url: state.addDraft.git_url,
      id: state.addDraft.id,
      repo: state.addDraft.repo,
      name: $("#addName").value.trim() || tool,
      tool,
      branch: $("#addBranch").value.trim() || "main",
      python_version: $("#addPy").value,
      entry_file: $("#addEntry").value.trim() || "app.py",
      app_var_name: $("#addAppVar").value.trim() || "app",
      language: $("#addLang").value.trim(),
      description: $("#addDesc").value.trim(),
      url: `https://${tool}.toolforge.org/`,
      status: "unknown",
    };
    const btn = $("#addSave");
    btn.disabled = true; const prev = btn.textContent; btn.textContent = "Adding…";
    try {
      const data = await api("/api/tools", { method: "POST", body: payload });
      if (!data.success) throw new Error(data.message || "add failed");
      await loadToolsFromApi();
      closeAdd();
      toast("ok", "Payload added", `${data.tool.name} is in the catalogue.`);
      const added = byId(data.tool.id);
      if (added) openDrawer(added, "deploy");
    } catch (e) {
      toast("error", "Add failed", e.message);
    } finally {
      btn.disabled = false; btn.textContent = prev;
    }
  }

  async function deleteTool(tool) {
    if (!state.apiOnline) { toast("error", "No link", "Backend not reachable."); return; }
    if (!confirm(`Remove "${tool.name}" (tools.${tool.tool}) from the catalogue?`)) return;
    try {
      const data = await api(`/api/tools/${encodeURIComponent(tool.id)}`, { method: "DELETE" });
      if (!data.success) throw new Error(data.message || "delete failed");
      closeDrawer();
      await loadToolsFromApi();
      toast("ok", "Payload removed", `${tool.name} deleted.`);
    } catch (e) {
      toast("error", "Remove failed", e.message);
    }
  }

  // ── Utilities ──────────────────────────────────────────
  function byId(id) { return state.tools.find((t) => t.id === id); }
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  function escapeHtml(s) { return String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c])); }
  function escapeAttr(s) { return escapeHtml(s); }
  function prettyHost(url) { try { return new URL(url).host; } catch { return url || ""; } }
  function spinnerSvg() {
    return `<svg class="spin" viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M21 12a9 9 0 1 1-6.22-8.56"/></svg>`;
  }

  // ── Theme ──────────────────────────────────────────────
  function initTheme() {
    // dark-first: mission control lives in the dark. Honor a saved override.
    document.documentElement.dataset.theme = localStorage.getItem(LS.theme) || "dark";
  }
  function toggleTheme() {
    const next = document.documentElement.dataset.theme === "dark" ? "light" : "dark";
    document.documentElement.dataset.theme = next;
    localStorage.setItem(LS.theme, next);
  }

  // ── Event wiring ───────────────────────────────────────
  function wire() {
    $("#themeToggle").addEventListener("click", toggleTheme);
    $("#settingsBtn").addEventListener("click", openSettings);
    $("#settingsClose").addEventListener("click", closeSettings);
    $("#settingsOverlay").addEventListener("click", closeSettings);
    $("#saveSettingsBtn").addEventListener("click", saveSettings);
    $("#testConnBtn").addEventListener("click", async () => {
      if (!(await pingApi())) { toast("error", "API offline", "Backend not reachable."); return; }
      const btn = $("#testConnBtn");
      btn.disabled = true; const prev = btn.textContent; btn.textContent = "Testing…";
      try {
        const data = await api("/api/test-connection", { method: "POST" });
        toast(data.success ? "ok" : "error", data.success ? "Connection OK" : "Connection failed", data.message);
      } catch (e) { toast("error", "Connection failed", e.message); }
      finally { btn.disabled = false; btn.textContent = prev; }
    });
    $("#pingBtn") && $("#pingBtn").addEventListener("click", pingApi);

    $("#drawerClose").addEventListener("click", closeDrawer);
    $("#overlay").addEventListener("click", closeDrawer);
    $$(".drawer__tab").forEach((b) => b.addEventListener("click", () => switchTab(b.dataset.tab)));

    $("#deployBtn").addEventListener("click", () => { const t = currentTool(); if (t) deploy(t); });
    $("#refreshStatusBtn").addEventListener("click", () => { const t = currentTool(); if (t) refreshStatus(t); });
    $("#consoleClear").addEventListener("click", clearConsole);
    $$("[data-control]").forEach((b) => b.addEventListener("click", () => {
      const t = currentTool(); if (t) control(t, b.dataset.control);
    }));

    // Add-payload modal
    $("#addBtn").addEventListener("click", openAdd);
    $("#addClose").addEventListener("click", closeAdd);
    $("#addCancel").addEventListener("click", closeAdd);
    $("#addOverlay").addEventListener("click", closeAdd);
    $("#inspectBtn").addEventListener("click", inspectRepo);
    $("#addUrl").addEventListener("keydown", (e) => { if (e.key === "Enter") { e.preventDefault(); inspectRepo(); } });
    $("#addSave").addEventListener("click", saveNewTool);
    $("#removeBtn").addEventListener("click", () => { const t = currentTool(); if (t) deleteTool(t); });

    $("#setActiveBtn").addEventListener("click", async () => {
      const t = currentTool(); if (!t) return;
      if (!state.apiOnline) { toast("error", "API offline", "Set the backend URL in Settings."); return; }
      try { await ensureActive(t); toast("ok", "Active tool set", `tools.${t.tool} is now the deploy target.`); }
      catch (e) { toast("error", "Failed", e.message); }
    });

    $("#configForm").addEventListener("submit", (e) => {
      e.preventDefault();
      const t = currentTool(); if (!t) return;
      const f = e.target;
      t.tool = f.tool.value.trim();
      t.git_url = f.git_url.value.trim();
      t.entry_file = f.entry_file.value.trim();
      t.app_var_name = f.app_var_name.value.trim();
      t.python_version = f.python_version.value;
      t.branch = f.branch.value.trim();
      persistTool(t);
      $("#drawerSub").textContent = `${t.repo} → tools.${t.tool}`;
      renderTools();
      toast("ok", "Configuration saved", `${t.name} updated.`);
    });

    $("#searchInput").addEventListener("input", (e) => { state.search = e.target.value; renderTools(); });
    $$("#filters .chip").forEach((c) => c.addEventListener("click", () => {
      $$("#filters .chip").forEach((x) => x.classList.remove("chip--active"));
      c.classList.add("chip--active");
      state.filter = c.dataset.filter;
      renderTools();
    }));

    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape") { closeDrawer(); closeSettings(); closeAdd(); }
    });
  }

  // ── Boot ───────────────────────────────────────────────
  async function init() {
    initTheme();
    startClock();
    wire();
    renderTools();
    await pingApi();
    await loadToolsFromApi();
    await loadBackendConfig();
  }

  document.addEventListener("DOMContentLoaded", init);
})();
