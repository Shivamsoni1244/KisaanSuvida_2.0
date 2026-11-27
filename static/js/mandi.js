/**
 * static/js/mandi.js - Mandi Prices module UI logic
 *
 * Provides cascading filters (State → District → Market → Commodity),
 * dynamic current-price cards, historical summary, and a 15-day Chart.js
 * graph. All data is fetched from the /api/mandi/* endpoints; no prices
 * are hardcoded. Missing dates appear as gaps in the chart.
 */

(function () {
  "use strict";

  // ------------------------------------------------------------------
  // Defaults
  // ------------------------------------------------------------------
  const DEFAULTS = {
    statesUrl: "/api/mandi/states",
    districtsUrl: "/api/mandi/districts",
    marketsUrl: "/api/mandi/markets",
    commoditiesUrl: "/api/mandi/commodities",
    pricesUrl: "/api/mandi/prices",
    historyUrl: "/api/mandi/history",
    summaryUrl: "/api/mandi/summary",
    graphUrl: "/api/mandi/graph",
    syncUrl: "/api/mandi/sync",
    days: 15,
  };

  // ------------------------------------------------------------------
  // Elements
  // ------------------------------------------------------------------
  const $ = (id) => document.getElementById(id);

  const elFilterState = $("filterState");
  const elFilterDistrict = $("filterDistrict");
  const elFilterMarket = $("filterMarket");
  const elFilterCommodity = $("filterCommodity");
  const elBtnRefresh = $("btnRefresh");
  const elBtnSync = $("btnSync");

  const elPriceCards = $("priceCards");
  const elPriceEmpty = $("priceEmpty");
  const elPriceMin = $("priceMin");
  const elPriceMinDate = $("priceMinDate");
  const elPriceMax = $("priceMax");
  const elPriceMaxDate = $("priceMaxDate");
  const elPriceAvg = $("priceAvg");
  const elPriceAvgDate = $("priceAvgDate");
  const elPriceAvgLabel = $("priceAvgLabel");
  const elPriceEmptyMsg = $("priceEmptyMsg");

  const elSummaryCards = $("summaryCards");
  const elSummaryHigh = $("summaryHigh");
  const elSummaryHighDate = $("summaryHighDate");
  const elSummaryLow = $("summaryLow");
  const elSummaryLowDate = $("summaryLowDate");

  const elChartCard = $("chartCard");
  const elChartEmpty = $("chartEmpty");
  const elChartSubtitle = $("chartSubtitle");
  const elMetaSource = $("metaSource");
  const elMetaLastSync = $("metaLastSync");
  const elMetaRecordCount = $("metaRecordCount");
  const elMetaStale = $("metaStale");

  // ------------------------------------------------------------------
  // State
  // ------------------------------------------------------------------
  let chartInstance = null;
  let isLoading = false;
  let config = {};

  // ------------------------------------------------------------------
  // Helpers
  // ------------------------------------------------------------------
  function fmtMoney(value) {
    if (value === null || value === undefined) return "N/A";
    return Number(value).toFixed(2);
  }

  function fmtDate(value) {
    if (!value) return "--";
    const d = String(value);
    return d.length >= 10 ? d.slice(0, 10) : d;
  }

  function setDisabled(select, disabled) {
    if (!select) return;
    select.disabled = disabled;
    if (disabled) {
      select.innerHTML = "<option value=\"\">Select</option>";
      select.value = "";
    }
  }

  function populateSelect(select, items, placeholder) {
    if (!select) return;
    select.innerHTML = "<option value=\"\">" + (placeholder || "Select") + "</option>";
    (items || []).forEach(function (item) {
      const opt = new Option(item.name, item.name, false, false);
      select.add(opt);
    });
  }

  function showToast(message, category) {
    const container = document.getElementById("toastContainer");
    if (!container) return;
    const div = document.createElement("div");
    div.className = "alert-toast " + (category || "success");
    const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    svg.setAttribute("width", "18");
    svg.setAttribute("height", "18");
    svg.setAttribute("viewBox", "0 0 24 24");
    svg.setAttribute("fill", "none");
    svg.setAttribute("stroke", "currentColor");
    svg.setAttribute("stroke-width", "2.5");
    const polyline = document.createElementNS("http://www.w3.org/2000/svg", "polyline");
    polyline.setAttribute("points", "20 6 9 17 4 12");
    svg.appendChild(polyline);
    div.appendChild(svg);
    const span = document.createElement("span");
    span.textContent = message;
    div.appendChild(span);
    container.appendChild(div);
    setTimeout(function () {
      div.style.transition = "opacity 0.4s ease, transform 0.4s ease";
      div.style.opacity = "0";
      div.style.transform = "translateY(-10px)";
      setTimeout(function () { div.remove(); }, 400);
    }, 4000);
  }

  // ------------------------------------------------------------------
  // API fetch
  // ------------------------------------------------------------------
  async function fetchJson(url) {
    const resp = await fetch(url, {
      credentials: "same-origin",
      headers: { Accept: "application/json" },
    });
    if (!resp.ok) {
      const err = new Error("HTTP " + resp.status);
      err.status = resp.status;
      throw err;
    }
    return resp.json();
  }

  function buildQuery(params) {
    const qs = new URLSearchParams();
    Object.keys(params).forEach(function (key) {
      const value = params[key];
      if (value !== null && value !== undefined && value !== "") {
        qs.append(key, value);
      }
    });
    return qs.toString();
  }

  // ------------------------------------------------------------------
  // Filter cascading
  // ------------------------------------------------------------------
  async function loadStates() {
    setDisabled(elFilterDistrict, true);
    setDisabled(elFilterMarket, true);
    setDisabled(elFilterCommodity, true);
    try {
      const data = await fetchJson(config.statesUrl);
      const items = (data && data.data) || [];
      populateSelect(elFilterState, items, "Select a state");
    } catch (e) {
      console.error("Failed to load states", e);
      populateSelect(elFilterState, [], "Unable to load states");
      showToast("Unable to load states.", "error");
    }
  }

  async function loadDistricts() {
    const state = elFilterState.value;
    setDisabled(elFilterDistrict, !state);
    setDisabled(elFilterMarket, true);
    setDisabled(elFilterCommodity, true);
    elFilterMarket.value = "";
    elFilterCommodity.value = "";
    if (!state) {
      populateSelect(elFilterDistrict, [], "Select a district");
      populateSelect(elFilterMarket, [], "Select a market");
      populateSelect(elFilterCommodity, [], "Select a crop");
      return;
    }
    try {
      const data = await fetchJson(config.districtsUrl + "?" + buildQuery({ state: state }));
      const items = (data && data.data) || [];
      populateSelect(elFilterDistrict, items, "Select a district");
    } catch (e) {
      console.error("Failed to load districts", e);
      populateSelect(elFilterDistrict, [], "Unable to load districts");
      showToast("Unable to load districts.", "error");
    }
  }

  async function loadMarkets() {
    const state = elFilterState.value;
    const district = elFilterDistrict.value;
    setDisabled(elFilterMarket, !(state && district));
    setDisabled(elFilterCommodity, true);
    elFilterCommodity.value = "";
    if (!(state && district)) {
      populateSelect(elFilterMarket, [], "Select a market");
      populateSelect(elFilterCommodity, [], "Select a crop");
      return;
    }
    try {
      const data = await fetchJson(
        config.marketsUrl + "?" + buildQuery({ state: state, district: district })
      );
      const items = (data && data.data) || [];
      populateSelect(elFilterMarket, items, "Select a market");
    } catch (e) {
      console.error("Failed to load markets", e);
      populateSelect(elFilterMarket, [], "Unable to load markets");
      showToast("Unable to load markets.", "error");
    }
  }

  async function loadCommodities() {
    const state = elFilterState.value;
    const district = elFilterDistrict.value;
    const market = elFilterMarket.value;
    setDisabled(elFilterCommodity, !(state && district && market));
    if (!(state && district && market)) {
      populateSelect(elFilterCommodity, [], "Select a crop");
      return;
    }
    try {
      const data = await fetchJson(
        config.commoditiesUrl +
        "?" +
        buildQuery({ state: state, district: district, market: market })
      );
      const items = (data && data.data) || [];
      populateSelect(elFilterCommodity, items, "Select a crop");
    } catch (e) {
      console.error("Failed to load commodities", e);
      populateSelect(elFilterCommodity, [], "Unable to load crops");
      showToast("Unable to load crops.", "error");
    }
  }

  // ------------------------------------------------------------------
  // Data loading
  // ------------------------------------------------------------------
  function setLoading(loading) {
    isLoading = loading;
    [elFilterState, elFilterDistrict, elFilterMarket, elFilterCommodity].forEach(function (s) {
      if (s) s.disabled = loading || !s.value;
    });
    if (elBtnRefresh) elBtnRefresh.disabled = loading;
    if (elBtnSync) elBtnSync.disabled = loading;
    const root = document.querySelector(".mandi-page");
    if (root) {
      if (loading) root.classList.add("loading");
      else root.classList.remove("loading");
    }
  }

  function renderPrices(data) {
    const records = (data && data.data) || [];
    const latestDate = data.latest_date || null;
    const source = data.source || null;
    const stale = data.stale === true;

    if (!records.length) {
      elPriceCards.style.display = "none";
      elPriceEmpty.style.display = "flex";
      elPriceEmptyMsg.textContent =
        data.message || "No price records available for the selected combination.";
      elSummaryCards.style.display = "none";
      elChartCard.style.display = "none";
      elChartEmpty.style.display = "flex";
      updateMeta(source, latestDate, stale);
      return;
    }

    // Latest record = first record (ordered by arrival_date desc).
    const latest = records[0];
    const minPrice = latest.min_price;
    const maxPrice = latest.max_price;
    const modalPrice = latest.modal_price;
    const arrivalDate = latest.arrival_date;

    elPriceCards.style.display = "grid";
    elPriceEmpty.style.display = "none";

    // Min price card
    elPriceMin.textContent = minPrice !== null ? fmtMoney(minPrice) : "N/A";
    elPriceMinDate.textContent = fmtDate(arrivalDate);
    if (minPrice === null) {
      elPriceMin.classList.add("price-card-unavailable");
      elPriceMin.textContent = "Unavailable";
    } else {
      elPriceMin.classList.remove("price-card-unavailable");
    }

    // Max price card
    elPriceMax.textContent = maxPrice !== null ? fmtMoney(maxPrice) : "N/A";
    elPriceMaxDate.textContent = fmtDate(arrivalDate);
    if (maxPrice === null) {
      elPriceMax.classList.add("price-card-unavailable");
      elPriceMax.textContent = "Unavailable";
    } else {
      elPriceMax.classList.remove("price-card-unavailable");
    }

    // Average / Modal price card
    const hasModal = modalPrice !== null;
    elPriceAvgLabel.textContent = hasModal ? "Modal Price" : "Average (Calculated)";
    if (hasModal) {
      elPriceAvg.textContent = fmtMoney(modalPrice);
      elPriceAvg.classList.remove("price-card-unavailable");
    } else {
      // Calculated midpoint when both min and max exist.
      if (minPrice !== null && maxPrice !== null) {
        elPriceAvg.textContent = fmtMoney((minPrice + maxPrice) / 2);
      } else {
        elPriceAvg.textContent = "Unavailable";
        elPriceAvg.classList.add("price-card-unavailable");
      }
    }
    elPriceAvgDate.textContent = fmtDate(arrivalDate);

    updateMeta(source, latestDate, stale);
  }

  function updateMeta(source, latestDate, stale) {
    if (elMetaSource) elMetaSource.textContent = source || "data.gov.in AGMARKNET";
    if (elMetaLastSync) elMetaLastSync.textContent = latestDate ? "Reported " + fmtDate(latestDate) : "--";
    if (elMetaStale) {
      elMetaStale.style.display = stale ? "inline-flex" : "none";
    }
  }

  async function loadSummary(params) {
    try {
      const data = await fetchJson(config.summaryUrl + "?" + buildQuery(params));
      const summary = (data && data.data) || {};
      elSummaryCards.style.display = "grid";
      elSummaryHigh.textContent = summary.highest_max_price !== null ? fmtMoney(summary.highest_max_price) : "N/A";
      elSummaryHighDate.textContent = fmtDate(summary.highest_max_date);
      if (summary.highest_max_price === null) {
        elSummaryHigh.textContent = "Unavailable";
        elSummaryHigh.classList.add("price-card-unavailable");
      } else {
        elSummaryHigh.classList.remove("price-card-unavailable");
      }
      elSummaryLow.textContent = summary.lowest_min_price !== null ? fmtMoney(summary.lowest_min_price) : "N/A";
      elSummaryLowDate.textContent = fmtDate(summary.lowest_min_date);
      if (summary.lowest_min_price === null) {
        elSummaryLow.textContent = "Unavailable";
        elSummaryLow.classList.add("price-card-unavailable");
      } else {
        elSummaryLow.classList.remove("price-card-unavailable");
      }
    } catch (e) {
      console.error("Failed to load summary", e);
      elSummaryCards.style.display = "none";
    }
  }

  async function loadGraph(params) {
    try {
      const data = await fetchJson(config.graphUrl + "?" + buildQuery(params));
      const graph = (data && data.data) || {};
      renderChart(graph);
    } catch (e) {
      console.error("Failed to load graph", e);
      elChartCard.style.display = "none";
      elChartEmpty.style.display = "flex";
    }
  }

  function renderChart(graph) {
    const labels = graph.labels || [];
    const datasets = graph.datasets || {};
    const maxPrices = datasets.max_price || [];
    const minPrices = datasets.min_price || [];
    const thirdPrices = datasets.modal_price || [];
    const thirdLabel = graph.third_label || "Modal Price";
    const recordCount = graph.record_count || 0;

    if (!labels.length || recordCount === 0) {
      elChartCard.style.display = "none";
      elChartEmpty.style.display = "flex";
      return;
    }

    elChartCard.style.display = "block";
    elChartEmpty.style.display = "none";
    elChartSubtitle.textContent =
      "Maximum, minimum and " + thirdLabel.toLowerCase() + " prices for the selected crop and mandi.";

    const ctx = document.getElementById("mandiChart");
    if (!ctx) return;

    if (chartInstance) {
      chartInstance.destroy();
      chartInstance = null;
    }

    Chart.defaults.color = "#54665a";
    Chart.defaults.font.family = "'DM Sans', sans-serif";
    Chart.defaults.font.size = 11;

    chartInstance = new Chart(ctx, {
      type: "line",
      data: {
        labels: labels,
        datasets: [
          {
            label: "Maximum Price",
            data: maxPrices,
            borderColor: "#991b1b",
            backgroundColor: "rgba(153, 27, 27, 0.12)",
            fill: false,
            tension: 0,
            pointRadius: 3,
            pointHoverRadius: 6,
            pointBackgroundColor: "#991b1b",
            pointBorderColor: "#ffffff",
            pointBorderWidth: 2,
            spanGaps: false,
          },
          {
            label: "Minimum Price",
            data: minPrices,
            borderColor: "#2d6a4f",
            backgroundColor: "rgba(45, 106, 79, 0.12)",
            fill: false,
            tension: 0,
            pointRadius: 3,
            pointHoverRadius: 6,
            pointBackgroundColor: "#2d6a4f",
            pointBorderColor: "#ffffff",
            pointBorderWidth: 2,
            spanGaps: false,
          },
          {
            label: thirdLabel,
            data: thirdPrices,
            borderColor: "#153a25",
            backgroundColor: "rgba(21, 58, 37, 0.12)",
            fill: false,
            tension: 0,
            pointRadius: 3,
            pointHoverRadius: 6,
            pointBackgroundColor: "#153a25",
            pointBorderColor: "#ffffff",
            pointBorderWidth: 2,
            spanGaps: false,
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        interaction: {
          mode: "nearest",
          axis: "x",
          intersect: false,
        },
        plugins: {
          legend: {
            display: true,
            position: "top",
            labels: { font: { size: 12 }, color: "#13251a", padding: 16, boxWidth: 14 },
          },
          tooltip: {
            backgroundColor: "rgba(255, 255, 255, 0.95)",
            titleColor: "#13251a",
            bodyColor: "#54665a",
            borderColor: "#e5ece6",
            borderWidth: 1,
            cornerRadius: 8,
            displayColors: false,
            padding: 10,
            callbacks: {
              label: function (context) {
                const val = context.parsed.y;
                if (val === null || val === undefined) return null;
                return context.dataset.label + ": ₹" + Number(val).toFixed(2) + " / quintal";
              },
            },
          },
        },
        scales: {
          x: {
            title: { display: true, text: "Date", font: { size: 11, weight: "600" } },
            ticks: { font: { size: 9 }, maxRotation: 45, minRotation: 45 },
            grid: { display: false },
          },
          y: {
            title: { display: true, text: "Price (₹ / quintal)", font: { size: 11, weight: "600" } },
            ticks: { font: { size: 10 } },
            grid: { color: "rgba(0,0,0,0.06)", drawBorder: false },
            suggestedMin: 0,
          },
        },
        elements: {
          line: { borderWidth: 2, tension: 0 },
          point: { radius: 3, hoverRadius: 6, backgroundColor: "#ffffff", borderWidth: 2 },
        },
        animation: { duration: 400 },
      },
    });

    chartInstance.update();
  }

  // ------------------------------------------------------------------
  // Refresh all data
  // ------------------------------------------------------------------
  async function refreshData() {
    const state = elFilterState.value;
    const district = elFilterDistrict.value;
    const market = elFilterMarket.value;
    const commodity = elFilterCommodity.value;

    const params = {
      state: state || undefined,
      district: district || undefined,
      market: market || undefined,
      commodity: commodity || undefined,
      start_date: startDate,
      end_date: endDate,
      days: DEFAULTS.days,
    };

    try {
      setLoading(true);
      await Promise.all([
        fetchJson(config.pricesUrl + "?" + buildQuery(params)).then(renderPrices),
        loadSummary(params),
        loadGraph(params),
      ]);
    } catch (e) {
      console.error("Refresh failed", e);
      showToast("Failed to load price data. Using cached records if available.", "error");
    } finally {
      setLoading(false);
    }
  }

  // ------------------------------------------------------------------
  // Synchronisation
  // ------------------------------------------------------------------
  async function syncNow() {
    setLoading(true);
    let jobId = null;
    try {
      const resp = await fetch(config.syncUrl, {
        method: "POST",
        credentials: "same-origin",
        headers: {
          Accept: "application/json",
          "Content-Type": "application/json",
        },
        body: JSON.stringify({}),
      });
      let data = {};
      try {
        data = await resp.json();
      } catch (e) {
        data = {};
      }
      if (resp.status === 409) {
        showToast(data.message || "A synchronisation is already in progress.", "error");
        return;
      }
      if (!resp.ok) {
        showToast("Sync request failed (HTTP " + resp.status + ").", "error");
        return;
      }
      if (!data || !data.success) {
        showToast(
          "Sync failed: " + ((data && data.message) || (data && data.error) || "unknown error"),
          "error"
        );
        return;
      }
      jobId = data.job_id;
      showToast(data.message || "Synchronisation started in the background.", "success");
      await pollSyncStatus(jobId);
    } catch (e) {
      console.error("Sync error", e);
      showToast("Sync request failed.", "error");
    } finally {
      setLoading(false);
    }
  }

  async function pollSyncStatus(jobId) {
    if (!jobId) return;
    // Poll for up to ~2 minutes (60 x 2s).
    for (let i = 0; i < 60; i++) {
      await new Promise((resolve) => setTimeout(resolve, 2000));
      try {
        const resp = await fetch(
          config.syncUrl + "/status?job_id=" + encodeURIComponent(jobId),
          { credentials: "same-origin", headers: { Accept: "application/json" } }
        );
        if (!resp.ok) continue;
        const data = await resp.json();
        if (!data || !data.success) continue;
        const status = data.status;
        if (status === "completed") {
          showToast(
            "Sync completed: " + data.fetched + " records (" +
            data.inserted + " new, " + data.updated + " updated).",
            "success"
          );
          if (elMetaRecordCount) elMetaRecordCount.textContent = data.fetched || 0;
          await loadStates();
          return;
        }
        if (status === "failed") {
          showToast("Sync failed: " + (data.error || "unknown error"), "error");
          return;
        }
        // Still pending/running; keep polling.
      } catch (e) {
        console.error("Sync status poll error", e);
      }
    }
    showToast("Synchronisation is still running in the background.", "success");
  }

  // ------------------------------------------------------------------
  // Initialisation
  // ------------------------------------------------------------------
  function init(userConfig) {
    config = Object.assign({}, DEFAULTS, userConfig || {});

    // Wire cascading filters.
    elFilterState.addEventListener("change", function () {
      loadDistricts();
      refreshData();
    });
    elFilterDistrict.addEventListener("change", function () {
      loadMarkets();
      refreshData();
    });
    elFilterMarket.addEventListener("change", function () {
      loadCommodities();
      refreshData();
    });
    elFilterCommodity.addEventListener("change", refreshData);
    if (elBtnRefresh) elBtnRefresh.addEventListener("click", refreshData);
    if (elBtnSync) elBtnSync.addEventListener("click", syncNow);

    // Kick off.
    loadStates().then(refreshData);
  }

  // Expose public API.
  window.MandiPrices = { init: init };
})();
