# app/routers/admin.py
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List

from fastapi import APIRouter, Depends
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse

from app.core.logging import get_logger
from app.core.redis import caches
from app.core.security import validate_authbridge_api_key
from app.models import ServiceLink
from app.routers.service import reload_services
from app.routers.workspace import reload_workspaces
from app.core.types_loader import load_service_types

log = get_logger("auth-bridge.admin")

router = APIRouter(tags=["admin"])

# Visuals kept as-is from the user's version.
# Minimal functional fixes:
#  - Guard against missing panel nodes in tab activation (prevents JS crash -> tabs dead).
#  - Fix template strings that accidentally escaped ${...} so IDs render correctly.
#  - Ensure initial data load runs safely and errors don't break the UI.
#  - Keep API calls and behaviors identical to the user's last working semantics.
ADMIN_HTML = """
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width,initial-scale=1"/>
  <title>AuthBridge • Admin Console</title>
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
            }
          },
          animation: {
            'fade-in': 'fadeIn 0.5s ease-in-out',
            'slide-up': 'slideUp 0.3s ease-out',
          },
          keyframes: {
            fadeIn: { '0%': { opacity: '0' }, '100%': { opacity: '1' } },
            slideUp: { '0%': { transform: 'translateY(10px)', opacity: '0' }, '100%': { transform: 'translateY(0)', opacity: '1' } }
          }
        }
      }
    }
  </script>
  <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');
    * { font-family: 'Inter', sans-serif; }
    body { background: linear-gradient(135deg, #f5f7fa 0%, #e4edf5 100%); min-height: 100vh; }

    .glass { background: rgba(255,255,255,.75); backdrop-filter: blur(10px); border: 1px solid rgba(255,255,255,.35); }
    .card { background: white; border-radius: 16px; box-shadow: 0 10px 15px -3px rgba(0,0,0,.05), 0 4px 6px -2px rgba(0,0,0,.03); border: 1px solid rgba(226,232,240,.8); transition: all .25s ease; }
    .card:hover { transform: translateY(-2px); box-shadow: 0 20px 25px -5px rgba(0,0,0,.08), 0 10px 10px -5px rgba(0,0,0,.03); }

    .btn { padding: .6rem 1rem; border-radius: .75rem; font-weight: 600; transition: all .15s ease; display:inline-flex; align-items:center; gap:.5rem; }
    .btn:active { transform: scale(.98); }

    .log.auto-grow {
      height: auto;        /* remove fixed height */
      max-height: none;    /* let it grow freely; keep or set a cap if you want */
    }

    .input, .select, .textarea {
      width: 100%;
      padding: .75rem 1rem;
      border: 1px solid rgb(226,232,240);
      border-radius: .75rem;
      background: white;
      transition: all .2s ease;
      box-shadow: 0 1px 2px rgba(0,0,0,.03);
    }
    .input:focus, .select:focus, .textarea:focus { border-color: rgb(14,165,233); box-shadow: 0 0 0 3px rgba(14,165,233,.12); outline: none; }

    .label { font-size: .8rem; font-weight: 600; color: rgb(71,85,105); margin-bottom: .5rem; display:block; }
    .small { font-size: .75rem; color: rgb(100,116,139); }
    .pill { padding: .25rem .6rem; border-radius: 9999px; font-size: .7rem; font-weight: 600; background: rgb(241,245,249); border:1px solid rgb(226,232,240); color:#334155; }
    .log { font-size: .75rem; color:#0f172a; background:#f8fafc; border:1px solid #e2e8f0; border-radius: .75rem; padding:.6rem; white-space:pre-wrap; height:160px; overflow:auto; }
    .json-invalid { border-color: rgb(239, 68, 68) !important; background: #fef2f2; }

    .tab { padding: .7rem 1.2rem; border-radius: .75rem; font-weight: 600; transition: all .15s ease; color:#64748b; border:1px solid rgba(226,232,240, .9); background:white; }
    .tab.active { background: rgba(14,165,233,.1); color: rgb(14,165,233); border-color: rgba(14,165,233,.25); }
    .panel { display:none; }
    .panel.active { display:block; }

    .list { max-height: 420px; overflow:auto; border:1px solid #e2e8f0; border-radius: .75rem; }
    .item { display:flex; justify-content:space-between; gap:.75rem; padding:.65rem .8rem; border-bottom:1px solid #f1f5f9; }
    .item:last-child { border-bottom:none; }

    .grid-2 { display:grid; grid-template-columns: 1fr 1fr; gap: 1rem; }
    .grid-3 { display:grid; grid-template-columns: 1fr 1fr 1fr; gap: 1rem; }
    .grid-aside { display:grid; grid-template-columns: 380px 1fr; gap: 1.25rem; }
    @media (max-width: 1024px){ .grid-aside { grid-template-columns: 1fr; } }
  </style>
</head>
<body class="bg-slate-50 text-slate-900">
  <div class="max-w-7xl mx-auto p-4 md:p-8">
    <!-- Header -->
    <header class="rounded-2xl p-6 md:p-8 mb-6 relative overflow-hidden animate-fade-in"
             style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white;">
      <div class="relative z-10">
        <div class="flex flex-col md:flex-row md:items-center md:justify-between gap-4">
          <div>
            <div class="flex items-center gap-3 mb-2">
              <div class="w-10 h-10 rounded-xl bg-white/20 flex items-center justify-center">
                <i class="fas fa-toolbox text-white text-lg"></i>
              </div>
              <h1 class="text-3xl font-bold text-white">AuthBridge Admin Console</h1>
            </div>
            <p class="opacity-95 text-sm text-white">Manage services, workspaces, trust links and system operations.</p>
          </div>
          <div class="glass rounded-xl p-4 flex flex-col md:flex-row items-center gap-3">
            <div class="relative flex-1">
              <i class="fas fa-key absolute left-3 top-1/2 -translate-y-1/2 text-slate-400"></i>
              <input id="apiKeyInput" type="password" placeholder="Paste AUTHBRIDGE admin key"
                     class="input !pl-10 !w-full md:!w-72 placeholder-slate-500 text-slate-900"
                     autocomplete="off">
            </div>
            <button id="saveKeyBtn" class="btn bg-white hover:bg-slate-100 text-slate-800 border border-slate-200">
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
      </div>
    </header>

    <!-- Tabs -->
    <div class="flex gap-2 mb-4">
      <button class="tab active" data-tab="workspaces"><i class="fas fa-layer-group"></i> <span class="ml-1">Workspaces</span></button>
      <button class="tab" data-tab="services"><i class="fas fa-cube"></i> <span class="ml-1">Services</span></button>
      <button class="tab" data-tab="links"><i class="fas fa-link"></i> <span class="ml-1">Link Services</span></button>
      <button class="tab" data-tab="system"><i class="fas fa-cog"></i> <span class="ml-1">System</span></button>
    </div>

    <!-- Workspaces -->
    <section id="panel-workspaces" class="panel active animate-slide-up">
      <div class="grid-aside">
        <div class="card p-5">
          <div class="flex items-center justify-between mb-3">
            <strong class="text-slate-800 flex items-center gap-2"><i class="fas fa-layer-group text-primary-500"></i> Workspaces</strong>
            <span class="pill">ver <span id="wsVer">—</span></span>
          </div>
          <input id="wsSearch" class="input" placeholder="Filter by name/id…">
          <div id="wsList" class="list mt-3"></div>
        </div>

        <div class="card p-5">
          <div class="flex items-center justify-between mb-3">
            <strong class="text-slate-800 flex items-center gap-2"><i class="fas fa-pen-to-square text-primary-500"></i> Workspace Editor</strong>
            <div class="small">Selected: <span id="wsSel">—</span></div>
          </div>
          <div class="grid-2">
            <div>
              <label class="label">Workspace ID</label>
              <input id="wsId" class="input read-only:border-slate-200 read-only:bg-slate-50 read-only:cursor-not-allowed" placeholder="workspace-xyz">
            </div>
            <div>
              <label class="label">Name</label>
              <input id="wsName" class="input read-only:border-slate-200 read-only:bg-slate-50 read-only:cursor-not-allowed" placeholder="My Workspace">
            </div>
          </div>
         <div class="grid-3 mt-3">
  <div class="col-span-3 grid grid-cols-1 md:grid-cols-2 gap-4">
    <div>
      <label class="label">Info JSON</label>
      <textarea id="wsInfo" class="textarea min-h-[28rem] md:min-h-[22rem]" data-json placeholder='{"owner":"team-1"}'></textarea>
      <div id="wsInfoHint" class="small mt-1">JSON • valid</div>
    </div>
    <div>
      <label class="label">Content JSON</label>
      <textarea id="wsContent" class="textarea min-h-[28rem] md:min-h-[22rem]" data-json placeholder="encrypted at rest"></textarea>
      <div id="wsContentHint" class="small mt-1">JSON • valid</div>
    </div>
  </div>
</div>

          <div class="flex flex-wrap gap-2 mt-3">
            <button id="wsCreateBtn" class="btn bg-emerald-500 hover:bg-emerald-600 text-white"><i class="fas fa-plus"></i> Create</button>
            <button id="wsDeleteBtn" class="btn bg-rose-500 hover:bg-rose-600 text-white"><i class="fas fa-trash"></i> Delete</button>
            <button id="wsRekeyBtn" class="btn bg-slate-200 hover:bg-slate-300 text-slate-800"><i class="fas fa-key"></i> Rekey</button>
            <button id="wsUpdateInfoBtn" class="btn bg-slate-200 hover:bg-slate-300 text-slate-800"><i class="fas fa-circle-info"></i> Update Info</button>
            <button id="wsUpdateContentBtn" class="btn bg-slate-200 hover:bg-slate-300 text-slate-800"><i class="fas fa-database"></i> Update Content</button>
          </div>
          <div class="label mt-3">Log</div>
          <pre id="wsLog" class="log auto-grow">—</pre>
        </div>
      </div>
    </section>

    <!-- Services -->
    <section id="panel-services" class="panel animate-slide-up">
      <div class="grid-aside">
        <div class="card p-5">
          <div class="flex items-center justify-between mb-3">
            <strong class="text-slate-800 flex items-center gap-2"><i class="fas fa-cube text-primary-500"></i> Services</strong>
            <span class="pill">ver <span id="svcVer">—</span></span>
          </div>
          <div class="grid-2">
            <input id="svcSearch" class="input" placeholder="Filter by name/id…">
            <select id="typeFilter" class="select">
              <option value="">All types</option>
            </select>
          </div>
          <div id="svcList" class="list mt-3"></div>
        </div>

        <div class="card p-5">
          <div class="flex items-center justify-between mb-3">
            <strong class="text-slate-800 flex items-center gap-2"><i class="fas fa-pen-to-square text-primary-500"></i> Service Editor</strong>
            <div class="small">Selected: <span id="svcSel">—</span></div>
          </div>
<div class="grid grid-cols-1 md:grid-cols-3 gap-4 mt-3">
  <div>
    <label class="label">Service ID</label>
    <input id="svcId" class="input" placeholder="service-abc">
  </div>
  <div>
    <label class="label">Name</label>
    <input id="svcName" class="input" placeholder="My Service">
  </div>
  <div>
    <label class="label">Type</label>
    <select id="svcType" class="select"></select>
  </div>
</div>

          <div class="grid-3 mt-3">

                  </div>
                    <div class="grid-3 mt-3">
                      <div class="col-span-3 grid grid-cols-1 md:grid-cols-2 gap-4">
                        <div>
                          <label class="label">Info JSON</label>
                          <textarea id="svcInfo" class="textarea min-h-[28rem] md:min-h-[22rem]" data-json placeholder='{"team":"core"}'></textarea>
                          <div id="svcInfoHint" class="small mt-1">JSON • valid</div>
                        </div>
                        <div>
                          <label class="label">Content JSON</label>
                          <textarea id="svcContent" class="textarea min-h-[28rem] md:min-h-[22rem]" data-json placeholder="encrypted at rest"></textarea>
                          <div id="svcContentHint" class="small mt-1">JSON • valid</div>
                        </div>
                      </div>
                    </div>

          <div class="flex flex-wrap gap-2 mt-3">
            <button id="svcCreateBtn" class="btn bg-emerald-500 hover:bg-emerald-600 text-white"><i class="fas fa-plus"></i> Create</button>
            <button id="svcDeleteBtn" class="btn bg-rose-500 hover:bg-rose-600 text-white"><i class="fas fa-trash"></i> Delete</button>
            <button id="svcRekeyBtn" class="btn bg-slate-200 hover:bg-slate-300 text-slate-800"><i class="fas fa-key"></i> Rekey</button>
            <button id="svcUpdateInfoBtn" class="btn bg-slate-200 hover:bg-slate-300 text-slate-800"><i class="fas fa-circle-info"></i> Update Info</button>
            <button id="svcUpdateContentBtn" class="btn bg-slate-200 hover:bg-slate-300 text-slate-800"><i class="fas fa-database"></i> Update Content</button>
          </div>
          <div class="label mt-3">Log</div>
          <pre id="svcLog" class="log">—</pre>
        </div>
      </div>
    </section>

<!-- Link Services -->
<section id="panel-links" class="panel animate-slide-up">
  <div class="grid-aside">
    <!-- Selected Workspace -->
    <div class="card p-5">
      <div class="flex items-center justify-between mb-3">
        <strong class="text-slate-800 flex items-center gap-2">
          <i class="fas fa-layer-group text-primary-500"></i> Selected Workspace
        </strong>
      </div>
      <div class="small">
        Selection must be made on the <b>Workspaces</b> tab.
      </div>
      <div class="flex items-center gap-2 mt-3">
        <span class="pill">Workspace: <span id="linkWsSel" class="ml-1">—</span></span>
        <button id="goToWorkspacesBtn" class="btn bg-slate-100 hover:bg-slate-200 text-slate-800">
          <i class="fas fa-arrow-right"></i> Go to Workspaces
        </button>
      </div>
    </div>

    <!-- Link Services -->
    <div class="card p-5">
      <div class="flex items-center justify-between mb-3">
        <strong class="text-slate-800 flex items-center gap-2">
          <i class="fas fa-link text-primary-500"></i> Link Services
        </strong>
      </div>

      <!-- Two-column layout -->
      <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
        <!-- Left column: issuer, audience, buttons, links -->
        <div class="space-y-4">
          <div>
            <label class="label">Issuer Service</label>
            <select id="linkIssuer" class="select"></select>
          </div>
          <div>
            <label class="label">Audience Service</label>
            <select id="linkAudience" class="select"></select>
          </div>

          <!-- Buttons -->
          <div class="flex flex-wrap gap-2">
            <button id="linkBtn" class="btn bg-primary-500 hover:bg-primary-600 text-white">
              <i class="fas fa-link"></i> Link
            </button>
            <button id="unlinkBtn" class="btn bg-rose-500 hover:bg-rose-600 text-white">
              <i class="fas fa-unlink"></i> Unlink
            </button>
          </div>

          <!-- Existing links list -->
          <div>
            <div class="label">Existing Links</div>
            <div id="linkList" class="list"></div>
          </div>
        </div>

        <!-- Right column: context JSON -->
        <div>
          <label class="label">Context (JSON)</label>
          <textarea id="linkContext" class="textarea min-h-[22rem]" data-json placeholder='{"db":"postgres://..."}'></textarea>
          <div id="linkContextHint" class="small mt-1">JSON • valid</div>
        </div>
      </div>

      <!-- Log section at bottom -->
      <div class="mt-4">
        <div class="label">Log</div>
        <pre id="linkLog" class="log">—</pre>
      </div>
    </div>
  </div>
</section>


    <!-- System -->
    <section id="panel-system" class="panel animate-slide-up">
      <div class="card p-5">
        <div class="flex items-center justify-between mb-3">
          <strong class="text-slate-800 flex items-center gap-2"><i class="fas fa-cog text-primary-500"></i> System Operations</strong>
        </div>
        <div class="flex flex-wrap gap-2">
          <button id="rotateRsaBtn" class="btn bg-primary-500 hover:bg-primary-600 text-white"><i class="fas fa-sync"></i> Rotate RSA Keys</button>
          <button id="reloadAdminBtn" class="btn bg-slate-200 hover:bg-slate-300 text-slate-800"><i class="fas fa-redo"></i> Rotate AuthBridge Admin Key</button>
          <button id="diagnosticsBtn" class="btn bg-amber-500 hover:bg-amber-600 text-white"><i class="fas fa-stethoscope"></i> Diagnostics</button>
        </div>
        <div class="label mt-3">System Log</div>
        <pre id="systemLog" class="log auto-grow">—</pre>
      </div>
    </section>

    <footer class="mt-8 text-center text-xs text-slate-500">
      <div class="flex items-center justify-center gap-2 mb-2">
        <i class="fas fa-eye text-primary-500"></i>
        <span>Client-only console • Your admin key is kept in browser storage</span>
      </div>
    </footer>
  </div>

<script>
(function(){
  // Tabs
  const tabs = document.querySelectorAll(".tab");
  const panels = {
    workspaces: document.getElementById("panel-workspaces"),
    services: document.getElementById("panel-services"),
    links: document.getElementById("panel-links"),
    system: document.getElementById("panel-system"),
  };
  function activate(name){
    tabs.forEach(t => t.classList.toggle("active", t.dataset.tab === name));
    Object.entries(panels).forEach(([k, el]) => { if (el) el.classList.toggle("active", k === name); });
  }
  tabs.forEach(t => t.addEventListener("click", ()=>activate(t.dataset.tab)));
  activate("workspaces");
  const goBtn = document.getElementById("goToWorkspacesBtn");
  if (goBtn) goBtn.addEventListener("click", ()=>activate("workspaces"));

  // Elements
  const KEY_STORAGE = "authbridge_admin_key";
  const WS_SELECTED_KEY = "authbridge_selected_workspace";
  const AUTO_REFRESH_MS = 60000;

  const apiKeyInput = document.getElementById("apiKeyInput");
  const saveKeyBtn = document.getElementById("saveKeyBtn");
  const autoRefreshChk = document.getElementById("autoRefreshChk");
  const refreshBtn = document.getElementById("refreshBtn");

  // Workspaces
  const wsSearch = document.getElementById("wsSearch");
  const wsList = document.getElementById("wsList");
  const wsVer = document.getElementById("wsVer");
  const wsSel = document.getElementById("wsSel");
  const wsId = document.getElementById("wsId");
  const wsName = document.getElementById("wsName");
  const wsInfo = document.getElementById("wsInfo");
  const wsInfoHint = document.getElementById("wsInfoHint");
  const wsContent = document.getElementById("wsContent");
  const wsContentHint = document.getElementById("wsContentHint");
  const wsCreateBtn = document.getElementById("wsCreateBtn");
  const wsDeleteBtn = document.getElementById("wsDeleteBtn");
  const wsRekeyBtn = document.getElementById("wsRekeyBtn");
  const wsUpdateInfoBtn = document.getElementById("wsUpdateInfoBtn");
  const wsUpdateContentBtn = document.getElementById("wsUpdateContentBtn");
  const wsLog = document.getElementById("wsLog");

  // Services
  const svcSearch = document.getElementById("svcSearch");
  const typeFilter = document.getElementById("typeFilter");
  const svcList = document.getElementById("svcList");
  const svcVer = document.getElementById("svcVer");
  const svcSel = document.getElementById("svcSel");
  const svcId = document.getElementById("svcId");
  const svcName = document.getElementById("svcName");
  const svcType = document.getElementById("svcType");
  const svcInfo = document.getElementById("svcInfo");
  const svcInfoHint = document.getElementById("svcInfoHint");
  const svcContent = document.getElementById("svcContent");
  const svcContentHint = document.getElementById("svcContentHint");
  const svcCreateBtn = document.getElementById("svcCreateBtn");
  const svcDeleteBtn = document.getElementById("svcDeleteBtn");
  const svcRekeyBtn = document.getElementById("svcRekeyBtn");
  const svcUpdateInfoBtn = document.getElementById("svcUpdateInfoBtn");
  const svcUpdateContentBtn = document.getElementById("svcUpdateContentBtn");
  const svcLog = document.getElementById("svcLog");

  // Links
  const linkWsSel = document.getElementById("linkWsSel");
  const linkIssuer = document.getElementById("linkIssuer");
  const linkAudience = document.getElementById("linkAudience");
  const linkContext = document.getElementById("linkContext");
  const linkContextHint = document.getElementById("linkContextHint");
  const linkBtn = document.getElementById("linkBtn");
  const unlinkBtn = document.getElementById("unlinkBtn");
  const linkLog = document.getElementById("linkLog");
  const linkList = document.getElementById("linkList");

  // System
  const rotateRsaBtn = document.getElementById("rotateRsaBtn");
  const reloadAdminBtn = document.getElementById("reloadAdminBtn");
  const diagnosticsBtn = document.getElementById("diagnosticsBtn");
  const systemLog = document.getElementById("systemLog");

  let cache = {services:[], workspaces:[], links:[], types:[], system:{}};
  let selectedLinkWorkspaceId = null;

  // Helpers
  function key(){ return localStorage.getItem(KEY_STORAGE) || ""; }
  function headers(extra){
    return Object.assign({ "x-api-key": key(), "accept": "application/json" }, extra||{});
  }
  function formatVersion(v){ return v ? String(v).slice(0,8)+"…" : "—"; }
  function parseJSONOrEmpty(text){
    const t = (text||"").trim();
    if (!t) return {};
    return JSON.parse(t);
  }
  function tryParse(text){
    try { parseJSONOrEmpty(text); return {ok:true, msg:"JSON • valid"}; }
    catch(e){ return {ok:false, msg:"Invalid JSON: "+e.message}; }
  }
  function attachJsonLiveValidation(textarea, hintEl){
    const apply = ()=>{
      const {ok, msg} = tryParse(textarea.value);
      textarea.classList.toggle("json-invalid", !ok);
      if (hintEl) { hintEl.textContent = ok ? "JSON • valid" : msg; hintEl.style.color = ok ? "" : "#ef4444"; }
    };
    textarea.addEventListener("input", apply);
    apply();
  }
  function assertJsonValid(textarea){
    const {ok, msg} = tryParse(textarea.value);
    if (!ok) throw new Error(msg);
  }
  function logTo(el, obj){ el.textContent = typeof obj === "string" ? obj : JSON.stringify(obj, null, 2); }

  function setSelectOptions(sel, items, get){
    sel.replaceChildren();
    const opts = (items || []).map(get);
    for (const o of opts){
      const el = document.createElement("option");
      el.value = o.value;
      el.textContent = o.label;
      sel.appendChild(el);
    }
  }

  // Lock/unlock workspace ID/Name (locked after selecting; editable for creation)
  function setWorkspaceFieldsLocked(lock){
    [wsId, wsName].forEach(el => {
      el.readOnly = !!lock;
      if (lock){
        el.classList.add("bg-slate-50", "cursor-not-allowed");
      } else {
        el.classList.remove("bg-slate-50", "cursor-not-allowed");
      }
    });
  }
  setWorkspaceFieldsLocked(false);

  function renderWorkspaceList(){
    const q = (wsSearch.value || "").toLowerCase();
    const items = (cache.workspaces || [])
      .filter(w => !q || String(w.name).toLowerCase().includes(q) || String(w.id).toLowerCase().includes(q))
      .sort((a,b)=>String(a.name).localeCompare(String(b.name)));
    wsList.replaceChildren();
    for (const w of items){
      const row = document.createElement("div");
      row.className = "item";
      row.innerHTML = `
        <div class="min-w-0">
          <div class="font-semibold text-slate-800 truncate">${w.name}</div>
          <div class="small truncate">${w.id}</div>
        </div>
        <div class="flex items-center gap-2">
          <span class="pill">ver ${formatVersion(w.version)}</span>
          <button class="btn bg-slate-100 hover:bg-slate-200 text-slate-800" data-id="${w.id}">Select</button>
        </div>
      `;
      row.querySelector("button").addEventListener("click", ()=>{
        wsSel.textContent = w.id;
        wsId.value = w.id;
        wsName.value = w.name || "";
        wsInfo.value = JSON.stringify(w.info || {}, null, 2);
        wsContent.value = JSON.stringify(w.content || {}, null, 2);
        wsInfo.dispatchEvent(new Event("input"));
        wsContent.dispatchEvent(new Event("input"));
        setWorkspaceFieldsLocked(true);
        localStorage.setItem(WS_SELECTED_KEY, w.id);
        selectedLinkWorkspaceId = w.id;
        linkWsSel.textContent = w.id;
        renderLinkList();
      });
      wsList.appendChild(row);
    }
  }

  function renderServiceList(){
    const q = (svcSearch.value || "").toLowerCase();
    const tf = (typeFilter.value || "").toLowerCase();
    const items = (cache.services || [])
      .filter(s => (!q || String(s.name).toLowerCase().includes(q) || String(s.id).toLowerCase().includes(q)))
      .filter(s => (!tf || String(s.type).toLowerCase() === tf))
      .sort((a,b)=>String(a.name).localeCompare(String(b.name)));
    svcList.replaceChildren();
    for (const s of items){
      const row = document.createElement("div");
      row.className = "item";
      row.innerHTML = `
        <div class="min-w-0">
          <div class="font-semibold text-slate-800 truncate">${s.name} <span class="small">(${s.type})</span></div>
          <div class="small truncate">${s.id}</div>
        </div>
        <div class="flex items-center gap-2">
          <span class="pill">ver ${formatVersion(s.version)}</span>
          <button class="btn bg-slate-100 hover:bg-slate-200 text-slate-800" data-id="${s.id}">Load</button>
        </div>
      `;
      row.querySelector("button").addEventListener("click", ()=>{
        svcSel.textContent = s.id;
        svcId.value = s.id;
        svcName.value = s.name || "";
        svcType.value = s.type || "";
        svcInfo.value = JSON.stringify(s.info || {}, null, 2);
        svcContent.value = JSON.stringify(s.content || {}, null, 2);
        svcInfo.dispatchEvent(new Event("input"));
        svcContent.dispatchEvent(new Event("input"));
      });
      svcList.appendChild(row);
    }
  }

  function renderLinkList(){
    linkList.replaceChildren();
    if (!selectedLinkWorkspaceId){
      const empty = document.createElement("div");
      empty.className = "item";
      empty.innerHTML = '<div class="small">Workspace must be selected first (Workspaces tab).</div>';
      linkList.appendChild(empty);
      return;
    }
    const svcById = Object.fromEntries((cache.services || []).map(s=>[s.id,s]));
    const items = (cache.links || []).filter(l => l.workspace_id === selectedLinkWorkspaceId);
    if (!items.length){
      const empty = document.createElement("div");
      empty.className = "item";
      empty.innerHTML = '<div class="small">No links in this workspace yet.</div>';
      linkList.appendChild(empty);
      return;
    }
    for (const l of items){
      const i = svcById[l.issuer_id];
      const a = svcById[l.audience_id];
      const row = document.createElement("div");
      row.className = "item";
      row.innerHTML = `
        <div class="min-w-0">
          <div class="font-semibold text-slate-800 truncate">${(i ? i.name : l.issuer_id)} → ${(a ? a.name : l.audience_id)}</div>
          <div class="small truncate">${l.issuer_id} → ${l.audience_id}</div>
        </div>
        <div class="flex items-center gap-2">
          <button class="btn bg-slate-100 hover:bg-slate-200" data-act="edit">Edit</button>
        </div>
      `;
      row.querySelector("button").addEventListener("click", ()=>{
        linkIssuer.value = l.issuer_id;
        linkAudience.value = l.audience_id;
        linkContext.value = JSON.stringify(l.context || {}, null, 2);
        linkContext.dispatchEvent(new Event("input"));
      });
      linkList.appendChild(row);
    }
  }

  // JSON live validation
  [wsInfo, wsContent, svcInfo, svcContent, linkContext].forEach((ta)=>{
    if (!ta) return;
    const hint = (ta === wsInfo) ? wsInfoHint :
                 (ta === wsContent) ? wsContentHint :
                 (ta === svcInfo) ? svcInfoHint :
                 (ta === svcContent) ? svcContentHint :
                 (ta === linkContext) ? linkContextHint : null;
    attachJsonLiveValidation(ta, hint);
  });

  // API helper
  async function api(path, opts = {}){
    const resp = await fetch(path, Object.assign({ headers: headers() }, opts));
    const text = await resp.text();
    if (!resp.ok){
      throw new Error(`HTTP ${resp.status}: ${text}`);
    }
    try { return text ? JSON.parse(text) : {}; } catch { return { raw: text }; }
  }

  // Data refresh
  async function refreshData(){
    try {
      if (!key()) return; // no key yet; UI still works (tabs etc.)
      const d = await api("/admin/data");
      cache.workspaces = d.workspaces || [];
      cache.services = d.services || [];
      cache.types = d.types || [];
      cache.links = d.links || [];
      cache.system = d.system || {};
      wsVer.textContent = formatVersion(d.system && d.system.workspaces_version);
      svcVer.textContent = formatVersion(d.system && d.system.services_version);

      renderWorkspaceList();
      renderServiceList();

      // Build filters/dropdowns
      typeFilter.replaceChildren();
      const oAll = document.createElement("option"); oAll.value = ""; oAll.textContent = "All types"; typeFilter.appendChild(oAll);
      (cache.types || []).forEach(t => { const o = document.createElement("option"); o.value = t; o.textContent = t; typeFilter.appendChild(o); });

      setSelectOptions(svcType, cache.types, t => ({ value: t, label: t }));
      setSelectOptions(linkIssuer, cache.services, s => ({ value: s.id, label: `${s.name} (${s.type})` }));
      setSelectOptions(linkAudience, cache.services, s => ({ value: s.id, label: `${s.name} (${s.type})` }));

      // Restore selected workspace for Links tab
      const savedWsId = localStorage.getItem(WS_SELECTED_KEY);
      if (savedWsId && cache.workspaces.some(w => w.id === savedWsId)){
        selectedLinkWorkspaceId = savedWsId;
        linkWsSel.textContent = savedWsId;
      } else {
        selectedLinkWorkspaceId = null;
        linkWsSel.textContent = "—";
      }
      renderLinkList();
    } catch(e){
      console.error(e);
      systemLog.textContent = "Failed to load admin data: " + e.message;
    }
  }

  // Auth/key handling (login/logout UX)
  function setSignedIn(on){
    if (on){
      apiKeyInput.disabled = true;
      apiKeyInput.classList.add("opacity-80", "cursor-not-allowed");
      saveKeyBtn.innerHTML = '<i class="fas fa-sign-out-alt"></i> Logout';
      // Use onclick assignment to avoid accumulating listeners across state flips.
      saveKeyBtn.onclick = () => {
        localStorage.removeItem(KEY_STORAGE);
        // Also clear selection state so Links panel doesn't show stale selection.
        localStorage.removeItem(WS_SELECTED_KEY);

        apiKeyInput.value = "";
        apiKeyInput.disabled = false;
        apiKeyInput.classList.remove("opacity-80", "cursor-not-allowed");

        saveKeyBtn.innerHTML = '<i class="fas fa-sign-in-alt"></i> Sign in';
        saveKeyBtn.onclick = doSignIn;

        // Clear UI quickly (refreshData() no-ops without a key)
        wsList.replaceChildren();
        svcList.replaceChildren();
        linkList.replaceChildren();
        wsVer.textContent = "—";
        svcVer.textContent = "—";
        wsSel.textContent = "—";
        svcSel.textContent = "—";
        linkWsSel.textContent = "—";
        selectedLinkWorkspaceId = null;

        systemLog.textContent = "Signed out.";
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
    if (!k) { alert("Paste a valid admin x-api-key"); return; }
    localStorage.setItem(KEY_STORAGE, k);
    setSignedIn(true);
    refreshData();
  }

  const savedKey = key();
  if (savedKey) {
    apiKeyInput.value = savedKey;
    setSignedIn(true);
  } else {
    setSignedIn(false);
  }
// Manual & auto refresh
  refreshBtn.addEventListener("click", refreshData);
  let timer = null;
  function startLoop(){
    if (timer) { clearInterval(timer); timer = null; }
    if (!autoRefreshChk.checked) return;
    timer = setInterval(refreshData, AUTO_REFRESH_MS);
  }
  autoRefreshChk.addEventListener("change", startLoop);
  startLoop();

  // Workspace actions
  wsCreateBtn.addEventListener("click", async ()=>{
    try{
      assertJsonValid(wsInfo); assertJsonValid(wsContent);
      const payload = {
        id: wsId.value.trim(),
        name: wsName.value.trim(),
        info: parseJSONOrEmpty(wsInfo.value),
        content: parseJSONOrEmpty(wsContent.value),
      };
      const resp = await api("/api/v1/workspaces", {
        method: "POST",
        headers: headers({ "content-type":"application/json" }),
        body: JSON.stringify(payload)
      });
      logTo(wsLog, resp);
      refreshData();
    }catch(e){ logTo(wsLog, String(e)); }
  });

  wsDeleteBtn.addEventListener("click", async ()=>{
    if (!wsId.value.trim()) return;
    if (!confirm("Delete this workspace?")) return;
    try{
      const wid = encodeURIComponent(wsId.value.trim());
      const resp = await api(`/api/v1/workspaces/${wid}`, { method: "DELETE" });
      logTo(wsLog, resp);
      wsId.value = ""; wsName.value = "";
      setWorkspaceFieldsLocked(false);
      refreshData();
    }catch(e){ logTo(wsLog, String(e)); }
  });

  wsUpdateInfoBtn.addEventListener("click", async ()=>{
    try{
      assertJsonValid(wsInfo);
      const wid = encodeURIComponent(wsId.value.trim());
      const resp = await api(`/api/v1/workspaces/${wid}/info`, {
        method: "PUT",
        headers: headers({ "content-type":"application/json" }),
        body: wsInfo.value
      });
      logTo(wsLog, resp);
      refreshData();
    }catch(e){ logTo(wsLog, String(e)); }
  });

  wsUpdateContentBtn.addEventListener("click", async ()=>{
    try{
      assertJsonValid(wsContent);
      const wid = encodeURIComponent(wsId.value.trim());
      const resp = await api(`/api/v1/workspaces/${wid}/content`, {
        method: "PUT",
        headers: headers({ "content-type":"application/json" }),
        body: wsContent.value
      });
      logTo(wsLog, resp);
      refreshData();
    }catch(e){ logTo(wsLog, String(e)); }
  });

  wsRekeyBtn.addEventListener("click", async ()=>{
    try{
      const wid = encodeURIComponent(wsId.value.trim());
      const resp = await api(`/api/v1/workspaces/${wid}/rekey`, { method: "PUT" });
      logTo(wsLog, resp);
      refreshData();
    }catch(e){ logTo(wsLog, String(e)); }
  });

  // Service actions
  svcCreateBtn.addEventListener("click", async ()=>{
    try{
      assertJsonValid(svcInfo); assertJsonValid(svcContent);
      const payload = {
        id: svcId.value.trim(),
        name: svcName.value.trim(),
        type: svcType.value.trim(),
        info: parseJSONOrEmpty(svcInfo.value),
        content: parseJSONOrEmpty(svcContent.value),
      };
      const resp = await api("/api/v1/services", {
        method: "POST",
        headers: headers({ "content-type":"application/json" }),
        body: JSON.stringify(payload)
      });
      logTo(svcLog, resp);
      refreshData();
    }catch(e){ logTo(svcLog, String(e)); }
  });

  svcDeleteBtn.addEventListener("click", async ()=>{
    if (!svcId.value.trim()) return;
    if (!confirm("Delete this service?")) return;
    try{
      const sid = encodeURIComponent(svcId.value.trim());
      const resp = await api(`/api/v1/services/${sid}`, { method: "DELETE" });
      logTo(svcLog, resp);
      refreshData();
    }catch(e){ logTo(svcLog, String(e)); }
  });

  svcRekeyBtn.addEventListener("click", async ()=>{
    try{
      const sid = encodeURIComponent(svcId.value.trim());
      const resp = await api(`/api/v1/services/${sid}/rekey`, { method: "PUT" });
      logTo(svcLog, resp);
      refreshData();
    }catch(e){ logTo(svcLog, String(e)); }
  });

  svcUpdateInfoBtn.addEventListener("click", async ()=>{
    try{
      assertJsonValid(svcInfo);
      const sid = encodeURIComponent(svcId.value.trim());
      const resp = await api(`/api/v1/services/${sid}/info`, {
        method: "PUT",
        headers: headers({ "content-type":"application/json" }),
        body: svcInfo.value
      });
      logTo(svcLog, resp);
      refreshData();
    }catch(e){ logTo(svcLog, String(e)); }
  });

  svcUpdateContentBtn.addEventListener("click", async ()=>{
    try{
      assertJsonValid(svcContent);
      const sid = encodeURIComponent(svcId.value.trim());
      const resp = await api(`/api/v1/services/${sid}/content`, {
        method: "PUT",
        headers: headers({ "content-type":"application/json" }),
        body: svcContent.value
      });
      logTo(svcLog, resp);
      refreshData();
    }catch(e){ logTo(svcLog, String(e)); }
  });

  // Link actions
  linkBtn.addEventListener("click", async ()=>{
    if (!selectedLinkWorkspaceId) { alert("Select a workspace first (Workspaces tab)."); return; }
    try{
      assertJsonValid(linkContext);
      const data = {
        issuer_id: linkIssuer.value,
        audience_id: linkAudience.value,
        context: parseJSONOrEmpty(linkContext.value)
      };
      const resp = await api(`/api/v1/workspaces/${encodeURIComponent(selectedLinkWorkspaceId)}/link-service`, {
        method: "POST",
        headers: headers({ "content-type":"application/json" }),
        body: JSON.stringify(data)
      });
      logTo(linkLog, resp);
      refreshData();
    }catch(e){ logTo(linkLog, String(e)); }
  });

  unlinkBtn.addEventListener("click", async ()=>{
    if (!selectedLinkWorkspaceId) { alert("Select a workspace first (Workspaces tab)."); return; }
    try{
      assertJsonValid(linkContext);
      const data = {
        issuer_id: linkIssuer.value,
        audience_id: linkAudience.value,
        context: parseJSONOrEmpty(linkContext.value)
      };
      const resp = await api(`/api/v1/workspaces/${encodeURIComponent(selectedLinkWorkspaceId)}/unlink-service`, {
        method: "POST",
        headers: headers({ "content-type":"application/json" }),
        body: JSON.stringify(data)
      });
      logTo(linkLog, resp);
      refreshData();
    }catch(e){ logTo(linkLog, String(e)); }
  });

  // System actions
  rotateRsaBtn.addEventListener("click", async ()=>{
    try{
      const resp = await api("/api/v1/system/rotate-keys", { method: "POST" });
      logTo(systemLog, resp);
      refreshData();
    } catch(e){ logTo(systemLog, String(e)); }
  });

  reloadAdminBtn.addEventListener("click", async ()=>{
    try{
      const resp = await api("/api/v1/system/rotate", { method: "POST" });
      logTo(systemLog, resp);
      refreshData();
    } catch(e){ logTo(systemLog, String(e)); }
  });

  diagnosticsBtn.addEventListener("click", async ()=>{
    try{
      const resp = await api("/api/v1/system/diagnostics");
      logTo(systemLog, resp);
    } catch(e){ logTo(systemLog, String(e)); }
  });

  // Filters
  wsSearch.addEventListener("input", renderWorkspaceList);
  svcSearch.addEventListener("input", renderServiceList);
  typeFilter.addEventListener("change", renderServiceList);

  // Initial load
  refreshData();
})();
</script>
</body>
</html>
"""


