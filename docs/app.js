/* Analogue 3D Settings — audit view
   ----------------------------------
   Single-page static viewer for collections/community-best/games.json.
   - Loads the JSON at runtime from the same GitHub repo (no build step).
   - Renders one row per cart with the sheet-derived setting (overclock),
     enriched metadata (genres/year/devs/tags/expansion_pak), and a
     direct link to the source spreadsheet row so a reviewer can spot-
     check against what the community originally wrote.
   - Filters are AND across blocks, OR within a block. Search matches
     title or cart ID (case-insensitive substring). */

const SHEET_ID  = "1SGo9l_NEzy0ESbWAgqOKAZSFJyXQhAAkZXZcSdZPeBA";
const SHEET_GID = "1975911248";
const COLLECTION_URL =
  "https://raw.githubusercontent.com/auntiepickle/Analogue3DSettings/main/collections/community-best/games.json";

const FILTER_FIELDS = [
  // [filterKey, valueExtractor, fallbackLabel]
  ["overclock",     (e) => e.settings?.hardware?.overclock,             "(none)"],
  ["genre",         (e) => e.metadata?.genres ?? [],                    "(none)"],
  ["tag",           (e) => e.metadata?.tags ?? [],                      "(none)"],
  ["expansion_pak", (e) => e.metadata?.expansion_pak ?? "(none)",       "(none)"],
  ["source_region", (e) => e.source?.observed_region ?? "(unknown)",    "(unknown)"],
];

const state = {
  games:    {},                          // cartId → entry
  rows:     [],                          // [entry, cartId]
  filters:  Object.fromEntries(FILTER_FIELDS.map(([k]) => [k, new Set()])),
  query:    "",
  sort:     "title",
};

// ---------- bootstrapping ----------

async function load() {
  const stats = $("stats");
  stats.textContent = "loading…";
  try {
    const r = await fetch(COLLECTION_URL, { cache: "no-cache" });
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    const j = await r.json();
    state.games = j.games || {};
  } catch (e) {
    stats.textContent = "fetch failed: " + e.message;
    return;
  }
  state.rows = Object.entries(state.games).map(([cid, e]) => ({ cart_id: cid, ...e }));
  buildFilterChips();
  bindControls();
  render();
}

// ---------- filter chips ----------

function buildFilterChips() {
  for (const [key, extract, fallback] of FILTER_FIELDS) {
    const counts = new Map();
    for (const e of state.rows) {
      const v = extract(e);
      const list = Array.isArray(v) ? (v.length ? v : [fallback]) : [v ?? fallback];
      for (const x of list) counts.set(x, (counts.get(x) || 0) + 1);
    }
    const container = $(`filter-${key}`);
    if (!container) continue;
    container.innerHTML = "";
    const items = [...counts.entries()].sort((a, b) => b[1] - a[1] || String(a[0]).localeCompare(String(b[0])));
    for (const [v, n] of items) {
      const chip = document.createElement("button");
      chip.type = "button";
      chip.className = "chip";
      chip.dataset.value = v;
      chip.innerHTML = `${escape(String(v))} <span class="chip-n">${n}</span>`;
      chip.addEventListener("click", () => {
        const set = state.filters[key];
        if (set.has(v)) set.delete(v); else set.add(v);
        chip.classList.toggle("active");
        render();
      });
      container.appendChild(chip);
    }
  }
}

function bindControls() {
  $("q").addEventListener("input", (ev) => { state.query = ev.target.value.trim().toLowerCase(); render(); });
  $("sort").addEventListener("change", (ev) => { state.sort = ev.target.value; render(); });
  $("reset").addEventListener("click", () => {
    state.query = "";  $("q").value = "";
    state.sort = "title";  $("sort").value = "title";
    Object.values(state.filters).forEach((s) => s.clear());
    document.querySelectorAll(".chip.active").forEach((el) => el.classList.remove("active"));
    render();
  });
}

// ---------- filtering + sort ----------

function passes(e) {
  if (state.query) {
    const hay = (e.title + " " + e.cart_id).toLowerCase();
    if (!hay.includes(state.query)) return false;
  }
  for (const [key, extract, fallback] of FILTER_FIELDS) {
    const pick = state.filters[key];
    if (!pick.size) continue;
    const v = extract(e);
    const got = Array.isArray(v) ? (v.length ? v : [fallback]) : [v ?? fallback];
    if (!got.some((g) => pick.has(g))) return false;
  }
  return true;
}

function sortRows(rows) {
  const t = state.sort;
  const cmp = (a, b) => {
    if (t === "title")      return a.title.localeCompare(b.title);
    if (t === "title_desc") return b.title.localeCompare(a.title);
    if (t === "year")       return (a.metadata?.release_year || 0) - (b.metadata?.release_year || 0);
    if (t === "year_desc")  return (b.metadata?.release_year || 0) - (a.metadata?.release_year || 0);
    if (t === "cart_id")    return a.cart_id.localeCompare(b.cart_id);
    return 0;
  };
  return [...rows].sort(cmp);
}

// ---------- render ----------

function render() {
  const filtered = state.rows.filter(passes);
  const ordered = sortRows(filtered);
  const body = $("grid-body");
  body.innerHTML = "";
  for (const e of ordered) body.appendChild(rowFor(e));
  $("stats").textContent = `${ordered.length} of ${state.rows.length} carts`;
  $("empty").classList.toggle("hidden", ordered.length > 0);
}

function rowFor(e) {
  const tr = document.createElement("tr");
  const overclock = e.settings?.hardware?.overclock || "—";
  const genres = (e.metadata?.genres || []).join(", ") || "—";
  const year = e.metadata?.release_year || "—";
  const devs = (e.metadata?.developers || []).join(", ") || "—";
  const tags = (e.metadata?.tags || []).join(", ");
  const ep = e.metadata?.expansion_pak;
  const epBadge = ep ? `<span class="ep ep-${ep}">${ep}</span>` : "";
  const rationale = e.source?.rationale || "";
  const caveats   = e.source?.caveats || "";
  const rationaleText = [rationale, caveats && `⚠ ${caveats}`].filter(Boolean).join(" · ");

  const sheetRow = e.source?.sheet_row;
  const sheetLink = sheetRow
    ? `<a href="https://docs.google.com/spreadsheets/d/${SHEET_ID}/edit?gid=${SHEET_GID}&range=A${sheetRow}:G${sheetRow}" target="_blank" rel="noopener">row ${sheetRow}</a>`
    : "—";

  tr.innerHTML = `
    <td class="mono cartid">${e.cart_id}</td>
    <td class="title">
      <div class="title-line">${escape(e.title)}</div>
      <div class="title-sub">${epBadge}${tags ? `<span class="tags">${escape(tags)}</span>` : ""}</div>
    </td>
    <td><span class="oc oc-${slug(overclock)}">${escape(overclock)}</span></td>
    <td class="muted">${escape(genres)}</td>
    <td class="muted">${escape(String(year))}</td>
    <td class="muted">${escape(devs)}</td>
    <td class="muted rat">${escape(rationaleText) || "—"}</td>
    <td class="src">${sheetLink}</td>
  `;
  return tr;
}

// ---------- util ----------

function $(id) { return document.getElementById(id); }
function escape(s) {
  return String(s ?? "")
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
}
function slug(s) { return String(s ?? "").toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, ""); }

load();
