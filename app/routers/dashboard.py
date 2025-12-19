# app/routers/dashboard.py
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse

from app.core.logging import get_logger
from app.core.redis import RedisManager, caches
from app.core.security import validate_authbridge_api_key
from app.models import ServiceLink
from app.routers.service import reload_services
from app.routers.workspace import reload_workspaces
from app.routers.token import RSA_KEYS, CURRENT_KID  # for JWKS stats

log = get_logger("auth-bridge.dashboard")

router = APIRouter(tags=["dashboard"])

DASHBOARD_HTML = """
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width,initial-scale=1"/>
  <title>AuthBridge • Trust Dashboard</title>
  <script src="https://cdn.tailwindcss.com"></script>
  <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css" rel="stylesheet">
  <script>
    tailwind.config = {
      theme: {
        extend: {
          colors: {
            primary: {
              50: '#f0f9ff',
              100: '#e0f2fe',
              200: '#bae6fd',
              300: '#7dd3fc',
              400: '#38bdf8',
              500: '#0ea5e9',
              600: '#0284c7',
              700: '#0369a1',
              800: '#075985',
              900: '#0c4a6e',
            },
            gradient: {
              start: '#667eea',
              end: '#764ba2'
            }
          },
          animation: {
            'fade-in': 'fadeIn 0.5s ease-in-out',
            'slide-up': 'slideUp 0.3s ease-out',
            'pulse-soft': 'pulseSoft 2s infinite',
          },
          keyframes: {
            fadeIn: {
              '0%': { opacity: '0' },
              '100%': { opacity: '1' }
            },
            slideUp: {
              '0%': { transform: 'translateY(10px)', opacity: '0' },
              '100%': { transform: 'translateY(0)', opacity: '1' }
            },
            pulseSoft: {
              '0%, 100%': { opacity: '1' },
              '50%': { opacity: '0.8' }
            }
          }
        }
      }
    }
  </script>
  <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');
    
    * {
      font-family: 'Inter', sans-serif;
    }
    
    :root {
      --glass-bg: rgba(255, 255, 255, 0.7);
      --glass-border: rgba(255, 255, 255, 0.2);
      --shadow-soft: 0 4px 6px -1px rgba(0, 0, 0, 0.05), 0 2px 4px -1px rgba(0, 0, 0, 0.03);
      --shadow-card: 0 10px 15px -3px rgba(0, 0, 0, 0.05), 0 4px 6px -2px rgba(0, 0, 0, 0.025);
    }
    
    body {
      background: linear-gradient(135deg, #f5f7fa 0%, #e4edf5 100%);
      min-height: 100vh;
    }
    
    .glass {
      background: var(--glass-bg);
      backdrop-filter: blur(10px);
      border: 1px solid var(--glass-border);
    }
    
    .card {
      background: white;
      border-radius: 16px;
      box-shadow: var(--shadow-card);
      border: 1px solid rgba(226, 232, 240, 0.8);
      transition: all 0.3s ease;
    }
    
    .card:hover {
      box-shadow: 0 20px 25px -5px rgba(0, 0, 0, 0.08), 0 10px 10px -5px rgba(0, 0, 0, 0.02);
      transform: translateY(-2px);
    }
    
    .btn {
      padding: 0.6rem 1.2rem;
      border-radius: 10px;
      font-weight: 600;
      transition: all 0.2s ease;
      display: inline-flex;
      align-items: center;
      gap: 0.5rem;
    }
    
    .btn:active {
      transform: scale(0.98);
    }
    
    .input, .select, .textarea {
      width: 100%;
      padding: 0.75rem 1rem;
      border: 1px solid rgb(226, 232, 240);
      border-radius: 10px;
      background: white;
      transition: all 0.2s ease;
      box-shadow: 0 1px 2px rgba(0, 0, 0, 0.03);
    }
    
    .input:focus, .select:focus, .textarea:focus {
      border-color: rgb(14, 165, 233);
      box-shadow: 0 0 0 3px rgba(14, 165, 233, 0.1);
      outline: none;
    }
    
    .label {
      font-size: 0.8rem;
      font-weight: 600;
      color: rgb(71, 85, 105);
      margin-bottom: 0.5rem;
      display: block;
    }
    
    .kbd {
      font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace;
      background: rgb(241, 245, 249);
      border: 1px solid rgb(226, 232, 240);
      border-radius: 6px;
      padding: 0.2rem 0.4rem;
      font-size: 0.75rem;
      color: #374151 !important;
    }
    
    .kbd-short {
      max-width: 80px;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
      display: inline-block;
      vertical-align: middle;
    }
    
    .pill {
      padding: 0.25rem 0.75rem;
      border-radius: 9999px;
      font-size: 0.7rem;
      font-weight: 600;
      background: rgb(241, 245, 249);
      border: 1px solid rgb(226, 232, 240);
      color: #374151 !important;
    }
    
    .tab-btn {
      padding: 0.75rem 1.5rem;
      border-radius: 10px;
      font-weight: 600;
      transition: all 0.2s ease;
      position: relative;
      overflow: hidden;
      color: #64748b;
    }
    
    .tab-btn.active {
      background: rgba(14, 165, 233, 0.1);
      color: rgb(14, 165, 233);
    }
    
    .tab-btn:not(.active):hover {
      background: rgba(100, 116, 139, 0.05);
    }
    
    .muted {
      color: rgb(100, 116, 139);
    }
    
    .grid-2 {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 1rem;
    }
    
    .grid-3 {
      display: grid;
      grid-template-columns: 1fr 1fr 1fr;
      gap: 1rem;
    }
    
    .grid-aside {
      display: grid;
      grid-template-columns: 380px 1fr;
      gap: 1.5rem;
    }
    
    @media (max-width: 1024px) {
      .grid-aside {
        grid-template-columns: 1fr;
      }
    }
    
    .list {
      max-height: 420px;
      overflow: auto;
    }
    
    .json-invalid {
      border-color: rgb(239, 68, 68) !important;
      background: #fef2f2;
    }
    
    .hint {
      font-size: 0.75rem;
      color: rgb(100, 116, 139);
    }
    
    .header-gradient {
      background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
      color: white;
      position: relative;
      overflow: hidden;
    }
    
    .header-gradient::before {
      content: '';
      position: absolute;
      top: 0;
      left: 0;
      right: 0;
      bottom: 0;
      background: url("data:image/svg+xml,%3Csvg width='60' height='60' viewBox='0 0 60 60' xmlns='http://www.w3.org/2000/svg'%3E%3Cg fill='none' fill-rule='evenodd'%3E%3Cg fill='%23ffffff' fill-opacity='0.05'%3E%3Cpath d='M36 34v-4h-2v4h-4v2h4v4h2v-4h4v-2h-4zm0-30V0h-2v4h-4v2h4v4h2V6h4V4h-4zM6 34v-4H4v4H0v2h4v4h2v-4h4v-2H6zM6 4V0H4v4H0v2h4v4h2V6h4V4H6z'/%3E%3C/g%3E%3C/g%3E%3C/svg%3E");
    }
    
    .kpi-card {
      background: rgba(255, 255, 255, 0.95);
      backdrop-filter: blur(10px);
      border-radius: 12px;
      padding: 1.25rem;
      border: 1px solid rgba(255, 255, 255, 0.5);
      transition: all 0.3s ease;
    }
    
    .kpi-card:hover {
      transform: translateY(-3px);
      box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.1);
    }
    
    .kpi-card,
    .kpi-card *:not(i):not(input) {
      color: #1e293b !important;
    }
    
    .kpi-card .text-slate-600 {
      color: #475569 !important;
    }
    
    .status-indicator {
      width: 8px;
      height: 8px;
      border-radius: 50%;
      display: inline-block;
      margin-right: 6px;
    }
    
    .status-active {
      background: #10b981;
      box-shadow: 0 0 0 2px rgba(16, 185, 129, 0.2);
    }
    
    .fade-in {
      animation: fadeIn 0.5s ease-in-out;
    }
    
    .slide-up {
      animation: slideUp 0.3s ease-out;
    }
    
    ::-webkit-scrollbar {
      width: 6px;
    }
    
    ::-webkit-scrollbar-track {
      background: #f1f5f9;
      border-radius: 10px;
    }
    
    ::-webkit-scrollbar-thumb {
      background: #cbd5e1;
      border-radius: 10px;
    }
    
    ::-webkit-scrollbar-thumb:hover {
      background: #94a3b8;
    }
    
    .loading-pulse {
      animation: pulseSoft 2s infinite;
    }
    
    .header-content h1,
    .header-content p,
    .header-content label {
      color: white !important;
      text-shadow: 0 1px 3px rgba(0, 0, 0, 0.3);
    }
    
    .glass .input {
      color: #1e293b !important;
    }
    
    .glass .btn {
      color: #1e293b !important;
    }
    
    .header-gradient,
    .header-gradient .header-text,
    .header-gradient label {
      color: white !important;
    }
    
    .header-gradient .text-slate-400 {
      color: rgba(255, 255, 255, 0.7) !important;
    }
    
    .header-gradient .placeholder-slate-500::placeholder {
      color: rgba(255, 255, 255, 0.6) !important;
    }
    
    /* Dashboard specific styles */
    .link { stroke: #9ca3af; stroke-opacity: 0.6; }
    .badge { padding: 2px 8px; border-radius: 6px; font-size: 0.75rem; font-weight: 500; display: inline-flex; align-items: center; gap: 6px; }
    .chip { width: 10px; height: 10px; border-radius: 9999px; display: inline-block; border: 1px solid rgba(0,0,0,.08); }
    .kv { display: grid; grid-template-columns: 1fr auto; gap: .25rem .75rem; font-variant-numeric: tabular-nums; }
  </style>
</head>
<body class="bg-slate-50 text-slate-900">
  <div class="max-w-7xl mx-auto p-4 md:p-8">
    <!-- Header with gradient -->
    <header class="header-gradient rounded-2xl p-6 md:p-8 mb-6 relative overflow-hidden fade-in">
      <div class="relative z-10">
        <div class="flex flex-col md:flex-row md:items-center md:justify-between gap-4">
          <div class="header-content">
            <div class="flex items-center gap-3 mb-2">
              <div class="w-10 h-10 rounded-xl bg-white/20 flex items-center justify-center">
                <i class="fas fa-chart-network text-white text-lg"></i>
              </div>
              <h1 class="text-3xl font-bold text-white">AuthBridge Trust Dashboard</h1>
            </div>
            <p class="opacity-95 text-sm text-white">Visualize real-time trust relationships between services across workspaces.</p>
          </div>
          <div class="glass rounded-xl p-4 flex flex-col md:flex-row items-center gap-3">
            <div class="relative flex-1">
              <i class="fas fa-key absolute left-3 top-1/2 transform -translate-y-1/2 text-slate-400"></i>
              <input id="apiKeyInput" type="password" placeholder="Paste AUTHBRIDGE admin key"
                     class="input !pl-10 !w-full md:!w-72 placeholder-slate-500 text-slate-900"
                     autocomplete="off">
            </div>
            <button id="saveKeyBtn" class="btn bg-white hover:bg-slate-100 text-slate-800 border border-slate-200 w-full md:w-auto">
              <i class="fas fa-sign-in-alt"></i> Sign in
            </button>
            <label class="flex items-center gap-2 text-sm text-white">
              <input id="autoRefreshChk" type="checkbox" class="w-4 h-4 accent-white" checked>
              Auto refresh (60s)
            </label>
            <button id="refreshBtn" class="btn bg-white/80 hover:bg-white text-slate-800 border border-white/30">
              <i class="fas fa-sync-alt"></i> Refresh
            </button>
          </div>
        </div>

        <!-- KPIs row -->
        <div class="mt-6 grid grid-cols-2 md:grid-cols-6 gap-4">
          <div class="kpi-card">
            <div class="flex items-center justify-between">
              <div class="text-sm font-medium text-slate-600">Services</div>
              <i class="fas fa-cube text-primary-400"></i>
            </div>
            <div id="svcCount" class="text-2xl font-bold mt-2 text-slate-800">–</div>
          </div>
          <div class="kpi-card">
            <div class="flex items-center justify-between">
              <div class="text-sm font-medium text-slate-600">Workspaces</div>
              <i class="fas fa-layer-group text-primary-400"></i>
            </div>
            <div id="wsCount" class="text-2xl font-bold mt-2 text-slate-800">–</div>
          </div>
          <div class="kpi-card">
            <div class="flex items-center justify-between">
              <div class="text-sm font-medium text-slate-600">Links</div>
              <i class="fas fa-link text-primary-400"></i>
            </div>
            <div id="linkCount" class="text-2xl font-bold mt-2 text-slate-800">–</div>
          </div>
          <div class="kpi-card">
            <div class="flex items-center justify-between">
              <div class="text-sm font-medium text-slate-600">Redis</div>
              <i class="fas fa-database text-primary-400"></i>
            </div>
            <div id="redisState" class="text-2xl font-bold mt-2 text-slate-800">–</div>
            <div class="mt-2 text-xs text-slate-600 kv">
              <span>Clients</span><span id="redisClients">–</span>
              <span>Memory</span><span id="redisMem">–</span>
              <span>Uptime</span><span id="redisUptime">–</span>
            </div>
          </div>
          <div class="kpi-card">
            <div class="flex items-center justify-between">
              <div class="text-sm font-medium text-slate-600">JWKS Keys</div>
              <i class="fas fa-key text-primary-400"></i>
            </div>
            <div id="jwksCount" class="text-2xl font-bold mt-2 text-slate-800">–</div>
            <div class="mt-2 text-xs text-slate-600">Current KID: <span id="kid">–</span></div>
          </div>
          <div class="kpi-card">
            <div class="flex items-center justify-between">
              <div class="text-sm font-medium text-slate-600">Last update</div>
              <i class="fas fa-clock text-primary-400"></i>
            </div>
            <div id="lastUpdate" class="text-xl font-bold mt-2 text-slate-800">–</div>
          </div>
        </div>
      </div>
    </header>

    <section class="mt-6 grid grid-cols-1 md:grid-cols-3 gap-4 slide-up">
      <div class="md:col-span-2 p-5 card">
        <div class="flex items-center justify-between mb-4">
          <h2 class="font-bold text-lg flex items-center gap-2">
            <i class="fas fa-project-diagram text-primary-500"></i> Trust Graph
          </h2>
          <div class="text-xs text-slate-500">Drag nodes, hover for details. Click a link to inspect.</div>
        </div>
        <svg id="graph" class="w-full bg-slate-50 rounded-xl border border-slate-200" style="height: 560px"></svg>
      </div>
      <div class="p-5 card">
        <h2 class="font-bold text-lg mb-4 flex items-center gap-2">
          <i class="fas fa-filter text-primary-500"></i> Legend & Filters
        </h2>
        <div id="legend" class="flex flex-wrap gap-2 mb-4"></div>

        <div class="mb-4">
          <label class="label">Workspace filter</label>
          <select id="wsFilter" class="select">
            <option value="">All workspaces</option>
          </select>
        </div>
        <div class="mb-4">
          <label class="label">Search service</label>
          <input id="searchInput" placeholder="Type to highlight…" class="input"/>
        </div>

        <div class="mt-6 border-t pt-4">
          <h3 class="font-semibold text-sm mb-2 flex items-center gap-2">
            <i class="fas fa-chart-pie text-primary-500"></i> Service types
          </h3>
          <div id="typeDist" class="text-xs text-slate-700 grid grid-cols-2 gap-1"></div>
        </div>

        <div class="mt-6 border-t pt-4">
          <label class="flex items-center gap-2 text-sm text-slate-700">
            <input id="promToggle" type="checkbox" class="w-4 h-4 accent-indigo-600">
            Show Prometheus snapshot
          </label>
          <div id="promBox" class="hidden mt-3 text-xs bg-slate-50 rounded border border-slate-200 p-3">
            <div class="flex items-center justify-between">
              <strong>Metrics</strong>
              <button id="promRefresh" class="btn bg-slate-200 hover:bg-slate-300 text-slate-800 text-xs">Reload</button>
            </div>
            <div id="prometrics" class="mt-2 font-mono whitespace-pre-wrap leading-5">—</div>
          </div>
        </div>

        <div class="mt-6 border-t pt-4">
          <h3 class="font-semibold text-sm mb-2 flex items-center gap-2">
            <i class="fas fa-search text-primary-500"></i> Link inspector
          </h3>
          <div id="linkInspector" class="text-xs text-slate-700 bg-slate-50 rounded border border-slate-200 p-3">
            Click an edge to see details…
          </div>
        </div>
      </div>
    </section>

    <section class="mt-6 p-5 card slide-up">
      <div class="flex items-center justify-between mb-4">
        <h2 class="font-bold text-lg flex items-center gap-2">
          <i class="fas fa-list-alt text-primary-500"></i> Activity
        </h2>
        <span id="activityInfo" class="text-xs text-slate-500"></span>
      </div>
      <pre id="activityLog" class="text-xs bg-slate-50 p-3 rounded-lg border border-slate-200 max-h-56 overflow-auto">Waiting for data…</pre>
    </section>

    <footer class="mt-8 text-center text-xs text-slate-500">
      <div class="flex items-center justify-center gap-2 mb-2">
        <i class="fas fa-eye text-primary-500"></i>
        <span>Built for non-technical stakeholders • Uses your admin API key in-browser</span>
      </div>
    </footer>
  </div>

  <!-- Load D3 just before our script to ensure availability -->
  <script src="https://cdn.jsdelivr.net/npm/d3@7/dist/d3.min.js"></script>

<script>
(function(){
  // =========================
  // CONFIG & STATE
  // =========================
  const KEY_STORAGE = "authbridge_admin_key";
  const LOG_MAX = 300;                 // Cap activity entries → avoids infinite growth
  const AUTO_REFRESH_MS = 60000;       // 60s

  const apiKeyInput = document.getElementById("apiKeyInput");
  const saveKeyBtn = document.getElementById("saveKeyBtn");
  const wsFilter = document.getElementById("wsFilter");
  const searchInput = document.getElementById("searchInput");
  const legendBox = document.getElementById("legend");
  const logEl = document.getElementById("activityLog");
  const logInfoEl = document.getElementById("activityInfo");
  const autoRefreshChk = document.getElementById("autoRefreshChk");
  const refreshBtn = document.getElementById("refreshBtn");
  const promToggle = document.getElementById("promToggle");
  const promBox = document.getElementById("promBox");
  const promRefresh = document.getElementById("promRefresh");
  const prometrics = document.getElementById("prometrics");
  const typeDist = document.getElementById("typeDist");
  const linkInspector = document.getElementById("linkInspector");

  // Metrics labels
  const svcCount = document.getElementById("svcCount");
  const wsCount = document.getElementById("wsCount");
  const linkCount = document.getElementById("linkCount");
  const redisState = document.getElementById("redisState");
  const redisClients = document.getElementById("redisClients");
  const redisMem = document.getElementById("redisMem");
  const redisUptime = document.getElementById("redisUptime");
  const jwksCount = document.getElementById("jwksCount");
  const kid = document.getElementById("kid");
  const lastUpdate = document.getElementById("lastUpdate");

  // Single source of truth for colors
  const TYPE_COLORS = {
    "reflection": "#38bdf8",
    "supertable": "#34d399",
    "mirage":     "#c4b5fd",
    "ai":         "#fca5a5",
    "bi":         "#fcd34d",
    "email_api":  "#f5d0fe",
    "unknown":    "#e5e7eb"
  };

  let logs = [];
  function log(msg) {
    const ts = new Date().toISOString();
    logs.unshift(`[${ts}] ${msg}`);
    if (logs.length > LOG_MAX) logs = logs.slice(0, LOG_MAX);
    logEl.textContent = logs.join("\\n");
    logInfoEl.textContent = `Showing last ${logs.length} events (max ${LOG_MAX})`;
  }

  function typeColor(t){
    return TYPE_COLORS[String(t || "unknown").toLowerCase()] || TYPE_COLORS["unknown"];
  }

  // =========================
  // AUTH KEY PERSISTENCE (login/logout UX)
  // =========================
  function setSignedIn(on){
    if (on){
      apiKeyInput.disabled = true;
      apiKeyInput.classList.add("opacity-80", "cursor-not-allowed");
      saveKeyBtn.innerHTML = '<i class="fas fa-sign-out-alt"></i> Logout';
      saveKeyBtn.onclick = () => {
        localStorage.removeItem(KEY_STORAGE);
        apiKeyInput.value = "";
        apiKeyInput.disabled = false;
        apiKeyInput.classList.remove("opacity-80", "cursor-not-allowed");
        saveKeyBtn.innerHTML = '<i class="fas fa-sign-in-alt"></i> Sign in';
        saveKeyBtn.onclick = doSignIn;

        // Stop polling and clear some UI.
        stopLoop();
        svcCount.textContent = "–";
        wsCount.textContent = "–";
        linkCount.textContent = "–";
        redisState.textContent = "–";
        redisClients.textContent = "–";
        redisMem.textContent = "–";
        redisUptime.textContent = "–";
        jwksCount.textContent = "–";
        kid.textContent = "–";
        lastUpdate.textContent = "–";
        legendBox.replaceChildren();
        typeDist.replaceChildren();
        linkInspector.textContent = "Signed out.";
        d3.select("#graph").selectAll("*").remove();
        log("Signed out.");
      };
      return;
    }

    apiKeyInput.disabled = false;
    apiKeyInput.classList.remove("opacity-80", "cursor-not-allowed");
    saveKeyBtn.innerHTML = '<i class="fas fa-sign-in-alt"></i> Sign in';
    saveKeyBtn.onclick = doSignIn;
  }

  function doSignIn(){
    const k = apiKeyInput.value.trim();
    if (!k) { alert("Please paste an AUTHBRIDGE admin key."); return; }
    localStorage.setItem(KEY_STORAGE, k);
    setSignedIn(true);
    log("Admin key saved. Fetching data…");
    fetchAndRender(true);
  }

  const saved = localStorage.getItem(KEY_STORAGE);
  if (saved) {
    apiKeyInput.value = saved;
    setSignedIn(true);
    log("Admin key loaded from local storage.");
  } else {
    setSignedIn(false);
  }


  // Manual refresh
  refreshBtn.addEventListener("click", () => {
    const k = localStorage.getItem(KEY_STORAGE);
    if (!k) { alert("Please sign in with an AUTHBRIDGE admin key first."); return; }
    log("Manual refresh triggered.");
    fetchAndRender(false);
  });

  // Auto-refresh loop
  let timer = null;
  function startLoop(){
    stopLoop();
    if (!autoRefreshChk.checked) return;
    timer = setInterval(fetchAndRender, AUTO_REFRESH_MS);
  }
  function stopLoop(){
    if (timer) {
      clearInterval(timer);
      timer = null;
    }
  }
  autoRefreshChk.addEventListener("change", () => {
    if (autoRefreshChk.checked) {
      log("Auto refresh enabled (60s).");
      startLoop();
    } else {
      log("Auto refresh disabled.");
      stopLoop();
    }
  });

  // =========================
  // DATA FETCH & RENDER
  // =========================
  let cache = { services: [], workspaces: [], links: [], system: {}, redis: "unknown", now: null };

  function fetchAndRender(first=false){
    const key = localStorage.getItem(KEY_STORAGE);
    if (!key) return;
    fetch("/dashboard/data", { headers: {"x-api-key": key} })
      .then(r => {
        if (!r.ok) throw new Error("HTTP " + r.status);
        return r.json();
      })
      .then(d => {
        cache = d;
        // Topline metrics
        svcCount.textContent = d.services.length;
        wsCount.textContent = d.workspaces.length;
        linkCount.textContent = d.links.length;
        redisState.textContent = d.redis;
        redisClients.textContent = d.redis_info.clients ?? "–";
        redisMem.textContent = d.redis_info.memory ?? "–";
        redisUptime.textContent = d.redis_info.uptime ?? "–";
        jwksCount.textContent = d.jwks.count;
        kid.textContent = d.jwks.current_kid || "–";
        lastUpdate.textContent = new Date(d.now).toLocaleTimeString();

        // Legend, filters, distribution
        buildLegend(d);
        ensureWorkspaceFilter(d);
        buildTypeDistribution(d);

        // Graph
        renderGraph(d);

        if (first) startLoop();
      })
      .catch(err => {
        log("Fetch failed: " + err.message + " (check admin key or network)");
      });
  }

  function buildLegend(d){
    legendBox.replaceChildren();
    const types = Array.from(new Set(d.services.map(s => s.type || "unknown"))).sort();
    types.forEach(t => {
      const span = document.createElement("span");
      span.className = "badge bg-slate-100";
      const chip = document.createElement("span");
      chip.className = "chip";
      chip.style.background = typeColor(t);
      const label = document.createElement("span");
      label.textContent = t || "unknown";
      span.appendChild(chip);
      span.appendChild(label);
      legendBox.appendChild(span);
    });
  }

  function ensureWorkspaceFilter(d){
    const existing = new Set(Array.from(wsFilter.options).slice(1).map(o => o.value));
    const incoming = new Set(d.workspaces.map(w => w.id));
    let same = existing.size === incoming.size && [...existing].every(v => incoming.has(v));
    if (same) return;

    wsFilter.replaceChildren();
    const all = document.createElement("option");
    all.value = "";
    all.textContent = "All workspaces";
    wsFilter.appendChild(all);

    const opts = d.workspaces.map(w => ({id:w.id, name:w.name})).sort((a,b)=>a.name.localeCompare(b.name));
    for (const w of opts) {
      const o = document.createElement("option");
      o.value = w.id; o.textContent = w.name + " ("+w.id+")";
      wsFilter.appendChild(o);
    }
  }

  function buildTypeDistribution(d){
    typeDist.replaceChildren();
    const counts = d.type_counts || {};
    const items = Object.keys(counts).sort();
    items.forEach(t => {
      const row = document.createElement("div");
      row.className = "flex items-center justify-between";
      const left = document.createElement("div");
      left.className = "flex items-center gap-2";
      const chip = document.createElement("span");
      chip.className = "chip";
      chip.style.background = typeColor(t);
      const label = document.createElement("span");
      label.textContent = t;
      const right = document.createElement("span");
      right.textContent = counts[t];
      left.appendChild(chip);
      left.appendChild(label);
      row.appendChild(left);
      row.appendChild(right);
      typeDist.appendChild(row);
    });
  }

  wsFilter.addEventListener("change", ()=>renderGraph(cache));
  searchInput.addEventListener("input", ()=>renderGraph(cache));

  function renderGraph(d){
    if (typeof window.d3 === "undefined") {
      log("Render skipped: d3 is not loaded.");
      return;
    }

    const workspaceId = wsFilter.value;
    const query = (searchInput.value || "").trim().toLowerCase();

    const services = new Map(d.services.map(s => [s.id, s]));
    const filteredLinks = d.links.filter(L => !workspaceId || L.workspace_id === workspaceId);

    const nodeIds = new Set();
    filteredLinks.forEach(L => { nodeIds.add(L.issuer_id); nodeIds.add(L.audience_id); });

    const nodes = [...nodeIds].map(id => {
      const svc = services.get(id) || {id, name:id, type:"unknown"};
      const name = String(svc.name || svc.id);
      const type = String(svc.type || "unknown").toLowerCase();
      return {
        id,
        name,
        type,
        color: typeColor(type),
        highlight: query && (String(svc.id).toLowerCase().includes(query) || name.toLowerCase().includes(query))
      };
    });

    const links = filteredLinks.map(L => ({
      source: L.issuer_id,
      target: L.audience_id,
      workspace_id: L.workspace_id,
      context: L.context || {}
    }));

    const svg = d3.select("#graph");
    svg.selectAll("*").remove();
    const width = svg.node().clientWidth || 800;
    const height = svg.node().clientHeight || 560;

    const simulation = d3.forceSimulation(nodes)
      .force("link", d3.forceLink(links).id(d=>d.id).distance(120).strength(0.6))
      .force("charge", d3.forceManyBody().strength(-300))
      .force("center", d3.forceCenter(width/2, height/2))
      .force("collision", d3.forceCollide().radius(46));

    const link = svg.append("g").attr("stroke-width", 1.2).selectAll("line")
      .data(links)
      .enter().append("line")
      .attr("class", "link")
      .on("click", (_, L) => inspectLink(L));

    const gNode = svg.append("g").selectAll("g")
      .data(nodes)
      .enter().append("g")
      .call(d3.drag()
        .on("start", (event,d)=>{ if(!event.active) simulation.alphaTarget(0.3).restart(); d.fx=d.x; d.fy=d.y; })
        .on("drag", (event,d)=>{ d.fx=event.x; d.fy=event.y; })
        .on("end", (event,d)=>{ if(!event.active) simulation.alphaTarget(0); d.fx=null; d.fy=null; })
      );

    gNode.append("circle")
      .attr("r", d => d.highlight ? 18 : 12)
      .attr("fill", d => d.color)
      .attr("stroke", d => d.highlight ? "#111827" : "#ffffff")
      .attr("stroke-width", d => d.highlight ? 2 : 1.5);

    gNode.append("text")
      .attr("x", 16)
      .attr("y", 4)
      .attr("font-size", "11px")
      .text(d => d.name);

    gNode.append("title").text(d => `${d.name}\\n(${d.id})\\nType: ${d.type}`);

    simulation.on("tick", ()=>{
      link
        .attr("x1", d=>d.source.x).attr("y1", d=>d.source.y)
        .attr("x2", d=>d.target.x).attr("y2", d=>d.target.y);
      gNode.attr("transform", d => `translate(${d.x},${d.y})`);
    });
  }

  function inspectLink(L){
    const html = [
      "<div class='kv'>",
      "<span><strong>Issuer</strong></span><span>"+L.source+"</span>",
      "<span><strong>Audience</strong></span><span>"+L.target+"</span>",
      "<span><strong>Workspace</strong></span><span>"+(L.workspace_id||"")+"</span>",
      "</div>",
      "<div class='mt-2'><strong>Context</strong></div>",
      "<pre class='mt-1 text-xs bg-slate-100 p-2 rounded'>" + JSON.stringify(L.context, null, 2) + "</pre>"
    ].join("");
    linkInspector.innerHTML = html;
  }

  // =========================
  // PROMETHEUS
  // =========================
  promToggle.addEventListener("change", ()=>{
    promBox.classList.toggle("hidden", !promToggle.checked);
    if (promToggle.checked) loadProm();
  });
  promRefresh.addEventListener("click", loadProm);
  function loadProm(){
    const key = localStorage.getItem(KEY_STORAGE);
    if (!key) return;
    fetch("/dashboard/prometheus", { headers: {"x-api-key": key} })
      .then(r => r.ok ? r.text() : Promise.reject("HTTP " + r.status))
      .then(t => prometrics.textContent = t)
      .catch(e => prometrics.textContent = "Error: " + e);
  }

  // =========================
  // INIT
  // =========================
  log("Dashboard initialized. Please sign in with your admin key.");
  if (localStorage.getItem(KEY_STORAGE)) fetchAndRender(true);
})();
</script>
</body>
</html>
"""