@router.get("/admin", response_class=HTMLResponse, include_in_schema=False)
async def admin_page() -> HTMLResponse:
    """Serve the Admin Console with requested styling and behavior."""
    return HTMLResponse(ADMIN_HTML)


@router.get("/admin/data", response_class=JSONResponse, include_in_schema=False)
async def admin_data(_: str = Depends(validate_authbridge_api_key)) -> JSONResponse:
    """
    Aggregated snapshot for the admin UI:
      - services (id, name, type, version, info/content)
      - workspaces (id, name, version, info/content)
      - links (issuer->audience per workspace)
      - available service types
      - system version stamps
    """
    await reload_services()
    await reload_workspaces()

    services: List[Dict[str, Any]] = []
    for s in caches.services.values():
        services.append(
            {
                "id": s.id,
                "name": s.name,
                "type": s.type,
                "version": s.version,
                "info": s.info or {},
                "content": s.content or {},
            }
        )

    workspaces: List[Dict[str, Any]] = []
    links: List[Dict[str, Any]] = []
    for w in caches.workspaces.values():
        workspaces.append(
            {
                "id": w.id,
                "name": w.name,
                "version": w.version,
                "info": w.info or {},
                "content": w.content or {},
            }
        )
        for link in (w.services or []):
            if isinstance(link, ServiceLink):
                links.append(
                    {
                        "workspace_id": w.id,
                        "issuer_id": link.issuer_id,
                        "audience_id": link.audience_id,
                        "context": link.context or {},
                    }
                )

    types = load_service_types()

    payload = {
        "now": datetime.now(timezone.utc).isoformat(),
        "system": {
            "services_version": caches.service_sys_ver,
            "workspaces_version": caches.workspace_sys_ver,
        },
        "services": sorted(
            services, key=lambda x: (str(x["type"]).lower(), str(x["name"]).lower())
        ),
        "workspaces": sorted(workspaces, key=lambda x: str(x["name"]).lower()),
        "links": links,
        "types": types,
    }
    return JSONResponse(payload)


@router.get("/admin/ready", response_class=PlainTextResponse, include_in_schema=False)
async def admin_ready() -> PlainTextResponse:
    """Simple readiness ping for this UI."""
    return PlainTextResponse("ok")
