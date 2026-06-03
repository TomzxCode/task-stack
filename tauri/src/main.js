"use strict";

const { invoke } = window.__TAURI__.core;
const { listen } = window.__TAURI__.event;

const ROW_HEIGHT = 28;
const URL_RE = /https?:\/\/[^\s<>"')\]]+/g;

// ---------------------------------------------------------------------------
// State
// ---------------------------------------------------------------------------

let tasks = []; // Array<TaskView>
let selected = new Set();
let lastSelectedKey = "";
let anchor = null;
let cursor = null;
let descShownFor = null;
let editingIndex = null;
let filterText = "";
let visibleIndices = [];
let placeholderActive = false;

let drag = null; // { startIdx, startRowY, moved }

const entryEl = document.getElementById("entry");
const listEl = document.getElementById("list");
const descPanel = document.getElementById("desc-panel");
const descEl = document.getElementById("desc");
const helpOverlay = document.getElementById("help-overlay");

const isMac = navigator.platform.toLowerCase().includes("mac");

// ---------------------------------------------------------------------------
// Formatting (ports of stack.format_timestamp / format_duration)
// ---------------------------------------------------------------------------

const pad2 = (n) => String(n).padStart(2, "0");

function fmtTimestamp(epoch, nowEpoch) {
  if (epoch == null) return "—";
  const d = new Date(epoch * 1000);
  const n = new Date(nowEpoch * 1000);
  if (d.getFullYear() !== n.getFullYear())
    return `${d.getFullYear()}-${pad2(d.getMonth() + 1)}-${pad2(d.getDate())} ${pad2(d.getHours())}:${pad2(d.getMinutes())}`;
  if (d.getMonth() !== n.getMonth())
    return `${pad2(d.getMonth() + 1)}-${pad2(d.getDate())} ${pad2(d.getHours())}:${pad2(d.getMinutes())}`;
  if (d.getDate() !== n.getDate())
    return `${pad2(d.getDate())} ${pad2(d.getHours())}:${pad2(d.getMinutes())}`;
  if (d.getHours() !== n.getHours())
    return `${pad2(d.getHours())}:${pad2(d.getMinutes())}`;
  return pad2(d.getMinutes());
}

function fmtDuration(seconds) {
  if (seconds == null) return "—";
  let total = Math.floor(seconds);
  if (total < 0) total = 0;
  const sec = total % 60;
  let minutes = Math.floor(total / 60);
  const m = minutes % 60;
  let hours = Math.floor(minutes / 60);
  const h = hours % 24;
  let days = Math.floor(hours / 24);
  const d = days % 7;
  const weeks = Math.floor(days / 7);
  if (weeks > 0) return `${weeks}w ${d}d`;
  if (days > 0) return `${days}d ${pad2(h)}h`;
  if (hours > 0) return `${hours}h ${pad2(m)}m`;
  return `${m}m ${pad2(sec)}s`;
}

function liveDuration(task, nowEpoch) {
  if (task.is_current && task.last_current_epoch != null) {
    const elapsed = nowEpoch - task.last_current_epoch;
    return task.duration_seconds + Math.max(0, elapsed);
  }
  return task.duration_seconds;
}

function fuzzyMatch(query, text) {
  if (!query) return true;
  const q = query.toLowerCase();
  const t = text.toLowerCase();
  let i = 0;
  for (const ch of t) {
    if (ch === q[i]) {
      i += 1;
      if (i === q.length) return true;
    }
  }
  return false;
}

// ---------------------------------------------------------------------------
// Rendering
// ---------------------------------------------------------------------------

const HANDLE_SVG =
  '<svg width="12" height="20" viewBox="0 0 12 20"><line x1="1" y1="7" x2="11" y2="7"/><line x1="1" y1="10" x2="11" y2="10"/><line x1="1" y1="13" x2="11" y2="13"/></svg>';

function selectionKey() {
  return [...selected].sort((a, b) => a - b).join(",");
}

function render() {
  const nowEpoch = Date.now() / 1000;

  if (filterText) {
    visibleIndices = [];
    tasks.forEach((t, idx) => {
      if (fuzzyMatch(filterText, t.text)) visibleIndices.push(idx);
    });
  } else {
    visibleIndices = tasks.map((_, idx) => idx);
  }

  listEl.innerHTML = "";

  if (tasks.length === 0) {
    const e = document.createElement("div");
    e.className = "empty";
    e.textContent = "No tasks — type above and press Enter";
    listEl.appendChild(e);
  } else if (visibleIndices.length === 0) {
    const e = document.createElement("div");
    e.className = "empty";
    e.textContent = "No matching tasks";
    listEl.appendChild(e);
  } else {
    for (const i of visibleIndices) {
      const task = tasks[i];
      const row = document.createElement("div");
      row.className = "row";
      if (i === 0) row.classList.add("current");
      if (selected.has(i)) row.classList.add("selected");
      row.dataset.idx = String(i);

      const handle = document.createElement("span");
      handle.className = "handle";
      handle.innerHTML = HANDLE_SVG;
      row.appendChild(handle);

      const idx = document.createElement("span");
      idx.className = "idx";
      idx.textContent = String(i);
      row.appendChild(idx);

      const indicator = document.createElement("span");
      indicator.className = "indicator";
      indicator.textContent = i === 0 ? "🔥" : "💤";
      row.appendChild(indicator);

      const note = document.createElement("span");
      note.className = "note";
      note.textContent = task.description ? "📝" : "";
      row.appendChild(note);

      const text = document.createElement("span");
      text.className = "text";
      text.textContent = task.text;
      row.appendChild(text);

      const exec = document.createElement("span");
      exec.className = "col exec";
      exec.textContent = task.execution_count ? `×${task.execution_count}` : "—";
      row.appendChild(exec);

      const started = document.createElement("span");
      started.className = "col started";
      started.textContent = fmtTimestamp(task.started_epoch, nowEpoch);
      row.appendChild(started);

      const last = document.createElement("span");
      last.className = "col last";
      last.textContent = fmtTimestamp(task.last_current_epoch, nowEpoch);
      row.appendChild(last);

      const dur = document.createElement("span");
      dur.className = "col dur";
      dur.dataset.idx = String(i);
      dur.textContent = fmtDuration(liveDuration(task, nowEpoch));
      row.appendChild(dur);

      listEl.appendChild(row);
    }
  }

  // Selection-change handling: keep the entry in sync with a single selection
  // so it doubles as the edit field (mirrors window.py).
  const key = selectionKey();
  if (key !== lastSelectedKey) {
    lastSelectedKey = key;
    if (selected.size === 1) {
      const [sole] = selected;
      if (sole >= 0 && sole < tasks.length && editingIndex === null) {
        entryEl.value = tasks[sole].text;
        entryEl.select();
        filterText = "";
      }
    } else if (editingIndex === null) {
      entryEl.value = "";
      filterText = "";
    }
  }

  if (selected.size === 1) {
    const [sole] = selected;
    if (sole >= 0 && sole < tasks.length) {
      showDescPanel(sole);
      return;
    }
  }
  hideDescPanel();
}

// Update only the live duration cells (called every second).
function tickDurations() {
  const nowEpoch = Date.now() / 1000;
  for (const cell of listEl.querySelectorAll(".col.dur")) {
    const i = Number(cell.dataset.idx);
    const task = tasks[i];
    if (task) cell.textContent = fmtDuration(liveDuration(task, nowEpoch));
  }
}

// ---------------------------------------------------------------------------
// Description panel
// ---------------------------------------------------------------------------

function showDescPanel(idx) {
  if (descShownFor === idx) return;
  descShownFor = idx;
  const task = tasks[idx];
  if (task.description) {
    descEl.value = task.description;
    descEl.classList.remove("placeholder");
    placeholderActive = false;
  } else {
    descEl.value = "Add a description…";
    descEl.classList.add("placeholder");
    placeholderActive = true;
  }
  descPanel.classList.remove("hidden");
}

function hideDescPanel() {
  if (descShownFor === null) return;
  descShownFor = null;
  descPanel.classList.add("hidden");
}

async function saveDesc() {
  const idx = descShownFor;
  if (idx === null || idx < 0 || idx >= tasks.length) return;
  if (placeholderActive) return;
  const content = descEl.value.replace(/\n+$/, "");
  tasks = await invoke("update_description", { idx, description: content });
  descShownFor = null;
}

descEl.addEventListener("focus", () => {
  if (placeholderActive) {
    descEl.value = "";
    descEl.classList.remove("placeholder");
    placeholderActive = false;
  }
});
descEl.addEventListener("blur", () => {
  saveDesc();
});
descEl.addEventListener("keydown", (e) => {
  if (e.key === "Escape") {
    e.preventDefault();
    saveDesc().then(() => listEl.focus());
  }
});
// Ctrl/Cmd-click a URL inside the description to open it.
descEl.addEventListener("click", (e) => {
  const wantMod = isMac ? e.metaKey : e.ctrlKey;
  if (!wantMod) return;
  const pos = descEl.selectionStart;
  const text = descEl.value;
  let m;
  URL_RE.lastIndex = 0;
  while ((m = URL_RE.exec(text)) !== null) {
    if (pos >= m.index && pos <= m.index + m[0].length) {
      invoke("open_url", { url: m[0] });
      break;
    }
  }
});

// ---------------------------------------------------------------------------
// Entry field
// ---------------------------------------------------------------------------

async function submitEntry(position) {
  const text = entryEl.value.trim();
  let editIdx = editingIndex;
  if (editIdx === null && selected.size === 1) {
    const [sole] = selected;
    if (sole >= 0 && sole < tasks.length) editIdx = sole;
  }
  if (editIdx !== null) {
    if (!text) {
      cancelEdit();
      render();
      return;
    }
    tasks = await invoke("update_text", { idx: editIdx, text });
    editingIndex = null;
    if (editIdx >= 0 && editIdx < tasks.length) {
      selected = new Set([editIdx]);
      anchor = editIdx;
      cursor = editIdx;
    } else {
      selected = new Set();
      anchor = cursor = null;
    }
    lastSelectedKey = selectionKey();
    render();
    listEl.focus();
    return;
  }
  if (!text) return;
  entryEl.value = "";
  filterText = "";
  if (position === "next") tasks = await invoke("push_next", { text });
  else if (position === "last") tasks = await invoke("push_last", { text });
  else tasks = await invoke("push", { text });
  selected = new Set();
  anchor = cursor = null;
  render();
  listEl.focus();
}

function cancelEdit() {
  if (editingIndex === null) return;
  editingIndex = null;
  entryEl.value = "";
}

function beginEdit(idx) {
  if (idx < 0 || idx >= tasks.length) return;
  editingIndex = idx;
  selected = new Set([idx]);
  anchor = cursor = idx;
  entryEl.value = tasks[idx].text;
  entryEl.focus();
  entryEl.select();
  render();
}

entryEl.addEventListener("keydown", (e) => {
  if (e.key === "Enter") {
    if (e.shiftKey) {
      e.preventDefault();
      submitEntry("next");
    } else {
      submitEntry("first");
    }
    return;
  }
  if (e.key === "Home") {
    e.preventDefault();
    submitEntry("first");
    return;
  }
  if (e.key === "End") {
    e.preventDefault();
    submitEntry("last");
    return;
  }
  if (e.key === "Escape") {
    e.preventDefault();
    if (entryEl.value) {
      cancelEdit();
      entryEl.value = "";
      filterText = "";
      selected = new Set();
      anchor = cursor = null;
      lastSelectedKey = "";
      render();
    } else {
      listEl.focus();
    }
  }
});

entryEl.addEventListener("input", () => {
  if (editingIndex !== null || selected.size > 0) return;
  if (entryEl.value === filterText) return;
  filterText = entryEl.value;
  render();
});

// ---------------------------------------------------------------------------
// List keyboard navigation (port of window._on_key)
// ---------------------------------------------------------------------------

function setSingleSelection(idx) {
  anchor = idx;
  cursor = idx;
  selected = new Set([idx]);
}

function extendSelection(toIdx) {
  if (anchor === null) anchor = toIdx;
  cursor = toIdx;
  const lo = Math.min(anchor, cursor);
  const hi = Math.max(anchor, cursor);
  selected = new Set();
  for (let i = lo; i <= hi; i++) selected.add(i);
}

function digitFromEvent(e) {
  if (/^[0-9]$/.test(e.key)) return Number(e.key);
  if (e.code && /^Numpad[0-9]$/.test(e.code)) return Number(e.code.slice(6));
  return null;
}

listEl.addEventListener("keydown", async (e) => {
  // Enter: begin editing the single selected row.
  if (e.key === "Enter") {
    if (selected.size === 1) {
      const [sole] = selected;
      beginEdit(sole);
    }
    return;
  }

  // Digit selection.
  const digit = digitFromEvent(e);
  if (digit !== null) {
    e.preventDefault();
    const visible = visibleIndices.length ? visibleIndices : tasks.map((_, i) => i);
    if (digit < visible.length) {
      const real = visible[digit];
      await saveDesc();
      if (e.shiftKey) extendSelection(real);
      else setSingleSelection(real);
      render();
    }
    return;
  }

  if (e.key === "?") {
    e.preventDefault();
    showHelp();
    return;
  }

  if (e.key === "Escape") {
    e.preventDefault();
    if (!helpOverlay.classList.contains("hidden")) {
      closeHelp();
      return;
    }
    if (selected.size || filterText) {
      selected = new Set();
      anchor = cursor = null;
      if (editingIndex === null) {
        entryEl.value = "";
        filterText = "";
      }
      lastSelectedKey = "";
      render();
    } else {
      invoke("request_hide");
    }
    return;
  }

  // Printable character: redirect to entry (edit if single selection, else filter).
  if (e.key.length === 1 && !e.ctrlKey && !e.metaKey && !e.altKey) {
    e.preventDefault();
    if (selected.size === 1) {
      const [sole] = selected;
      beginEdit(sole);
      entryEl.value = e.key;
    } else {
      cancelEdit();
      entryEl.value = e.key;
      entryEl.focus();
      filterText = entryEl.value;
      if (selected.size) {
        selected = new Set();
        anchor = cursor = null;
        lastSelectedKey = "";
      }
      render();
    }
    entryEl.focus();
    return;
  }

  if (e.key === "ArrowUp" || e.key === "ArrowDown") {
    e.preventDefault();
    await saveDesc();
    const delta = e.key === "ArrowUp" ? -1 : 1;
    const visible = visibleIndices.length ? visibleIndices : tasks.map((_, i) => i);
    if (!visible.length) return;
    if (e.shiftKey) {
      if (anchor === null) {
        anchor = e.key === "ArrowDown" ? visible[0] : visible[visible.length - 1];
        cursor = anchor;
      }
      const cursorPos = cursor !== null ? cursor : anchor;
      let curV = visible.indexOf(cursorPos);
      if (curV < 0) curV = 0;
      const newV = Math.max(0, Math.min(visible.length - 1, curV + delta));
      extendSelection(visible[newV]);
    } else {
      let pos;
      if (!selected.size) {
        pos = e.key === "ArrowDown" ? visible[0] : visible[visible.length - 1];
      } else {
        const cur = cursor !== null ? cursor : Math.min(...selected);
        let curV = visible.indexOf(cur);
        if (curV < 0) curV = 0;
        const newV = Math.max(0, Math.min(visible.length - 1, curV + delta));
        pos = visible[newV];
      }
      setSingleSelection(pos);
    }
    render();
    return;
  }

  if (!selected.size) return;

  let sole = null;
  if (selected.size === 1) [sole] = selected;

  if (e.key === "ArrowLeft" || e.key === "ArrowRight") {
    if (sole === null) return;
    e.preventDefault();
    const delta = e.key === "ArrowLeft" ? -1 : 1;
    const newIdx = sole + delta;
    if (newIdx >= 0 && newIdx < tasks.length) {
      cancelEdit();
      tasks = await invoke("reorder", { fromIdx: sole, toIdx: newIdx });
      setSingleSelection(newIdx);
      render();
    }
    return;
  }

  if (e.key === "Home") {
    if (sole === null) return;
    e.preventDefault();
    cancelEdit();
    tasks = await invoke("promote", { idx: sole });
    selected = new Set();
    anchor = cursor = null;
    render();
    return;
  }

  if (e.key === "End") {
    if (sole === null) return;
    e.preventDefault();
    cancelEdit();
    tasks = await invoke("reorder", { fromIdx: sole, toIdx: tasks.length - 1 });
    selected = new Set();
    anchor = cursor = null;
    render();
    return;
  }

  if (e.key === "Backspace" || e.key === "Delete") {
    e.preventDefault();
    cancelEdit();
    const minDeleted = Math.min(...selected);
    tasks = await invoke("remove_many", { indices: [...selected] });
    hideDescPanel();
    lastSelectedKey = "";
    entryEl.value = "";
    if (tasks.length) {
      const next = Math.min(minDeleted, tasks.length - 1);
      setSingleSelection(next);
    } else {
      selected = new Set();
      anchor = cursor = null;
    }
    render();
    return;
  }
});

// ---------------------------------------------------------------------------
// Drag and drop (port of window._drag_*)
// ---------------------------------------------------------------------------

function rowAt(clientY) {
  const rect = listEl.getBoundingClientRect();
  const y = clientY - rect.top + listEl.scrollTop;
  if (!visibleIndices.length) {
    return Math.max(0, Math.min(tasks.length - 1, Math.floor(y / ROW_HEIGHT)));
  }
  const row = Math.max(0, Math.min(visibleIndices.length - 1, Math.floor(y / ROW_HEIGHT)));
  return visibleIndices[row];
}

listEl.addEventListener("mousedown", (e) => {
  if (e.button !== 0 || !tasks.length) return;
  saveDesc();
  listEl.focus();
  drag = { startIdx: rowAt(e.clientY), startRow: rowAt(e.clientY), moved: false };
});

document.addEventListener("mousemove", async (e) => {
  if (!drag || tasks.length < 2) return;
  const target = rowAt(e.clientY);
  if (target === drag.startIdx) return;
  cancelEdit();
  const src = drag.startIdx;
  let group;
  if (selected.has(src) && selected.size > 1) group = [...selected];
  else group = [src];

  const result = await invoke("reorder_group", {
    fromIndices: group,
    anchorIdx: src,
    targetIdx: target,
  });
  tasks = result.tasks;
  const map = new Map(result.index_map.map(([o, n]) => [o, n]));
  const remap = (i) => (map.has(i) ? map.get(i) : i);

  selected = new Set([...selected].map(remap));
  anchor = anchor !== null ? remap(anchor) : null;
  cursor = cursor !== null ? remap(cursor) : null;
  descShownFor = descShownFor !== null ? remap(descShownFor) : null;
  lastSelectedKey = selectionKey();
  drag.startIdx = remap(src);
  drag.moved = true;
  render();
});

document.addEventListener("mouseup", (e) => {
  if (!drag) return;
  if (!drag.moved) {
    const released = rowAt(e.clientY);
    if (e.shiftKey) extendSelection(released);
    else setSingleSelection(released);
    render();
  }
  drag = null;
});

// ---------------------------------------------------------------------------
// Help dialog
// ---------------------------------------------------------------------------

const HELP_ROWS = [
  ["Typing", "Focus entry and type"],
  ["Enter", "Add task to top  /  Save edit"],
  ["Shift+Enter", "Insert task after current"],
  ["Home", "Add task to top  /  Promote selected to top"],
  ["End", "Add task to bottom  /  Send selected to bottom"],
  ["0-9", "Select task by index"],
  ["Shift+0-9 / Shift+↑↓", "Extend selection (range)"],
  ["Shift+click", "Extend selection to clicked row"],
  ["Up / Down", "Move selection"],
  ["Left / Right", "Move selected task up / down one position"],
  ["Return", "Edit selected task"],
  ["Escape", "Cancel edit  /  Hide window"],
  ["Backspace / Del", "Delete selected task(s)"],
  ["?", "Show this help"],
];

function buildHelpTable() {
  const table = document.getElementById("help-table");
  table.innerHTML = "";
  for (const [key, desc] of HELP_ROWS) {
    const tr = document.createElement("tr");
    const k = document.createElement("td");
    k.className = "key";
    k.textContent = key;
    const d = document.createElement("td");
    d.textContent = desc;
    tr.appendChild(k);
    tr.appendChild(d);
    table.appendChild(tr);
  }
}

function showHelp() {
  buildHelpTable();
  helpOverlay.classList.remove("hidden");
}
function closeHelp() {
  helpOverlay.classList.add("hidden");
  listEl.focus();
}

document.getElementById("help-close").addEventListener("click", closeHelp);
helpOverlay.addEventListener("keydown", (e) => {
  if (e.key === "Escape" || e.key === "?") {
    e.preventDefault();
    closeHelp();
  }
});
helpOverlay.addEventListener("mousedown", (e) => {
  if (e.target === helpOverlay) closeHelp();
});

// ---------------------------------------------------------------------------
// Theme + settings
// ---------------------------------------------------------------------------

function applyTheme() {
  const dark = window.matchMedia("(prefers-color-scheme: dark)").matches;
  document.body.classList.toggle("dark", dark);
}

function applySettings(s) {
  let family = s.font_family;
  if (!family || family === "TkDefaultFont" || family === "TkFixedFont") {
    family = "system-ui, sans-serif";
  }
  document.documentElement.style.setProperty("--font-family", family);
  const size = s.font_size && s.font_size >= 6 && s.font_size <= 72 ? s.font_size : 11;
  document.documentElement.style.setProperty("--font-size", `${size}px`);
}

// ---------------------------------------------------------------------------
// Refresh + lifecycle
// ---------------------------------------------------------------------------

async function refresh() {
  tasks = await invoke("list_tasks");
  selected = new Set();
  anchor = cursor = null;
  descShownFor = null;
  cancelEdit();
  filterText = "";
  entryEl.value = "";
  lastSelectedKey = "";
  hideDescPanel();
  render();
}

async function init() {
  applyTheme();
  window
    .matchMedia("(prefers-color-scheme: dark)")
    .addEventListener("change", applyTheme);

  try {
    const s = await invoke("get_settings");
    applySettings(s);
  } catch (_) {}

  await refresh();
  listEl.focus();

  // Backend-driven events (tray actions, window show).
  listen("stack-changed", async () => {
    await refresh();
    listEl.focus();
  });
  listen("show-help", () => showHelp());

  // Live duration tick.
  setInterval(tickDurations, 1000);
}

window.addEventListener("DOMContentLoaded", init);
