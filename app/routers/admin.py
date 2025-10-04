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

log = get_logger("auth-bridge.admin-ui")

router = APIRouter(tags=["admin-ui"])

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
      color: #374151 !important; /* Force dark color */
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
      color: #374151 !important; /* Force dark color */
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
    
    /* Force dark text in KPI cards */
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
    
    /* Custom scrollbar */
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
    
    /* Loading animation */
    .loading-pulse {
      animation: pulseSoft 2s infinite;
    }
    
    /* Header text - ensure visibility */
    .header-content h1,
    .header-content p,
    .header-content label {
      color: white !important;
      text-shadow: 0 1px 3px rgba(0, 0, 0, 0.3);
    }
    
    /* Ensure form elements in header have proper colors */
    .glass .input {
      color: #1e293b !important;
    }
    
    .glass .btn {
      color: #1e293b !important;
    }
    
    /* Force white text in header area */
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
  </style>
    <!-- Header with gradient -->
    <header class="header-gradient rounded-2xl p-6 md:p-8 mb-6 relative overflow-hidden fade-in">
      <div class="relative z-10">
        <div class="flex flex-col md:flex-row md:items-center md:justify-between gap-4">
          <div class="header-content">
            <div class="flex items-center gap-3 mb-2">
              <div class="w-10 h-10 rounded-xl bg-white/20 flex items-center justify-center">
                <i class="fas fa-bridge text-white text-lg"></i>
              </div>
              <h1 class="text-3xl font-bold text-white">AuthBridge Admin Console</h1>
            </div>
            <p class="opacity-95 text-sm text-white">Provision & maintain workspaces, services, trust links, and keys.</p>
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
        <div class="mt-6 grid grid-cols-2 md:grid-cols-4 gap-4">
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
              <div class="text-sm font-medium text-slate-600">Last update</div>
              <i class="fas fa-clock text-primary-400"></i>
            </div>
            <div id="lastUpdate" class="text-xl font-bold mt-2 text-slate-800">–</div>
          </div>
        </div>
      </div>
    </header>

    <!-- Tabs -->
    <nav class="mb-6 slide-up">
      <div class="card p-2 flex flex-wrap gap-1">
        <button data-tab="workspaces" class="tab-btn active">
          <i class="fas fa-layer-group"></i> Workspaces
        </button>
        <button data-tab="services" class="tab-btn">
          <i class="fas fa-cube"></i> Services
        </button>
        <button data-tab="links" class="tab-btn">
          <i class="fas fa-link"></i> Link Services
        </button>
        <button data-tab="system" class="tab-btn">
          <i class="fas fa-cog"></i> System
        </button>
      </div>
    </nav>

    <!-- Panels -->
    <section class="slide-up">
      <!-- Workspaces -->
      <div id="tab-workspaces" class="tab-panel">
        <div class="grid-aside">
          <!-- List -->
          <div class="card p-5">
            <div class="flex items-center justify-between mb-4">
              <h2 class="font-bold text-lg flex items-center gap-2">
                <i class="fas fa-layer-group text-primary-500"></i> Workspaces
              </h2>
              <span class="pill flex items-center gap-1">
                <i class="fas fa-code-branch text-xs"></i>
                ver <span id="wsVer" class="kbd kbd-short" title="Full version: —">—</span>
              </span>
            </div>
            <div class="relative mb-4">
              <i class="fas fa-search absolute left-3 top-1/2 transform -translate-y-1/2 text-slate-400"></i>
              <input id="wsSearch" class="input !pl-10" placeholder="Filter by name/id…"/>
            </div>
            <div id="wsList" class="list text-sm divide-y divide-slate-100"></div>
          </div>
          <!-- Form -->
          <div class="card p-5">
            <div class="flex items-center justify-between mb-4">
              <h3 class="font-bold text-lg flex items-center gap-2">
                <i class="fas fa-edit text-primary-500"></i> Workspace Editor
              </h3>
              <div class="text-xs text-slate-500">Selected: <span id="wsSel" class="kbd kbd-short" title="Full ID: —">—</span></div>
            </div>

            <div class="grid-3 mb-4">
              <div>
                <label class="label">Workspace ID</label>
                <input id="wsId" class="input" placeholder="unique identifier"/>
              </div>
              <div>
                <label class="label">Name</label>
                <input id="wsName" class="input" placeholder="display name"/>
              </div>
              <div>
                <label class="label">If-Match (version)</label>
                <input id="wsIfMatch" class="input" placeholder="concurrency version"/>
              </div>
            </div>
            <div class="grid-2 mb-4">
              <div>
                <label class="label">Info JSON</label>
                <textarea id="wsInfo" class="textarea h-56" placeholder='{"env":"prod"}' data-json></textarea>
                <div id="wsInfoHint" class="hint mt-1 flex items-center gap-1">
                  <i class="fas fa-code"></i> <span>JSON • valid</span>
                </div>
              </div>
              <div>
                <label class="label">Content JSON</label>
                <textarea id="wsContent" class="textarea h-56" placeholder='encrypted at rest' data-json></textarea>
                <div id="wsContentHint" class="hint mt-1 flex items-center gap-1">
                  <i class="fas fa-code"></i> <span>JSON • valid</span>
                </div>
              </div>
            </div>
            <div class="flex flex-wrap gap-2 mb-4">
              <button id="wsCreateBtn" class="btn bg-emerald-500 hover:bg-emerald-600 text-white">
                <i class="fas fa-plus"></i> Create
              </button>
              <button id="wsUpdateInfoBtn" class="btn bg-primary-500 hover:bg-primary-600 text-white">
                <i class="fas fa-save"></i> Update Info
              </button>
              <button id="wsUpdateContentBtn" class="btn bg-primary-500 hover:bg-primary-600 text-white">
                <i class="fas fa-save"></i> Update Content
              </button>
              <button id="wsRekeyBtn" class="btn bg-amber-500 hover:bg-amber-600 text-white">
                <i class="fas fa-key"></i> Rekey
              </button>
              <button id="wsDeleteBtn" class="btn bg-rose-500 hover:bg-rose-600 text-white">
                <i class="fas fa-trash"></i> Delete
              </button>
              <button id="wsClearBtn" class="btn bg-slate-200 hover:bg-slate-300 text-slate-700">
                <i class="fas fa-eraser"></i> Clear
              </button>
            </div>
            <div>
              <label class="label">Activity Log</label>
              <pre id="wsLog" class="text-xs bg-slate-50 p-3 rounded-lg border overflow-auto max-h-48">—</pre>
            </div>
          </div>
        </div>
      </div>

      <!-- Services -->
      <div id="tab-services" class="tab-panel hidden">
        <div class="grid-aside">
          <!-- List -->
          <div class="card p-5">
            <div class="flex items-center justify-between mb-4">
              <h2 class="font-bold text-lg flex items-center gap-2">
                <i class="fas fa-cube text-primary-500"></i> Services
              </h2>
              <span class="pill flex items-center gap-1">
                <i class="fas fa-code-branch text-xs"></i>
                ver <span id="svcVer" class="kbd kbd-short" title="Full version: —">—</span>
              </span>
            </div>
            <div class="grid-2 mb-4">
              <div class="relative">
                <i class="fas fa-search absolute left-3 top-1/2 transform -translate-y-1/2 text-slate-400"></i>
                <input id="svcSearch" class="input !pl-10" placeholder="Filter by name/id…"/>
              </div>
              <select id="typeFilter" class="select">
                <option value="">All types</option>
              </select>
            </div>
            <div id="svcList" class="list text-sm divide-y divide-slate-100"></div>
          </div>
          <!-- Form -->
          <div class="card p-5">
            <div class="flex items-center justify-between mb-4">
              <h3 class="font-bold text-lg flex items-center gap-2">
                <i class="fas fa-edit text-primary-500"></i> Service Editor
              </h3>
              <div class="text-xs text-slate-500">Selected: <span id="svcSel" class="kbd kbd-short" title="Full ID: —">—</span></div>
            </div>

            <div class="grid-3 mb-4">
              <div>
                <label class="label">Service ID</label>
                <input id="svcId" class="input" placeholder="unique identifier"/>
              </div>
              <div>
                <label class="label">Name</label>
                <input id="svcName" class="input" placeholder="display name"/>
              </div>
              <div>
                <label class="label">Type</label>
                <select id="svcType" class="select"></select>
              </div>
            </div>
            <div class="grid-2 mb-4">
              <div>
                <label class="label">Info JSON</label>
                <textarea id="svcInfo" class="textarea h-56" placeholder='metadata / TTL' data-json></textarea>
                <div id="svcInfoHint" class="hint mt-1 flex items-center gap-1">
                  <i class="fas fa-code"></i> <span>JSON • valid</span>
                </div>
              </div>
              <div>
                <label class="label">Content JSON</label>
                <textarea id="svcContent" class="textarea h-56" placeholder='conn strings, constants, etc.' data-json></textarea>
                <div id="svcContentHint" class="hint mt-1 flex items-center gap-1">
                  <i class="fas fa-code"></i> <span>JSON • valid</span>
                </div>
              </div>
            </div>
           <div class="flex flex-wrap gap-2 mb-2">
  <button id="svcCreateBtn" class="btn bg-emerald-500 hover:bg-emerald-600 text-white">
    <i class="fas fa-plus"></i> Create
  </button>
  <button id="svcRekeyBtn" class="btn bg-amber-500 hover:bg-amber-600 text-white">
    <i class="fas fa-key"></i> Rekey
  </button>
  <button id="svcUpdateInfoBtn" class="btn bg-primary-500 hover:bg-primary-600 text-white">
    <i class="fas fa-save"></i> Update Info
  </button>
  <button id="svcUpdateContentBtn" class="btn bg-primary-500 hover:bg-primary-600 text-white">
    <i class="fas fa-save"></i> Update Content
  </button>
  <button id="svcDeleteBtn" class="btn bg-rose-500 hover:bg-rose-600 text-white">
    <i class="fas fa-trash"></i> Delete
  </button>
