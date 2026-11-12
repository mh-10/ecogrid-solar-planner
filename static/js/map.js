/**
 * static/js/map.js
 * Leaflet initialisation and map interaction logic for EcoGrid.
 *
 * Responsibilities:
 *   - Mount a Leaflet map centred on the continental US
 *   - On map click → fetch /api/solar-data → drop marker → update chart & UI
 *   - "Save Location" button → POST /api/locations → refresh saved list
 *   - Load and render the saved-locations list on startup
 *   - Clicking a saved item re-fetches and re-renders that location
 *   - DELETE button removes a location via the API
 */

/* ============================================================
   Constants & module-level state
   ============================================================ */
const MAP_CENTER   = [39.5, -98.35];   // geographic centre of the contiguous US
const MAP_ZOOM     = 4;
const API_BASE     = "/api";

let _map           = null;   // Leaflet map instance
let _activeMarker  = null;   // currently placed marker
let _selectedLat   = null;
let _selectedLon   = null;
let _lastPayload   = null;   // last /api/solar-data response

/* ============================================================
   Initialise Leaflet map
   ============================================================ */
function initMap() {
  _map = L.map("map", { zoomControl: true }).setView(MAP_CENTER, MAP_ZOOM);

  // OpenStreetMap tile layer
  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    attribution: '© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
    maxZoom: 18,
  }).addTo(_map);

  _map.on("click", onMapClick);
}

/* ============================================================
   Map click handler
   ============================================================ */
async function onMapClick(e) {
  const { lat, lng } = e.latlng;
  _selectedLat = lat;
  _selectedLon = lng;

  // Update coordinate display immediately
  setCoordDisplay(lat, lng);

  // Show spinner
  setSpinner(true);
  clearSolarChart();

  try {
    const capacity = getCapacityInput();
    const url = `${API_BASE}/solar-data?lat=${lat}&lon=${lng}&system_capacity=${capacity}`;
    const res  = await fetch(url);

    if (!res.ok) throw new Error(`Server error ${res.status}`);
    const data = await res.json();

    if (data.errors && data.errors.length) {
      throw new Error(data.errors.join("; "));
    }

    _lastPayload = data;
    const outputs = data.outputs;

    // Drop / move marker
    placeMarker(lat, lng, outputs.ac_annual);

    // Update chart
    renderSolarChart(outputs.ac_monthly, `${lat.toFixed(4)}, ${lng.toFixed(4)}`);

    // Update annual badge
    setAnnualBadge(outputs.ac_annual);

    // Enable save button
    document.getElementById("btn-save").disabled = false;

  } catch (err) {
    showToast(`Error: ${err.message}`, "error");
    console.error(err);
  } finally {
    setSpinner(false);
  }
}

/* ============================================================
   Marker management
   ============================================================ */
function placeMarker(lat, lon, annualKwh) {
  if (_activeMarker) _map.removeLayer(_activeMarker);

  const icon = L.divIcon({
    className: "",
    html: `<div style="
             width:18px; height:18px; border-radius:50%;
             background: #f59e0b; border: 3px solid #fff;
             box-shadow: 0 0 8px rgba(245,158,11,0.7);">
           </div>`,
    iconSize: [18, 18],
    iconAnchor: [9, 9],
  });

  _activeMarker = L.marker([lat, lon], { icon })
    .addTo(_map)
    .bindPopup(
      `<b>Solar Estimate</b><br>
       <small>${lat.toFixed(4)}, ${lon.toFixed(4)}</small><br>
       <span style="color:#f59e0b; font-weight:700;">
         ${annualKwh.toFixed(0)} kWh/yr
       </span>`
    )
    .openPopup();
}

/* ============================================================
   Save Location
   ============================================================ */
async function saveLocation() {
  if (_selectedLat === null || _selectedLon === null) return;

  const nameInput = document.getElementById("location-name");
  const name = nameInput.value.trim() || `Location (${_selectedLat.toFixed(3)}, ${_selectedLon.toFixed(3)})`;
  const capacity = getCapacityInput();

  document.getElementById("btn-save").disabled = true;

  try {
    const res = await fetch(`${API_BASE}/locations`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        name,
        latitude: _selectedLat,
        longitude: _selectedLon,
        system_capacity_kw: capacity,
      }),
    });

    if (!res.ok) throw new Error(`Server error ${res.status}`);
    const saved = await res.json();

    showToast(`✓ Saved "${saved.name}"`, "success");
    nameInput.value = "";
    loadSavedLocations();

  } catch (err) {
    showToast(`Save failed: ${err.message}`, "error");
    console.error(err);
  } finally {
    document.getElementById("btn-save").disabled = false;
  }
}

/* ============================================================
   Load & render saved locations list
   ============================================================ */
async function loadSavedLocations() {
  const listEl = document.getElementById("saved-locations");
  listEl.innerHTML = `<p class="empty-state">Loading…</p>`;

  try {
    const res = await fetch(`${API_BASE}/locations`);
    if (!res.ok) throw new Error(`Server error ${res.status}`);
    const locations = await res.json();

    if (locations.length === 0) {
      listEl.innerHTML = `<p class="empty-state">No saved locations yet.<br>Click the map to begin.</p>`;
      return;
    }

    listEl.innerHTML = "";
    locations.forEach((loc) => renderSavedItem(loc, listEl));

  } catch (err) {
    listEl.innerHTML = `<p class="empty-state">Failed to load.</p>`;
    console.error(err);
  }
}