@router.get("/dashboard", response_class=HTMLResponse, include_in_schema=False)
async def dashboard_page() -> HTMLResponse:
    """
    Serves the single-page Admin Dashboard.
    Authentication is done client-side by passing `x-api-key` in requests to /dashboard/data.
    """
    return HTMLResponse(DASHBOARD_HTML)


@router.get("/dashboard/data", response_class=JSONResponse, include_in_schema=False)
async def dashboard_data(_: str = Depends(validate_authbridge_api_key)) -> JSONResponse:
    """
    Returns a real-time snapshot of services, workspaces, trust links, JWKS stats,
    and lightweight Redis info. Requires an admin key via `x-api-key`.
    """
    # Ensure latest caches
    await reload_services()
    await reload_workspaces()

    # Shape services
    services: List[Dict[str, Any]] = []
    type_counts: Dict[str, int] = {}
    for s in caches.services.values():
        stype = (s.type or "unknown")
        type_counts[stype] = type_counts.get(stype, 0) + 1
        services.append({
            "id": s.id,
            "name": s.name,
            "type": stype,
            "version": s.version,
            "info": s.info or {},
        })

    # Shape workspaces & links
    workspaces: List[Dict[str, Any]] = []
    links: List[Dict[str, Any]] = []
    for w in caches.workspaces.values():
        workspaces.append({
            "id": w.id,
            "name": w.name,
            "version": w.version,
            "info": w.info or {},
        })
        for link in (w.services or []):
            if isinstance(link, ServiceLink):
                links.append({
                    "workspace_id": w.id,
                    "issuer_id": link.issuer_id,
                    "audience_id": link.audience_id,
                    "context": link.context or {},
                })

    # Redis info (lightweight)
    rm = RedisManager()
    redis_ok = await rm.is_available()
    info_clients: Optional[int] = None
    info_mem: Optional[str] = None
    info_uptime: Optional[str] = None
    try:
        if redis_ok:
            info = await rm.redis.info(section="all")  # returns dict
            info_clients = int(info.get("connected_clients", 0))
            info_mem = info.get("used_memory_human") or f'{int(info.get("used_memory", 0))//1024} KiB'
            uptime_sec = int(info.get("uptime_in_seconds", 0))
            # Pretty uptime
            days, rem = divmod(uptime_sec, 86400)
            hours, rem = divmod(rem, 3600)
            minutes, _ = divmod(rem, 60)
            info_uptime = f"{days}d {hours}h {minutes}m"
    except Exception as exc:
        log.warning("Redis INFO failed: %s", exc)

    # JWKS stats (from token router globals)
    jwks = {
        "count": len(RSA_KEYS),
        "current_kid": CURRENT_KID,
    }

    payload = {
        "now": datetime.now(timezone.utc).isoformat(),
        "redis": "ok" if redis_ok else "down",
        "redis_info": {
            "clients": info_clients,
            "memory": info_mem,
            "uptime": info_uptime,
        },
        "jwks": jwks,
        "system": {
            "services_version": caches.service_sys_ver,
            "workspaces_version": caches.workspace_sys_ver,
        },
        "type_counts": dict(sorted(type_counts.items(), key=lambda kv: kv[0])),
        "services": sorted(services, key=lambda x: (str(x["type"]).lower(), str(x["name"]).lower())),
        "workspaces": sorted(workspaces, key=lambda x: str(x["name"]).lower()),
        "links": links,
    }
    return JSONResponse(payload)


# Optional helper endpoint to verify Prometheus availability from the app itself.
@router.get("/dashboard/metrics-ready", response_class=PlainTextResponse, include_in_schema=False)
async def metrics_ready() -> PlainTextResponse:
    """
    Returns 'ok' to indicate the dashboard is mounted; real metrics are read from GET /metrics.
    """
    return PlainTextResponse("ok")