</div>
<div class="mb-4">
  <label class="label">If-Match (version)</label>
  <input id="svcIfMatch" class="input" placeholder="concurrency version" maxlength="100"/>
</div>
<div>
  <label class="label">Activity Log</label>
  <pre id="svcLog" class="text-xs bg-slate-50 p-3 rounded-lg border overflow-auto max-h-48">—</pre>
</div>

      </div>

      <!-- Link Services -->
      <div id="tab-links" class="tab-panel hidden">
        <div class="grid-aside">
          <!-- Left: workspace list -->
          <div class="card p-5">
            <div class="flex items-center justify-between mb-4">
              <h2 class="font-bold text-lg flex items-center gap-2">
                <i class="fas fa-layer-group text-primary-500"></i> Workspaces
              </h2>
              <span class="pill flex items-center gap-1">
                <i class="fas fa-code-branch text-xs"></i>
                ver <span id="linkWsVer" class="kbd kbd-short" title="Full version: —">—</span>
              </span>
            </div>
            <div class="relative mb-4">
              <i class="fas fa-search absolute left-3 top-1/2 transform -translate-y-1/2 text-slate-400"></i>
              <input id="linkWsSearch" class="input !pl-10" placeholder="Filter by name/id…"/>
            </div>
            <div id="linkWsList" class="list text-sm divide-y divide-slate-100"></div>
          </div>

          <!-- Right: linking editor -->
          <div class="card p-5">
            <div class="flex items-center justify-between mb-4">
              <h3 class="font-bold text-lg flex items-center gap-2">
                <i class="fas fa-link text-primary-500"></i> Link Services
              </h3>
              <div class="text-xs text-slate-500">Workspace: <span id="linkWsSel" class="kbd kbd-short" title="Full ID: —">—</span></div>
            </div>

            <div class="grid-3 mb-4">
              <div>
                <label class="label">If-Match (workspace version)</label>
                <input id="linkIfMatch" class="input" placeholder="concurrency version"/>
              </div>
              <div class="hint self-center">Concurrency check via <span class="kbd">If-Match</span></div>
              <div></div>
            </div>

            <div class="grid-3 mb-4">
              <div>
                <label class="label">Issuer Service</label>
                <select id="linkIssuer" class="select"></select>
              </div>
              <div>
                <label class="label">Context (JSON)</label>
                <textarea id="linkContext" class="textarea h-44" placeholder='{"db": "postgres://..."}' data-json></textarea>
                <div id="linkContextHint" class="hint mt-1 flex items-center gap-1">
                  <i class="fas fa-code"></i> <span>JSON • valid</span>
                </div>
              </div>
              <div>
                <label class="label">Audience Service</label>
                <select id="linkAudience" class="select"></select>
              </div>
            </div>

            <div class="flex flex-wrap gap-2 mb-4">
              <button id="linkBtn" class="btn bg-primary-500 hover:bg-primary-600 text-white">
                <i class="fas fa-link"></i> Link Services
              </button>
              <button id="unlinkBtn" class="btn bg-rose-500 hover:bg-rose-600 text-white">
                <i class="fas fa-unlink"></i> Unlink Services
              </button>
            </div>

            <div class="grid md:grid-cols-2 gap-4">
              <div class="card p-4">
                <div class="text-sm font-medium mb-2 flex items-center gap-2">
                  <i class="fas fa-list text-primary-500"></i> Existing Links
                </div>
                <div id="linkList" class="list text-xs"></div>
              </div>
              <div>
                <label class="label">Activity Log</label>
                <pre id="linkLog" class="text-xs bg-slate-50 p-3 rounded-lg border overflow-auto max-h-64">—</pre>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- System -->
      <div id="tab-system" class="tab-panel hidden">
        <div class="card p-5">
          <h2 class="font-bold text-lg mb-2 flex items-center gap-2">
            <i class="fas fa-cog text-primary-500"></i> System Operations
          </h2>
          <p class="text-sm muted mb-4">Use with care. Concurrency-safe updates rely on <span class="kbd">If-Match</span> versions.</p>
          <div class="grid-2 mb-4">
            <button id="rotateRsaBtn" class="btn bg-primary-500 hover:bg-primary-600 text-white">
              <i class="fas fa-sync"></i> Rotate RSA Keys
            </button>
            <button id="reloadAdminBtn" class="btn bg-slate-200 hover:bg-slate-300 text-slate-700">
              <i class="fas fa-redo"></i> Reload Admin Keys
            </button>
          </div>
          <div>
            <label class="label">System Log</label>
            <pre id="systemLog" class="text-xs bg-slate-50 p-3 rounded-lg border overflow-auto max-h-56">—</pre>
          </div>
        </div>
      </div>
    </section>

    <footer class="mt-8 text-center text-xs text-slate-500">
      <div class="flex items-center justify-center gap-2 mb-2">
        <i class="fas fa-shield-alt text-primary-500"></i>
        <span>Built for administrators • Uses your admin API key in-browser • No external calls from the server-rendered UI</span>
      </div>
    </footer>
  </div>