function renderSavedItem(loc, container) {
  const item = document.createElement("div");
  item.className = "saved-item";
  item.dataset.id = loc.id;

  const kwh = loc.annual_kwh ? `${loc.annual_kwh.toFixed(0)} kWh/yr` : "—";

  item.innerHTML = `
    <div class="saved-item-info">
      <div class="saved-item-name" title="${loc.name}">${loc.name}</div>
      <div class="saved-item-kwh">☀ ${kwh}</div>
    </div>
    <button class="btn-delete" data-id="${loc.id}" title="Remove location">✕</button>
  `;

  // Click the row → re-fetch and show that location
  item.addEventListener("click", (e) => {
    if (e.target.classList.contains("btn-delete")) return;
    jumpToLocation(loc);
  });

  // Delete button
  item.querySelector(".btn-delete").addEventListener("click", async (e) => {
    e.stopPropagation();
    await deleteLocation(loc.id, loc.name);
  });

  container.appendChild(item);
}

/* Jump to a saved location: pan map + re-render chart */
async function jumpToLocation(loc) {
  _selectedLat = loc.latitude;
  _selectedLon = loc.longitude;

  setCoordDisplay(loc.latitude, loc.longitude);
  _map.setView([loc.latitude, loc.longitude], 8, { animate: true });

  if (loc.monthly_kwh && Array.isArray(loc.monthly_kwh)) {
    renderSolarChart(loc.monthly_kwh, loc.name);
    setAnnualBadge(loc.annual_kwh);
    placeMarker(loc.latitude, loc.longitude, loc.annual_kwh);
  } else {
    // Fetch fresh data if monthly breakdown is missing
    setSpinner(true);
    try {
      const res = await fetch(
        `${API_BASE}/solar-data?lat=${loc.latitude}&lon=${loc.longitude}&system_capacity=${loc.system_capacity_kw || 4}`
      );
      const data = await res.json();
      renderSolarChart(data.outputs.ac_monthly, loc.name);
      setAnnualBadge(data.outputs.ac_annual);
      placeMarker(loc.latitude, loc.longitude, data.outputs.ac_annual);
    } finally {
      setSpinner(false);
    }
  }
}

/* Delete a location via API then refresh the list */
async function deleteLocation(id, name) {
  try {
    const res = await fetch(`${API_BASE}/locations/${id}`, { method: "DELETE" });
    if (!res.ok) throw new Error(`Server error ${res.status}`);
    showToast(`Removed "${name}"`, "success");
    loadSavedLocations();
  } catch (err) {
    showToast(`Delete failed: ${err.message}`, "error");
    console.error(err);
  }
}

/* ============================================================
   UI helpers
   ============================================================ */
function setCoordDisplay(lat, lon) {
  const el = document.getElementById("coords-display");
  if (el) el.textContent = `${lat.toFixed(5)}, ${lon.toFixed(5)}`;
}

function setAnnualBadge(kwh) {
  const badge = document.getElementById("annual-badge");
  const val   = document.getElementById("annual-kwh-value");
  if (badge) badge.classList.remove("hidden");
  if (val)   val.textContent = `${(kwh || 0).toFixed(0)} kWh`;
}

function setSpinner(active) {
  const overlay = document.getElementById("spinner-overlay");
  if (!overlay) return;
  overlay.classList.toggle("active", active);
}

function getCapacityInput() {
  const el = document.getElementById("system-capacity");
  const v  = parseFloat(el ? el.value : "4");
  return isNaN(v) || v <= 0 ? 4 : v;
}

/* ============================================================
   Toast notifications
   ============================================================ */
function showToast(message, type = "info") {
  const container = document.getElementById("toast-container");
  if (!container) return;

  const toast = document.createElement("div");
  toast.className = `toast ${type}`;
  toast.textContent = message;
  container.appendChild(toast);

  setTimeout(() => {
    toast.style.transition = "opacity 0.3s";
    toast.style.opacity = "0";
    setTimeout(() => toast.remove(), 350);
  }, 3200);
}

/* ============================================================
   Data-source status badge
   ============================================================ */
async function checkDataSource() {
  const badge = document.getElementById("data-source-badge");
  if (!badge) return;
  try {
    const res  = await fetch("/api/status");
    const data = await res.json();
    if (data.mode === "live") {
      badge.textContent = "🟢 Live — NREL PVWatts v6";
      badge.style.borderColor = "#22c55e";
      badge.style.color       = "#22c55e";
    } else {
      badge.textContent = "🟡 Simulated data";
      badge.style.borderColor = "#f59e0b";
      badge.style.color       = "#f59e0b";
    }
    badge.title = data.message;
  } catch {
    badge.textContent = "⚠ Status unknown";
  }
}

/* ============================================================
   Boot — safe for both defer and inline loading
   ============================================================ */
function _boot() {
  initMap();
  loadSavedLocations();
  checkDataSource();

  // Wire up save button
  const saveBtn = document.getElementById("btn-save");
  if (saveBtn) saveBtn.addEventListener("click", saveLocation);
}

// With `defer`, DOMContentLoaded may already have fired by the time this
// script executes. The readyState guard handles both timing scenarios.
if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", _boot);
} else {
  _boot();
}
