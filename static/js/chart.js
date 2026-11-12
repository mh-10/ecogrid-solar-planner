/**
 * static/js/chart.js
 * Chart.js rendering module for EcoGrid.
 *
 * Exports:
 *   renderSolarChart(monthlyData, locationName) — draw / redraw the bar chart
 *   clearSolarChart()                           — destroy chart & reset UI
 */

const MONTH_LABELS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                       "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

let _chartInstance = null;   // holds the active Chart.js instance

/**
 * Draw (or redraw) the 12-month solar production bar chart.
 *
 * @param {number[]} monthlyData  - Array of 12 AC kWh values (Jan→Dec).
 * @param {string}   locationName - Display name shown in the chart heading.
 */
function renderSolarChart(monthlyData, locationName) {
  const container   = document.getElementById("chart-container");
  const placeholder = document.getElementById("chart-placeholder");
  const canvas      = document.getElementById("solar-chart");
  const heading     = document.getElementById("chart-location-label");

  // Show canvas, hide placeholder
  if (placeholder) placeholder.style.display = "none";
  if (container)   container.style.display   = "block";
  if (heading)     heading.textContent        = locationName || "Selected Location";

  // Destroy previous instance to avoid canvas reuse errors
  if (_chartInstance) {
    _chartInstance.destroy();
    _chartInstance = null;
  }

  // ------------------------------------------------------------------
  // Build amber→orange gradient fill
  // ------------------------------------------------------------------
  const ctx = canvas.getContext("2d");
  const gradient = ctx.createLinearGradient(0, 0, 0, canvas.clientHeight || 300);
  gradient.addColorStop(0,   "#f59e0b");   // amber-500 (top / peak bars)
  gradient.addColorStop(0.6, "#f97316");   // orange-500
  gradient.addColorStop(1,   "#ea580c");   // orange-600 (bottom)

  // ------------------------------------------------------------------
  // Chart.js configuration
  // ------------------------------------------------------------------
  _chartInstance = new Chart(ctx, {
    type: "bar",
    data: {
      labels: MONTH_LABELS,
      datasets: [{
        label: "AC Output (kWh)",
        data: monthlyData,
        backgroundColor: gradient,
        borderColor: "rgba(249, 115, 22, 0.6)",
        borderWidth: 1,
        borderRadius: 4,
        borderSkipped: false,
      }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      animation: { duration: 500, easing: "easeOutQuart" },
      plugins: {
        legend: { display: false },
        tooltip: {
          backgroundColor: "#1e293b",
          titleColor: "#94a3b8",
          bodyColor: "#e2e8f0",
          borderColor: "#334155",
          borderWidth: 1,
          padding: 10,
          callbacks: {
            title: (items) => MONTH_LABELS[items[0].dataIndex],
            label: (item) => ` ${item.parsed.y.toFixed(1)} kWh`,
          },
        },
      },
      scales: {
        x: {
          grid:  { color: "rgba(51, 65, 85, 0.5)" },
          ticks: { color: "#94a3b8", font: { size: 12 } },
        },
        y: {
          beginAtZero: true,
          grid:  { color: "rgba(51, 65, 85, 0.5)" },
          ticks: {
            color: "#94a3b8",
            font: { size: 12 },
            callback: (v) => `${v} kWh`,
          },
          title: {
            display: true,
            text: "Energy Output (kWh)",
            color: "#64748b",
            font: { size: 11 },
          },
        },
      },
    },
  });
}

/**
 * Destroy the active chart and reset the UI to its placeholder state.
 */
function clearSolarChart() {
  if (_chartInstance) {
    _chartInstance.destroy();
    _chartInstance = null;
  }
  const container   = document.getElementById("chart-container");
  const placeholder = document.getElementById("chart-placeholder");
  const heading     = document.getElementById("chart-location-label");

  if (container)   container.style.display   = "none";
  if (placeholder) placeholder.style.display = "flex";
  if (heading)     heading.textContent        = "—";
}