<script>
(function(){
  // ---------------- Tabs ----------------
  const tabButtons = document.querySelectorAll(".tab-btn");
  const panels = {
    workspaces: document.getElementById("tab-workspaces"),
    services: document.getElementById("tab-services"),
    links: document.getElementById("tab-links"),
    system: document.getElementById("tab-system"),
  };
  function activateTab(name){
    tabButtons.forEach(b => {
      const isActive = b.dataset.tab === name;
      b.classList.toggle("active", isActive);
    });
    Object.entries(panels).forEach(([key, el])=>{
      el.classList.toggle("hidden", key !== name);
    });
  }
  tabButtons.forEach(b => b.addEventListener("click", ()=>activateTab(b.dataset.tab)));
  activateTab("workspaces");

  // ------------- STATE -------------
  const KEY_STORAGE = "authbridge_admin_key";
  const AUTO_REFRESH_MS = 60000;

  const apiKeyInput = document.getElementById("apiKeyInput");
  const saveKeyBtn = document.getElementById("saveKeyBtn");
  const autoRefreshChk = document.getElementById("autoRefreshChk");
  const refreshBtn = document.getElementById("refreshBtn");

  const wsCount = document.getElementById("wsCount");
  const svcCount = document.getElementById("svcCount");
  const linkCount = document.getElementById("linkCount");
  const lastUpdate = document.getElementById("lastUpdate");
  const wsVer = document.getElementById("wsVer");
  const svcVer = document.getElementById("svcVer");

  // Workspaces (main tab)
  const wsList = document.getElementById("wsList");
  const wsSearch = document.getElementById("wsSearch");
  const wsSel = document.getElementById("wsSel");
  const wsId = document.getElementById("wsId");
  const wsName = document.getElementById("wsName");
  const wsIfMatch = document.getElementById("wsIfMatch");
  const wsInfo = document.getElementById("wsInfo");
  const wsContent = document.getElementById("wsContent");
  const wsCreateBtn = document.getElementById("wsCreateBtn");
  const wsUpdateInfoBtn = document.getElementById("wsUpdateInfoBtn");
  const wsUpdateContentBtn = document.getElementById("wsUpdateContentBtn");
  const wsRekeyBtn = document.getElementById("wsRekeyBtn");
  const wsDeleteBtn = document.getElementById("wsDeleteBtn");
  const wsClearBtn = document.getElementById("wsClearBtn");
  const wsLog = document.getElementById("wsLog");

  // Services
  const svcList = document.getElementById("svcList");
  const svcSearch = document.getElementById("svcSearch");
  const typeFilter = document.getElementById("typeFilter");
  const svcSel = document.getElementById("svcSel");
  const svcId = document.getElementById("svcId");
  const svcName = document.getElementById("svcName");
  const svcType = document.getElementById("svcType");
  const svcIfMatch = document.getElementById("svcIfMatch");
  const svcInfo = document.getElementById("svcInfo");
  const svcContent = document.getElementById("svcContent");
  const svcCreateBtn = document.getElementById("svcCreateBtn");
  const svcRekeyBtn = document.getElementById("svcRekeyBtn");
  const svcUpdateInfoBtn = document.getElementById("svcUpdateInfoBtn");
  const svcUpdateContentBtn = document.getElementById("svcUpdateContentBtn");
  const svcDeleteBtn = document.getElementById("svcDeleteBtn");
  const svcLog = document.getElementById("svcLog");

  // Links (redesigned)
  const linkWsVer = document.getElementById("linkWsVer");
  const linkWsSel = document.getElementById("linkWsSel");
  const linkWsList = document.getElementById("linkWsList");
  const linkWsSearch = document.getElementById("linkWsSearch");
  const linkIssuer = document.getElementById("linkIssuer");
  const linkAudience = document.getElementById("linkAudience");
  const linkContext = document.getElementById("linkContext");
  const linkContextHint = document.getElementById("linkContextHint");
  const linkIfMatch = document.getElementById("linkIfMatch");
  const linkBtn = document.getElementById("linkBtn");
  const unlinkBtn = document.getElementById("unlinkBtn");
  const linkLog = document.getElementById("linkLog");
  const linkList = document.getElementById("linkList");

  // System
  const systemLog = document.getElementById("systemLog");

  let cache = {services:[], workspaces:[], links:[], types:[], system:{}};
  let selectedLinkWorkspaceId = null;

  // ------------- AUTH -------------
  function key(){ return localStorage.getItem(KEY_STORAGE) || ""; }
  const saved = key();
  if (saved) apiKeyInput.value = saved;

  saveKeyBtn.addEventListener("click", ()=>{
    const k = apiKeyInput.value.trim();
    if (!k) { alert("Paste a valid AUTHBRIDGE admin key."); return; }
    localStorage.setItem(KEY_STORAGE, k);
    fetchAll(true);
  });

  refreshBtn.addEventListener("click", ()=>fetchAll(false));

  let timer = null;
  function startLoop(){
    stopLoop();
    if (!autoRefreshChk.checked) return;
    timer = setInterval(fetchAll, AUTO_REFRESH_MS);
  }
  function stopLoop(){ if (timer) { clearInterval(timer); timer=null; } }
  autoRefreshChk.addEventListener("change", ()=> autoRefreshChk.checked ? startLoop() : stopLoop());

  // ------------- HELPERS -------------
  function headers(extra){ return Object.assign({"x-api-key": key(), "accept":"application/json"}, extra || {}); }
  
  function setKpi(d){
    wsCount.textContent = d.workspaces.length;
    svcCount.textContent = d.services.length;
    linkCount.textContent = d.links.length;
    lastUpdate.textContent = new Date(d.now).toLocaleTimeString();
    
    // Format versions to show first 8 characters only
    wsVer.textContent = formatVersion(d.system.workspaces_version);
    wsVer.title = "Full version: " + (d.system.workspaces_version || "—");
    svcVer.textContent = formatVersion(d.system.services_version);
    svcVer.title = "Full version: " + (d.system.services_version || "—");
  }
  
  function formatVersion(version) {
    if (!version || version === "—") return "—";
    // Show first 8 characters for long version hashes
    return version.length > 8 ? version.substring(0, 8) + "…" : version;
  }
  
  function parseJSONOrEmpty(text){
    if (!text || !text.trim()) return {};
    return JSON.parse(text);
  }
  function tryParse(text){
    try { parseJSONOrEmpty(text); return {ok:true, msg:"JSON • valid"}; }
    catch(e){ return {ok:false, msg:"Invalid JSON: "+e.message}; }
  }
  function attachJsonLiveValidation(textarea, hintEl){
    const apply = ()=>{
      const {ok, msg} = tryParse(textarea.value);
      textarea.classList.toggle("json-invalid", !ok);
      if (hintEl) { 
        hintEl.innerHTML = `<i class="fas fa-code"></i> <span>${ok ? "JSON • valid" : msg}</span>`; 
        hintEl.style.color = ok ? "" : "rgb(239 68 68)"; 
      }
    };
    apply();
    textarea.addEventListener("input", apply);
  }
  function assertJsonValid(textarea){
    const {ok, msg} = tryParse(textarea.value);
    if (!ok) throw new Error(msg);
  }
  function logTo(el, obj){ 
    el.textContent = typeof obj === "string" ? obj : JSON.stringify(obj, null, 2); 
    el.classList.remove("opacity-50"); 
    el.classList.add("fade"); 
    setTimeout(()=>el.classList.add("opacity-50"), 100); 
  }
  function setSelectOptions(sel, arr, get){
    sel.replaceChildren();
    arr.forEach(o=>{
      const {value,label} = get ? get(o) : {value:o.id, label:o.name || o.id};
      const opt = document.createElement("option");
      opt.value = value; opt.textContent = label;
      sel.appendChild(opt);
    });
  }

  // Attach live JSON validation to all [data-json] textareas
  document.querySelectorAll("textarea[data-json]").forEach((ta)=>{
    const hint = document.getElementById(ta.id + "Hint");
    attachJsonLiveValidation(ta, hint);
  });

  // ------------- RENDERERS -------------
  function renderWorkspaceList(){
    const q = (wsSearch.value || "").toLowerCase();
    const items = cache.workspaces
      .filter(w => !q || String(w.name).toLowerCase().includes(q) || String(w.id).toLowerCase().includes(q))
      .sort((a,b)=>String(a.name).localeCompare(String(b.name)));
    wsList.replaceChildren();
    for (const w of items){
      const row = document.createElement("div");
      row.className = "py-3 px-2 flex items-center justify-between hover:bg-slate-50 rounded-lg transition-colors";
      row.innerHTML = `
        <div class="flex-1 min-w-0">
          <div class="font-medium text-slate-800 truncate">${w.name}</div>
          <div class="text-xs text-slate-500 truncate">${w.id}</div>
        </div>
        <div class="text-right flex-shrink-0 ml-3">
          <div class="text-xs mb-1"><span class="pill">ver ${formatVersion(w.version)}</span></div>
          <button class="btn bg-slate-100 hover:bg-slate-200 text-slate-800 text-xs">
            <i class="fas fa-mouse-pointer text-xs"></i> Select
          </button>
        </div>
      `;
      row.querySelector("button").addEventListener("click", ()=>{
        wsSel.textContent = formatVersion(w.id);
        wsSel.title = "Full ID: " + w.id;
        wsId.value = w.id;
        wsName.value = w.name || "";
        wsIfMatch.value = w.version || "";
        wsInfo.value = JSON.stringify(w.info || {}, null, 2);
        wsContent.value = JSON.stringify(w.content || {}, null, 2);
        // trigger validation coloring
        wsInfo.dispatchEvent(new Event("input"));
        wsContent.dispatchEvent(new Event("input"));
      });
      wsList.appendChild(row);
    }
  }

  function renderServiceList(){
    const q = (svcSearch.value || "").toLowerCase();
    const tf = (typeFilter.value || "").toLowerCase();
    const items = cache.services
      .filter(s => (!q || String(s.name).toLowerCase().includes(q) || String(s.id).toLowerCase().includes(q)))
      .filter(s => (!tf || String(s.type).toLowerCase() === tf))
      .sort((a,b)=> (String(a.type)+a.name).localeCompare(String(b.type)+b.name));
    svcList.replaceChildren();
    for (const s of items){
      const row = document.createElement("div");
      row.className = "py-3 px-2 flex items-center justify-between hover:bg-slate-50 rounded-lg transition-colors";
      row.innerHTML = `
        <div class="flex-1 min-w-0">
          <div class="font-medium text-slate-800 truncate">${s.name} <span class="pill">${s.type}</span></div>
          <div class="text-xs text-slate-500 truncate">${s.id}</div>
        </div>
        <div class="text-right flex-shrink-0 ml-3">
          <div class="text-xs mb-1"><span class="pill">ver ${formatVersion(s.version)}</span></div>
          <button class="btn bg-slate-100 hover:bg-slate-200 text-slate-800 text-xs">
            <i class="fas fa-mouse-pointer text-xs"></i> Select
          </button>
        </div>
      `;
      row.querySelector("button").addEventListener("click", ()=>{
        svcSel.textContent = formatVersion(s.id);
        svcSel.title = "Full ID: " + s.id;
        svcId.value = s.id;
        svcName.value = s.name || "";
        svcType.value = s.type || "";
        svcIfMatch.value = s.version || "";
        svcInfo.value = JSON.stringify(s.info || {}, null, 2);
        svcContent.value = JSON.stringify(s.content || {}, null, 2);
        svcInfo.dispatchEvent(new Event("input"));
        svcContent.dispatchEvent(new Event("input"));
      });
      svcList.appendChild(row);
    }
  }

  // Link tab renderers
  function renderLinkWorkspaceList(){
    const q = (linkWsSearch.value || "").toLowerCase();
    const items = cache.workspaces
      .filter(w => !q || String(w.name).toLowerCase().includes(q) || String(w.id).toLowerCase().includes(q))
      .sort((a,b)=>String(a.name).localeCompare(String(b.name)));
    linkWsList.replaceChildren();
    for (const w of items){
      const row = document.createElement("div");
      row.className = "py-3 px-2 flex items-center justify-between hover:bg-slate-50 rounded-lg transition-colors";
      row.innerHTML = `
        <div class="flex-1 min-w-0">
          <div class="font-medium text-slate-800 truncate">${w.name}</div>
          <div class="text-xs text-slate-500 truncate">${w.id}</div>
        </div>
        <div class="text-right flex-shrink-0 ml-3">
          <div class="text-xs mb-1"><span class="pill">ver ${formatVersion(w.version)}</span></div>
          <button class="btn bg-slate-100 hover:bg-slate-200 text-slate-800 text-xs">
            <i class="fas fa-mouse-pointer text-xs"></i> Select
          </button>
        </div>
      `;
      row.querySelector("button").addEventListener("click", ()=>{
        selectedLinkWorkspaceId = w.id;
        linkWsSel.textContent = formatVersion(w.id);
        linkWsSel.title = "Full ID: " + w.id;
        linkWsVer.textContent = formatVersion(w.version) || "—";
        linkWsVer.title = "Full version: " + (w.version || "—");
        linkIfMatch.value = w.version || "";
        // Filter existing links by selected workspace
        renderLinkList();
      });
      linkWsList.appendChild(row);
    }
  }

  function renderLinkList(){
    linkList.replaceChildren();
    if (!selectedLinkWorkspaceId){
      const empty = document.createElement("div");
      empty.className = "text-slate-400 text-xs p-4 text-center";
      empty.innerHTML = '<i class="fas fa-inbox mb-2 text-2xl opacity-50"></i><div>Select a workspace to see its links.</div>';
      linkList.appendChild(empty);
      return;
    }
    const wsById = Object.fromEntries(cache.workspaces.map(w=>[w.id,w]));
    const svcById = Object.fromEntries(cache.services.map(s=>[s.id,s]));
    const items = cache.links.filter(l => l.workspace_id === selectedLinkWorkspaceId);
    if (!items.length){
      const empty = document.createElement("div");
      empty.className = "text-slate-400 text-xs p-4 text-center";
      empty.innerHTML = '<i class="fas fa-link-slash mb-2 text-2xl opacity-50"></i><div>No links in this workspace yet.</div>';
      linkList.appendChild(empty);
      return;
    }
    for (const l of items){
      const i = svcById[l.issuer_id];
      const a = svcById[l.audience_id];
      const row = document.createElement("div");
      row.className = "py-3 px-3 flex items-center justify-between border-b border-slate-100 last:border-b-0 hover:bg-slate-50 rounded";
      row.innerHTML = `
        <div class="flex-1 min-w-0">
          <div class="font-medium text-slate-800 text-sm">
            <span class="text-primary-600">${i?.name || formatVersion(l.issuer_id)}</span>
            <i class="fas fa-arrow-right mx-2 text-xs text-slate-400"></i>
            <span class="text-primary-600">${a?.name || formatVersion(l.audience_id)}</span>
          </div>
          <div class="text-[11px] text-slate-500 mt-1 truncate">
            ${formatVersion(l.issuer_id)} ➜ ${formatVersion(l.audience_id)}
          </div>
        </div>
        <div class="text-right flex-shrink-0 ml-3">
          <button class="btn bg-slate-100 hover:bg-slate-200 text-xs">
            <i class="fas fa-edit text-xs"></i> Edit
          </button>
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

  wsSearch.addEventListener("input", renderWorkspaceList);
  svcSearch.addEventListener("input", renderServiceList);
  typeFilter.addEventListener("change", renderServiceList);
  linkWsSearch.addEventListener("input", renderLinkWorkspaceList);

  // ------------- FETCH -------------
  function ensureKey(){ if(!key()){ alert("Sign in with an AUTHBRIDGE admin key first."); throw new Error("no key"); } }
  function fetchAll(first=false){
    try{ ensureKey(); }catch{return;}
    fetch("/admin/data", { headers: headers() })
      .then(r=>{ if(!r.ok) throw new Error("HTTP "+r.status); return r.json(); })
      .then(d=>{
        cache = d;
        setKpi(d);

        // Types
        svcType.replaceChildren();
        d.types.forEach(t => {
          const o = document.createElement("option");
          o.value = t; o.textContent = t;
          svcType.appendChild(o);
        });

        typeFilter.replaceChildren();
        const all = document.createElement("option"); all.value=""; all.textContent="All types";
        typeFilter.appendChild(all);
        d.types.forEach(t => {
          const o = document.createElement("option");
          o.value = t; o.textContent = t;
          typeFilter.appendChild(o);
        });

        // Populate link selects with all services (workspace selection is separate)
        setSelectOptions(linkIssuer, d.services, s=>({value:s.id, label:`${s.name} (${s.type})`}));
        setSelectOptions(linkAudience, d.services, s=>({value:s.id, label:`${s.name} (${s.type})`}));

        // Render lists
        renderWorkspaceList();
        renderServiceList();
        renderLinkWorkspaceList();
        renderLinkList();

        if (first) startLoop();
      })
      .catch(err => {
        systemLog.textContent = "Fetch failed: " + err.message + " (check admin key)";
      });
  }

  // ------------- HTTP helpers -------------
  function post(path, data, extraHeaders){
    return fetch(path, {
      method: "POST",
      headers: headers(Object.assign({"content-type":"application/json"}, extraHeaders||{})),
      body: data ? JSON.stringify(data) : null
    }).then(async r=>{
      const txt = await r.text();
      const payload = (txt && txt.startsWith("{")) ? JSON.parse(txt) : {raw:txt};
      if (!r.ok) { throw new Error((payload && payload.detail && (payload.detail.message || payload.detail.error_code)) || ("HTTP "+r.status)); }
      return payload;
    });
  }
  function put(path, data, extraHeaders){
    return fetch(path, {
      method: "PUT",
      headers: headers(Object.assign({"content-type":"application/json"}, extraHeaders||{})),
      body: data ? JSON.stringify(data) : null
    }).then(async r=>{
      const txt = await r.text();
      const payload = (txt && txt.startsWith("{")) ? JSON.parse(txt) : {raw:txt};
      if (!r.ok) { throw new Error((payload && payload.detail && (payload.detail.message || payload.detail.error_code)) || ("HTTP "+r.status)); }
      return payload;
    });
  }
  function del(path, extraHeaders){
    return fetch(path, {
      method: "DELETE",
      headers: headers(extraHeaders||{})
    }).then(async r=>{
      const txt = await r.text();
      const payload = (txt && txt.startsWith("{")) ? JSON.parse(txt) : {raw:txt};
      if (!r.ok) { throw new Error((payload && payload.detail && (payload.detail.message || payload.detail.error_code)) || ("HTTP "+r.status)); }
      return payload;
    });
  }

  // ------------- System actions -------------
  document.getElementById("rotateRsaBtn").addEventListener("click", ()=>{
    post("/api/v1/system/rotate-keys")
      .then(d=>{ logTo(systemLog, d); fetchAll(); })
      .catch(e=> logTo(systemLog, String(e)));
  });
  document.getElementById("reloadAdminBtn").addEventListener("click", ()=>{
    post("/api/v1/system/rotate")
      .then(d=> logTo(systemLog, d))
      .catch(e=> logTo(systemLog, String(e)));
  });

  // ------------- Workspace actions -------------
  wsCreateBtn.addEventListener("click", ()=>{
    try{
      assertJsonValid(wsInfo); assertJsonValid(wsContent);
      const payload = { id: wsId.value.trim(), name: wsName.value.trim() };
      const info = parseJSONOrEmpty(wsInfo.value); if (Object.keys(info).length) payload.info = info;
      const content = parseJSONOrEmpty(wsContent.value); if (Object.keys(content).length) payload.content = content;
      post("/api/v1/workspaces", payload)
        .then(d=>{ logTo(wsLog, d); fetchAll(); })
        .catch(e=> logTo(wsLog, String(e)));
    }catch(e){ logTo(wsLog, String(e)); }
  });

  wsUpdateInfoBtn.addEventListener("click", ()=>{
    try{
      assertJsonValid(wsInfo);
      const wid = encodeURIComponent(wsId.value.trim());
      const info = parseJSONOrEmpty(wsInfo.value);
      put(`/api/v1/workspaces/${wid}/info`, info, wsIfMatch.value ? {"If-Match": wsIfMatch.value.trim()} : {})
        .then(d=>{ logTo(wsLog, d); wsIfMatch.value = d.version || ""; fetchAll(); })
        .catch(e=> logTo(wsLog, String(e)));
    }catch(e){ logTo(wsLog, String(e)); }
  });

  wsUpdateContentBtn.addEventListener("click", ()=>{
    try{
      assertJsonValid(wsContent);
      const wid = encodeURIComponent(wsId.value.trim());
      const content = parseJSONOrEmpty(wsContent.value);
      put(`/api/v1/workspaces/${wid}/content`, content, wsIfMatch.value ? {"If-Match": wsIfMatch.value.trim()} : {})
        .then(d=>{ logTo(wsLog, d); wsIfMatch.value = d.version || ""; fetchAll(); })
        .catch(e=> logTo(wsLog, String(e)));
    }catch(e){ logTo(wsLog, String(e)); }
  });

  wsRekeyBtn.addEventListener("click", ()=>{
    const wid = encodeURIComponent(wsId.value.trim());
    put(`/api/v1/workspaces/${wid}/rekey`, null, wsIfMatch.value ? {"If-Match": wsIfMatch.value.trim()} : {})
      .then(d=>{ logTo(wsLog, d); wsIfMatch.value = d.version || ""; fetchAll(); })
      .catch(e=> logTo(wsLog, String(e)));
  });

  wsDeleteBtn.addEventListener("click", ()=>{
    const wid = encodeURIComponent(wsId.value.trim());
    if (!wid) { logTo(wsLog, "Workspace id is required."); return; }
    if (!confirm("Delete workspace and its links?")) return;
    del(`/api/v1/workspaces/${wid}`)
      .then(d=>{ logTo(wsLog, d); fetchAll(); })
      .catch(e=> logTo(wsLog, String(e)));
  });

  wsClearBtn.addEventListener("click", ()=>{
    wsSel.textContent = "—";
    wsSel.title = "Full ID: —";
    wsId.value = wsName.value = wsIfMatch.value = "";
    wsInfo.value = wsContent.value = "";
    wsInfo.dispatchEvent(new Event("input"));
    wsContent.dispatchEvent(new Event("input"));
  });

  // ------------- Service actions -------------
  svcCreateBtn.addEventListener("click", ()=>{
    try{
      assertJsonValid(svcInfo); assertJsonValid(svcContent);
      const payload = { id: svcId.value.trim(), name: svcName.value.trim(), type: (svcType.value||"unknown") };
      const info = parseJSONOrEmpty(svcInfo.value); if (Object.keys(info).length) payload.info = info;
      const content = parseJSONOrEmpty(svcContent.value); if (Object.keys(content).length) payload.content = content;
      post("/api/v1/services", payload)
        .then(d=>{ logTo(svcLog, d); fetchAll(); })
        .catch(e=> logTo(svcLog, String(e)));
    }catch(e){ logTo(svcLog, String(e)); }
  });

  svcRekeyBtn.addEventListener("click", ()=>{
    const sid = encodeURIComponent(svcId.value.trim());
    put(`/api/v1/services/${sid}/rekey`, null, svcIfMatch.value ? {"If-Match": svcIfMatch.value.trim()} : {})
      .then(d=>{ logTo(svcLog, d); svcIfMatch.value = d.version || ""; fetchAll(); })
      .catch(e=> logTo(svcLog, String(e)));
  });

  svcUpdateInfoBtn.addEventListener("click", ()=>{
    try{
      assertJsonValid(svcInfo);
      const sid = encodeURIComponent(svcId.value.trim());
      const info = parseJSONOrEmpty(svcInfo.value);
      put(`/api/v1/services/${sid}/info`, info, svcIfMatch.value ? {"If-Match": svcIfMatch.value.trim()} : {})
        .then(d=>{ logTo(svcLog, d); svcIfMatch.value = d.version || ""; fetchAll(); })
        .catch(e=> logTo(svcLog, String(e)));
    }catch(e){ logTo(svcLog, String(e)); }
  });

  svcUpdateContentBtn.addEventListener("click", ()=>{
    try{
      assertJsonValid(svcContent);
      const sid = encodeURIComponent(svcId.value.trim());
      const content = parseJSONOrEmpty(svcContent.value);
      put(`/api/v1/services/${sid}/content`, content, svcIfMatch.value ? {"If-Match": svcIfMatch.value.trim()} : {})
        .then(d=>{ logTo(svcLog, d); svcIfMatch.value = d.version || ""; fetchAll(); })
        .catch(e=> logTo(svcLog, String(e)));
    }catch(e){ logTo(svcLog, String(e)); }
  });

  svcDeleteBtn.addEventListener("click", ()=>{
    const sid = encodeURIComponent(svcId.value.trim());
    if (!sid) { logTo(svcLog, "Service id is required."); return; }
    if (!confirm("Delete service (and remove its links)?")) return;
    del(`/api/v1/services/${sid}`)
      .then(d=>{ logTo(svcLog, d); fetchAll(); })
      .catch(e=> logTo(svcLog, String(e)));
  });

  // ------------- Linking actions -------------
  function requireSelectedWorkspace(){
    if (!selectedLinkWorkspaceId){
      throw new Error("Select a workspace on the left first.");
    }
  }
  function postLink(action, wid, payload){
    return fetch(`/api/v1/workspaces/${wid}/${action}`, {
      method: "POST",
      headers: headers(Object.assign({"content-type":"application/json"}, linkIfMatch.value ? {"If-Match": linkIfMatch.value.trim()} : {})),
      body: JSON.stringify(payload)
    })
    .then(async r=>{
      const txt = await r.text();
      const data = (txt && txt.startsWith("{")) ? JSON.parse(txt) : {raw:txt};
      if (!r.ok) throw new Error((data && data.detail && (data.detail.message || data.detail.error_code)) || ("HTTP " + r.status));
      return data;
    });
  }

  linkBtn.addEventListener("click", ()=>{
    try{
      requireSelectedWorkspace();
      assertJsonValid(linkContext);
      const wid = encodeURIComponent(selectedLinkWorkspaceId);
      const payload = {
        issuer_id: linkIssuer.value,
        audience_id: linkAudience.value,
        context: parseJSONOrEmpty(linkContext.value)
      };
      postLink("link-service", wid, payload)
        .then(d=>{ logTo(linkLog, d); linkIfMatch.value = d.version || ""; fetchAll(); })
        .catch(e=> logTo(linkLog, String(e)));
    }catch(e){ logTo(linkLog, String(e)); }
  });

  unlinkBtn.addEventListener("click", ()=>{
    try{
      requireSelectedWorkspace();
      assertJsonValid(linkContext);
      const wid = encodeURIComponent(selectedLinkWorkspaceId);
      const payload = {
        issuer_id: linkIssuer.value,
        audience_id: linkAudience.value,
        context: parseJSONOrEmpty(linkContext.value)
      };
      postLink("unlink-service", wid, payload)
        .then(d=>{ logTo(linkLog, d); linkIfMatch.value = d.version || ""; fetchAll(); })
        .catch(e=> logTo(linkLog, String(e)));
    }catch(e){ logTo(linkLog, String(e)); }
  });

  // ------------- INIT -------------
  if (saved) fetchAll(true);
})();
</script>
</body>
</html>
"""


@router.get("/admin", response_class=HTMLResponse, include_in_schema=False)
async def admin_page() -> HTMLResponse:
    """
    Serves the single-page Admin Console with 4 tabs:
      - Workspaces
      - Services
      - Link Services (workspace-first, two-service linking)
      - System
    Authentication is done client-side by passing `x-api-key` to existing /api/v1 endpoints.
    """
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
    # Ensure fresh caches
    await reload_services()
    await reload_workspaces()

    # Services
    services: List[Dict[str, Any]] = []
    for s in caches.services.values():
        services.append(
            {
                "id": s.id,
                "name": s.name,
                "type": s.type or "unknown",
                "version": s.version,
                "info": s.info or {},
                "content": s.content or {},
            }
        )

    # Workspaces & links
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

    types = sorted(set(load_service_types()) | set([s["type"] for s in services]))

    payload = {
        "now": datetime.now(timezone.utc).isoformat(),
        "system": {
            "services_version": caches.service_sys_ver,
            "workspaces_version": caches.workspace_sys_ver,
        },
        "services": sorted(services, key=lambda x: (str(x["type"]).lower(), str(x["name"]).lower())),
        "workspaces": sorted(workspaces, key=lambda x: str(x["name"]).lower()),
        "links": links,
        "types": types,
    }
    return JSONResponse(payload)


@router.get("/admin/ready", response_class=PlainTextResponse, include_in_schema=False)
async def admin_ready() -> PlainTextResponse:
    """Simple readiness ping for this UI."""
    return PlainTextResponse("ok")
