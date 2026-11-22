/*
 * crop_suitability_analysis.js - Frontend logic for Crop Suitability Analysis
 * Handles crop search, category filtering, location cascading (via location.js),
 * form submission, and modern dashboard rendering with Chart.js.
 *
 * Consumes the centralized weather suitability API response contract:
 *   { success, crop, weather_analysis, ph_analysis, daily_assessments, overall, ... }
 * Each daily_assessment contains: date, status, score, avg_temperature, min_temperature,
 * max_temperature, avg_humidity, total_rainfall, avg_wind_speed, wind_direction,
 * condition, descriptions, classifications.
 */

(function () {
  const API_BASE = "/crop-suitability/api";

  // Chart.js instances (destroyed before recreating)
  let chartInstances = {};

  // ------------------------------------------------------------------
  // Number formatting helpers (round only for display)
  // ------------------------------------------------------------------
  function formatTemp(value) {
    if (value === null || value === undefined || isNaN(value)) return "--";
    return `${parseFloat(value).toFixed(1)}°C`;
  }

  function formatTempPlain(value) {
    if (value === null || value === undefined || isNaN(value)) return "--";
    return parseFloat(value).toFixed(1);
  }

  function formatHumidity(value) {
    if (value === null || value === undefined || isNaN(value)) return "--";
    return `${parseFloat(value).toFixed(0)}%`;
  }

  function formatRain(value) {
    if (value === null || value === undefined || isNaN(value)) return "--";
    return `${parseFloat(value).toFixed(1)} mm`;
  }

  function formatWind(value) {
    if (value === null || value === undefined || isNaN(value)) return "--";
    return `${parseFloat(value).toFixed(1)} m/s`;
  }

  function formatNumber(value) {
    if (value === null || value === undefined || isNaN(value)) return "--";
    return parseFloat(value).toFixed(1);
  }

  function formatScore(value) {
    if (value === null || value === undefined || isNaN(value)) return "--";
    return parseFloat(value).toFixed(1);
  }

  function formatDays(value) {
    if (value === null || value === undefined || isNaN(value)) return "--";
    return parseInt(value, 10);
  }

  function formatDate(value) {
    if (!value) return "--";
    try {
      return new Date(value).toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" });
    } catch (e) {
      return value;
    }
  }

  // ------------------------------------------------------------------
  // Classification -> CSS class mapping
  // ------------------------------------------------------------------
  function classificationClass(classification) {
    const c = (classification || "").toUpperCase();
    if (c === "GOOD") return "good";
    if (c === "SUSTAINABLE") return "sustainable";
    if (c === "MARGINAL") return "marginal";
    if (c === "BAD") return "bad";
    return "unknown";
  }

  function classificationLabel(classification) {
    const c = (classification || "").toUpperCase();
    if (c === "GOOD") return "Good";
    if (c === "SUSTAINABLE") return "Sustainable";
    if (c === "MARGINAL") return "Marginal";
    if (c === "BAD") return "Bad";
    return "Unknown";
  }

  function statusColor(status) {
    const s = (status || "").toUpperCase();
    if (s === "FAVOURABLE") return "green";
    if (s === "MODERATE") return "amber";
    if (s === "MARGINAL") return "amber";
    if (s === "UNFAVOURABLE") return "red";
    if (s === "INSUFFICIENT_DATA") return "grey";
    return "grey";
  }

  function statusBadgeClass(status) {
    const c = (status || "").toUpperCase();
    if (c === "GOOD" || c === "SUSTAINABLE") return "good";
    if (c === "MARGINAL") return "marginal";
    if (c === "BAD") return "bad";
    return "unknown";
  }

  // ------------------------------------------------------------------
  // Crop Search & Category
  // ------------------------------------------------------------------
  const cropSearchInput = document.getElementById("cropSearch");
  const categoryList = document.getElementById("categoryList");
  const cropResults = document.getElementById("cropResults");
  const cropHidden = document.getElementById("crop");
  const btnShowCategories = document.getElementById("btnShowCategories");

  let categoriesVisible = false;

  if (btnShowCategories) {
    btnShowCategories.addEventListener("click", function () {
      categoriesVisible = !categoriesVisible;
      categoryList.style.display = categoriesVisible ? "grid" : "none";
      cropResults.style.display = "none";
      cropSearchInput.value = "";
    });
  }

  if (categoryList) {
    categoryList.addEventListener("click", function (e) {
      const btn = e.target.closest(".cs-btn-category-outline");
      if (!btn) return;
      const cat = btn.getAttribute("data-category");
      if (!cat) return;
      fetchCropsByCategory(cat);
      categoriesVisible = false;
      categoryList.style.display = "none";
      cropSearchInput.value = "";
    });
  }

  if (cropSearchInput) {
    let searchTimeout;
    cropSearchInput.addEventListener("input", function () {
      const q = this.value.trim();
      clearTimeout(searchTimeout);
      if (q.length < 1) {
        cropResults.style.display = "none";
        return;
      }
      // User is typing a new query: clear any previously selected crop so a
      // stale value is not silently submitted if the user does not re-select.
      cropHidden.value = "";
      searchTimeout = setTimeout(() => {
        console.log('[crop_suitability] Searching for crops:', q);
        fetch(`${API_BASE}/crops/search?q=${encodeURIComponent(q)}`, {
          credentials: 'same-origin',
          headers: { 'Accept': 'application/json' },
        })
          .then((r) => {
            console.log('[crop_suitability] Search response status:', r.status, 'content-type:', r.headers.get('content-type'));
            const ct = r.headers.get('content-type') || '';
            if (r.status === 401) {
              throw new Error('authentication_required');
            }
            if (!r.ok) {
              throw new Error(`HTTP ${r.status}`);
            }
            if (!ct.includes('application/json')) {
              throw new Error('Received a non-JSON response (likely a login page). Please log in and try again.');
            }
            return r.json();
          })
          .then((data) => {
            console.log('[crop_suitability] Search response data:', data);
            if (!data.success) {
              throw new Error(data.message || "Search failed");
            }
            console.log('[crop_suitability] Rendering search results:', data.data);
            renderSearchResults(data.data || []);

            // Auto-populate hidden field if there's an exact match
            if (data.data && data.data.length === 1) {
              const exact = data.data[0].crop_name.toLowerCase() === q.toLowerCase();
              if (exact) {
                cropSearchInput.value = data.data[0].crop_name;
                cropHidden.value = data.data[0].crop_name;
              }
            }
          })
          .catch((err) => {
            console.error('[crop_suitability] Search error:', err);
            let message = 'Unable to load crops.';
            if (err.message === 'authentication_required') {
              message = 'Your session has expired. Please log in to search crops.';
            } else if (err.message) {
              message = `Unable to load crops: ${err.message}`;
            }
            cropResults.innerHTML = `<div class="cs-crop-result-item cs-crop-error">${message}</div>`;
            cropResults.style.display = "block";
          });
      }, 300);
    });

    document.addEventListener("click", function (e) {
      if (!cropSearchInput.contains(e.target) && !cropResults.contains(e.target)) {
        cropResults.style.display = "none";
      }
    });
  }

  function fetchCropsByCategory(category) {
    fetch(`${API_BASE}/crops/category/${encodeURIComponent(category)}`, {
      credentials: 'same-origin',
      headers: { 'Accept': 'application/json' },
    })
      .then((r) => {
        console.log('[crop_suitability] Category response status:', r.status, 'content-type:', r.headers.get('content-type'));
        const ct = r.headers.get('content-type') || '';
        if (r.status === 401) {
          throw new Error('authentication_required');
        }
        if (!r.ok) {
          throw new Error(`HTTP ${r.status}`);
        }
        if (!ct.includes('application/json')) {
          throw new Error('Received a non-JSON response (likely a login page). Please log in and try again.');
        }
        return r.json();
      })
      .then((data) => {
        if (!data.success) {
          throw new Error(data.message || "Failed to load crops");
        }
        renderSearchResults(data.data || [], true);
      })
      .catch((err) => {
        console.error('[crop_suitability] Category error:', err);
        let message = 'Unable to load crops.';
        if (err.message === 'authentication_required') {
          message = 'Your session has expired. Please log in to browse categories.';
        } else if (err.message) {
          message = err.message;
        }
        cropResults.innerHTML = `<div class="cs-crop-result-item cs-crop-error">${message}</div>`;
        cropResults.style.display = "block";
      });
  }

  function renderSearchResults(crops, isCategory = false) {
    if (!crops || crops.length === 0) {
      cropResults.innerHTML = '<div class="cs-crop-result-item">No crops found.</div>';
      cropResults.style.display = "block";
      return;
    }
    const html = crops
      .map(
        (c) => `
        <div class="cs-crop-result-item" data-crop="${c.crop_name}">
          <strong>${c.crop_name}</strong>
          ${isCategory ? `<span style="float:right;font-size:11px;color:var(--color-text-muted);">${c.category}</span>` : ""}
        </div>
      `
      )
      .join("");
    cropResults.innerHTML = html;
    cropResults.style.display = "block";

    cropResults.querySelectorAll(".cs-crop-result-item").forEach((item) => {
      item.addEventListener("click", function () {
        const name = this.getAttribute("data-crop");
        cropSearchInput.value = name;
        cropHidden.value = name;
        cropResults.style.display = "none";
      });
    });
  }

  // ------------------------------------------------------------------
  // Form Submission via AJAX
  // ------------------------------------------------------------------
  const form = document.getElementById("csForm");
  const resultsSection = document.getElementById("csResults");
  const analyzeBtn = document.getElementById("analyzeBtn");

  if (form) {
    form.addEventListener("submit", function (e) {
      e.preventDefault();

      const cropValue = (cropHidden && cropHidden.value.trim()) || "";
      if (!cropValue) {
        alert("Please select a valid crop from the search results before submitting.");
        return;
      }

      const formData = new FormData(form);

      analyzeBtn.disabled = true;
      analyzeBtn.innerHTML = '<span>Analyzing...</span><svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z"></path><line x1="12" y1="7" x2="12" y2="17"></line><line x1="12" y1="17" x2="12.01" y2="17"></line></svg>';

      fetch("/crop-suitability/", {
        method: "POST",
        body: formData,
        credentials: "same-origin",
      })
        .then((r) => {
          const ct = r.headers.get('content-type') || '';
          if (r.status === 401) {
            throw new Error('authentication_required');
          }
          if (!r.ok) {
            throw new Error(`HTTP ${r.status}`);
          }
          if (!ct.includes('application/json')) {
            throw new Error('Received a non-JSON response. Please log in and try again.');
          }
          return r.json();
        })
        .then((data) => {
          analyzeBtn.disabled = false;
          analyzeBtn.innerHTML = '<span>Analyse crop suitability</span><svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><line x1="5" y1="12" x2="19" y2="12"></line><polyline points="12 5 19 12 12 19"></polyline></svg>';

          if (!data.success) {
            alert(data.message || "Analysis failed. Please try again.");
            return;
          }

          renderResults(data);
        })
        .catch((err) => {
          analyzeBtn.disabled = false;
          analyzeBtn.innerHTML = '<span>Analyse crop suitability</span><svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><line x1="5" y1="12" x2="19" y2="12"></line><polyline points="12 5 19 12 12 19"></polyline></svg>';
          let message = "Analysis failed. Please check your connection and try again.";
          if (err && err.message === 'authentication_required') {
            message = "Your session has expired. Please log in and try again.";
          } else if (err && err.message) {
            message = err.message;
          }
          alert(message);
          console.error('[crop_suitability] Analysis error:', err);
        });
    });
  }

  // ------------------------------------------------------------------
  // Result rendering
  // ------------------------------------------------------------------
  function renderResults(data) {
    resultsSection.style.display = "block";
    resultsSection.scrollIntoView({ behavior: "smooth" });

    const crop = data.crop || {};
    const weather = data.weather_analysis || {};
    const ph = data.ph_analysis || {};
    const overall = data.overall || {};
    const dailyAssessments = data.daily_assessments || [];

    // Dashboard header
    document.getElementById("dashCropName").textContent = crop.name || "Unknown Crop";
    document.getElementById("dashCropSub").textContent = (data.crop && data.crop.category) || "";
    const locParts = [
      data.location && data.location.village || data.location && data.location.name,
      data.location && data.location.tehsil,
      data.location && data.location.district,
      data.location && data.location.state,
    ].filter(Boolean);
    document.getElementById("dashLocation").textContent = locParts.join(", ");
    const fp = data.forecast_period || {};
    document.getElementById("dashPeriod").textContent =
      (fp.start && fp.end ? `${fp.start} to ${fp.end}` : "7-day forecast") +
      " | " + (fp.source || "openweathermap");

    // Summary cards — computed from daily assessments (source of truth: seven days)
    const dailyAssessmentsForCounts = data.daily_assessments || [];
    const dayStatuses = dailyAssessmentsForCounts.map((d) => (d.status || "UNKNOWN").toUpperCase());
    const goodCount = dayStatuses.filter((s) => s === "GOOD").length;
    const sustainableCount = dayStatuses.filter((s) => s === "SUSTAINABLE").length;
    const marginalCount = dayStatuses.filter((s) => s === "MARGINAL").length;
    const badCount = dayStatuses.filter((s) => s === "BAD").length;
    const poorCount = badCount + marginalCount;
    const totalAnalysedDays = dayStatuses.filter((s) => s !== "UNKNOWN").length;

    // Compute weekly averages/totals from daily assessments
    const humidityValues = dailyAssessmentsForCounts.map((d) => d.avg_humidity).filter((v) => v !== null && v !== undefined && !isNaN(v));
    const rainfallValues = dailyAssessmentsForCounts.map((d) => d.total_rainfall).filter((v) => v !== null && v !== undefined && !isNaN(v));
    const windValues = dailyAssessmentsForCounts.map((d) => d.avg_wind_speed).filter((v) => v !== null && v !== undefined && !isNaN(v));
    const avgHumidity = humidityValues.length > 0 ? (humidityValues.reduce((a, b) => a + b, 0) / humidityValues.length) : null;
    const totalRainfall = rainfallValues.length > 0 ? rainfallValues.reduce((a, b) => a + b, 0) : null;
    const avgWind = windValues.length > 0 ? (windValues.reduce((a, b) => a + b, 0) / windValues.length) : null;

    // Temperature - weekly average
    const tempValues = dailyAssessmentsForCounts.map((d) => d.avg_temperature).filter((v) => v !== null && v !== undefined && !isNaN(v));
    const avgTemperature = tempValues.length > 0 ? (tempValues.reduce((a, b) => a + b, 0) / tempValues.length) : null;

    // Temperature - weekly suitability score
    const weeklyScore = overall.score !== null && overall.score !== undefined ? overall.score : null;

    // Score banner
    document.getElementById("csOverallScore").textContent = weeklyScore !== null ? `${formatScore(weeklyScore)}` : "--";
    const csScoreContextSub = document.getElementById("csScoreContextSub");
    if (csScoreContextSub) {
      csScoreContextSub.textContent = totalAnalysedDays !== null ? `Based on ${totalAnalysedDays} valid days` : "Based on 0 valid days";
    }

    // Overall progress bar width (good + sustainable) / total valid days
    const goodSustainableCount = goodCount + sustainableCount;
    const progressPct = totalAnalysedDays > 0 ? Math.round((goodSustainableCount / totalAnalysedDays) * 100) : 0;
    const csOverallProgress = document.getElementById("csOverallProgress");
    if (csOverallProgress) {
      csOverallProgress.style.width = `${progressPct}%`;
    }

    document.getElementById("csDaysBadge").textContent = totalAnalysedDays !== null ? `${totalAnalysedDays} valid days assessed` : "0 valid days assessed";

    // Legend counts and percentages
    const pctGood = totalAnalysedDays > 0 ? ((goodCount / totalAnalysedDays) * 100).toFixed(1) : "0.0";
    const pctSustainable = totalAnalysedDays > 0 ? ((sustainableCount / totalAnalysedDays) * 100).toFixed(1) : "0.0";
    const pctMarginal = totalAnalysedDays > 0 ? ((marginalCount / totalAnalysedDays) * 100).toFixed(1) : "0.0";
    const pctBad = totalAnalysedDays > 0 ? ((badCount / totalAnalysedDays) * 100).toFixed(1) : "0.0";

    document.getElementById("csDistGoodCount").textContent = `${goodCount} days`;
    document.getElementById("csDistGoodPct").textContent = `${pctGood}%`;
    document.getElementById("csDistSustainableCount").textContent = `${sustainableCount} days`;
    document.getElementById("csDistSustainablePct").textContent = `${pctSustainable}%`;
    document.getElementById("csDistMarginalCount").textContent = `${marginalCount} days`;
    document.getElementById("csDistMarginalPct").textContent = `${pctMarginal}%`;
    document.getElementById("csDistBadCount").textContent = `${badCount} days`;
    document.getElementById("csDistBadPct").textContent = `${pctBad}%`;

    const footerMsg = totalAnalysedDays > 0
      ? `Good and sustainable days account for all ${totalAnalysedDays} valid days.`
      : "No valid days assessed.";
    document.getElementById("csDistFooter").textContent = footerMsg;

    document.getElementById("csTempValue").textContent = avgTemperature !== null ? formatTemp(avgTemperature) : "--";
    const csTempSuitabilityEl = document.getElementById("csTempSuitability");
    if (csTempSuitabilityEl) {
      csTempSuitabilityEl.textContent = weeklyScore !== null ? `${formatScore(weeklyScore)} % Suitability` : "-- % Suitability";
    }
    document.getElementById("csHumidityValue").textContent = avgHumidity !== null ? `${avgHumidity.toFixed(0)}` : "--";
    document.getElementById("csRainfallValue").textContent = totalRainfall !== null ? `${totalRainfall.toFixed(1)}` : "--";
    document.getElementById("csWindValue").textContent = avgWind !== null ? `${avgWind.toFixed(1)}` : "--";

    // Soil pH
    const phValue = ph.farmer_ph;
    const phValueEl = document.getElementById("csPhValue");
    const phSubEl = document.getElementById("csPhCaption");
    if (phValueEl && phSubEl) {
      if (phValue !== null && phValue !== undefined) {
        phValueEl.textContent = phValue.toFixed(1);
        phSubEl.textContent = ph.status === "GOOD" ? "Within crop range" : ph.status === "MARGINAL" ? "Near crop range" : "Outside crop range";
      } else {
        phValueEl.textContent = "--";
        phSubEl.textContent = "Not provided";
      }
    }

    // Day-wise suitability cards
    renderDaywise(dailyAssessments, crop);

    // Crop season & duration info
    renderCropInfo(data.crop_duration);

    // Growth progress
    renderGrowthProgress(data.growth_progress, data.sowing_date);

    // Compact factor analysis
    renderFactors(crop, weather, ph, dailyAssessments);

    // Soil pH analysis
    renderPHAnalysis(ph);

    // Charts
    renderCharts(data, crop);

    // Advisory banner
    renderAdvisory(weather, ph, crop);
  }

  function renderDaywise(dailyAssessments, crop) {
    const grid = document.getElementById("daywiseGrid");
    if (!grid) return;
    grid.innerHTML = "";

    if (!dailyAssessments || dailyAssessments.length === 0) {
      grid.innerHTML = '<div class="cs-day-empty" style="grid-column: 1 / -1; padding: 24px; text-align: center; color: var(--color-text-muted);">No daily forecast data available.</div>';
      return;
    }

    dailyAssessments.forEach((day) => {
      const status = day.status || "UNKNOWN";
      const badgeClass = statusBadgeClass(status);
      const badgeLabel = classificationLabel(status);

      const dateObj = day.date ? new Date(day.date) : null;
      const dayName = dateObj ? dateObj.toLocaleDateString("en-IN", { weekday: "short" }) : "Day";
      const dayDate = dateObj ? dateObj.toLocaleDateString("en-IN", { day: "numeric", month: "short" }) : "";

      const card = document.createElement("div");
      card.className = `cs-day-card cs-day-${classificationClass(status)}`;
      card.innerHTML = `
        <div class="cs-day-header">
          <div class="cs-day-name">${dayName}</div>
          <div class="cs-day-date">${dayDate}</div>
        </div>
        <div class="cs-day-status-badge ${badgeClass}">${badgeLabel}</div>
        <div class="cs-day-temp">${formatTemp(day.avg_temperature)}</div>
        <div class="cs-day-detail"><span class="cs-day-icon">Humidity</span> ${formatHumidity(day.avg_humidity)}</div>
        <div class="cs-day-detail"><span class="cs-day-icon">Rainfall</span> ${formatRain(day.total_rainfall)}</div>
        <div class="cs-day-detail"><span class="cs-day-icon">Wind</span> ${formatWind(day.avg_wind_speed)}</div>
      `;
      grid.appendChild(card);
    });
  }

  // ------------------------------------------------------------------
  // Crop Season & Duration Info
  // ------------------------------------------------------------------
  function renderCropInfo(cropDuration) {
    if (!cropDuration) {
      document.getElementById("csCropCategory").textContent = "Not available";
      document.getElementById("csSeasonBadge").textContent = "Not available";
      document.getElementById("csTotalDuration").textContent = "--";
      ["csStage1Days","csStage2Days","csStage3Days","csStage4Days","csStage5Days"].forEach(id => {
        document.getElementById(id).textContent = "-- days";
      });
      ["csStage1Fill","csStage2Fill","csStage3Fill","csStage4Fill","csStage5Fill"].forEach(id => {
        document.getElementById(id).style.width = "0%";
      });
      return;
    }

    document.getElementById("csCropCategory").textContent = cropDuration.category || "Not available";
    document.getElementById("csSeasonBadge").textContent = cropDuration.season || "Not available";
    document.getElementById("csTotalDuration").textContent = cropDuration.total_duration_days ? cropDuration.total_duration_days : "--";

    const stages = [
      { id: "csStage1Days", idFill: "csStage1Fill", val: cropDuration.establishment_duration_days },
      { id: "csStage2Days", idFill: "csStage2Fill", val: cropDuration.vegetative_duration_days },
      { id: "csStage3Days", idFill: "csStage3Fill", val: cropDuration.flowering_duration_days },
      { id: "csStage4Days", idFill: "csStage4Fill", val: cropDuration.fruiting_grain_filling_duration_days },
      { id: "csStage5Days", idFill: "csStage5Fill", val: cropDuration.maturity_harvesting_duration_days },
    ];

    const total = cropDuration.total_duration_days || 0;

    stages.forEach((s) => {
      const el = document.getElementById(s.id);
      const fillEl = document.getElementById(s.idFill);
      if (s.val !== null && s.val !== undefined) {
        el.textContent = `${s.val} days`;
        const pct = total > 0 ? Math.round((s.val / total) * 100) : 0;
        fillEl.style.width = `${pct}%`;
      } else {
        el.textContent = "-- days";
        fillEl.style.width = "0%";
      }
    });
  }

  // ------------------------------------------------------------------
  // Growth Progress
  // ------------------------------------------------------------------
  function renderGrowthProgress(gp, sowingDate) {
    const section = document.getElementById("growthProgressSection");
    if (!section) return;

    if (!gp || !gp.available) {
      section.style.display = "none";
      return;
    }

    section.style.display = "block";

    const progress = gp.progress_percentage !== null && gp.progress_percentage !== undefined ? gp.progress_percentage : 0;

    document.getElementById("gpProgressValue").textContent = `${progress}%`;
    document.getElementById("gpProgressFill").style.width = `${progress}%`;
    document.getElementById("gpElapsedDays").textContent = formatDays(gp.elapsed_days);
    document.getElementById("gpRemainingDays").textContent = formatDays(gp.remaining_days);
    document.getElementById("gpTotalDuration").textContent = formatDays(gp.total_duration_days) ? `${formatDays(gp.total_duration_days)} days` : "--";
    document.getElementById("gpMaturityDate").textContent = formatDate(gp.expected_maturity_date);
    document.getElementById("gpStageName").textContent = gp.stage || "Not yet sown";
    document.getElementById("gpStageDesc").textContent = gp.stage_description || "";

    const btn = document.getElementById("gpEnterSowingBtn");
    if (gp.status === "upcoming" || gp.status === "not_started") {
      btn.style.display = "block";
    } else {
      btn.style.display = "none";
    }
  }

  // ------------------------------------------------------------------
  // Soil pH Analysis with Visual Indicators
  // ------------------------------------------------------------------
  function renderPHAnalysis(ph) {
    const container = document.getElementById("phAnalysis");
    if (!container) return;
    container.innerHTML = "";

    if (!ph) {
      container.innerHTML = '<div class="cs-ph-empty">Soil pH analysis data is not available.</div>';
      return;
    }

    const farmerPh = ph.farmer_ph;
    const cropMin = ph.crop_min;
    const cropMax = ph.crop_max;
    const status = ph.status || "UNKNOWN";
    const difference = ph.difference;
    const message = ph.message || "";
    const explanation = ph.explanation || "";

    let statusColor = "grey";
    let statusBg = "#F3F4F6";
    if (status === "GOOD") { statusColor = "#15803d"; statusBg = "#dcfce7"; }
    else if (status === "MARGINAL") { statusColor = "#92400e"; statusBg = "#fef3c7"; }
    else if (status === "BAD") { statusColor = "#991b1b"; statusBg = "#fee2e2"; }

    const farmerPhDisplay = farmerPh !== null && farmerPh !== undefined ? farmerPh.toFixed(1) : "Not provided";
    const cropMinDisplay = cropMin !== null ? cropMin.toFixed(1) : "--";
    const cropMaxDisplay = cropMax !== null ? cropMax.toFixed(1) : "--";
    const diffDisplay = difference !== null && difference !== undefined ? difference.toFixed(1) : "--";

    let phPosition = 0;
    if (farmerPh !== null && farmerPh !== undefined) {
      phPosition = (farmerPh / 14) * 100;
    }

    let rangeStart = 0, rangeEnd = 100;
    if (cropMin !== null && cropMax !== null) {
      rangeStart = (cropMin / 14) * 100;
      rangeEnd = (cropMax / 14) * 100;
    }

    container.innerHTML = `
      <div class="cs-ph-status-row">
        <span class="cs-ph-status-badge" style="background-color: ${statusBg}; color: ${statusColor};">
          ${status}
        </span>
        ${farmerPh !== null && farmerPh !== undefined
          ? `<span class="cs-ph-diff">${difference !== null ? (difference > 0 ? "+" : "") + diffDisplay : ""}</span>`
          : ""
        }
      </div>

      <div class="cs-ph-layout">
        <div class="cs-ph-left">
          <div class="cs-ph-value-display">
            <span class="cs-ph-value">${farmerPhDisplay}</span>
            <span class="cs-ph-caption">Your soil pH</span>
          </div>
        </div>
        <div class="cs-ph-right">
          <div class="cs-ph-detail">
            <span class="cs-ph-detail-label">Crop minimum</span>
            <span class="cs-ph-detail-value">${cropMinDisplay}</span>
          </div>
          <div class="cs-ph-detail">
            <span class="cs-ph-detail-label">Crop maximum</span>
            <span class="cs-ph-detail-value">${cropMaxDisplay}</span>
          </div>
          <div class="cs-ph-detail">
            <span class="cs-ph-detail-label">Difference</span>
            <span class="cs-ph-detail-value">${diffDisplay}</span>
          </div>
        </div>
      </div>

      <div class="cs-ph-scale-container">
        <div class="cs-ph-scale">
          <div class="cs-ph-zone cs-ph-zone-acidic" style="left: 0%; width: ${rangeStart}%;"></div>
          <div class="cs-ph-zone cs-ph-zone-recommended" style="left: ${rangeStart}%; width: ${rangeEnd - rangeStart}%;"></div>
          <div class="cs-ph-zone cs-ph-zone-alkaline" style="left: ${rangeEnd}%; width: ${100 - rangeEnd}%;"></div>
          ${farmerPh !== null && farmerPh !== undefined
            ? `<div class="cs-ph-marker" style="left: ${phPosition}%;"></div>`
            : ""
          }
        </div>
        <div class="cs-ph-scale-labels">
          <span>0</span>
          <span>${cropMin !== null ? cropMin.toFixed(1) : "4.4"}</span>
          <span>${cropMax !== null ? cropMax.toFixed(1) : "7.5"}</span>
          <span>14</span>
        </div>
      </div>

      <p class="cs-ph-explanation">${explanation}</p>
      ${message ? `<p class="cs-ph-message">${message}</p>` : ""}
    `;
  }

  function renderFactors(crop, weather, ph, dailyAssessments) {
    // Temperature factor
    const optimalRange = `${formatTempPlain(crop.best_low_temp)}–${formatTempPlain(crop.best_high_temp)}°C`;
    const sustainableRange = `${formatTempPlain(crop.low_temp)}–${formatTempPlain(crop.max_temp)}°C`;
    setFactor(
      "resTempStatus", "resTempDot", "resTempLabel", "resTempMessage",
      "resTempCropRange", "resTempForecast",
      {
        label: "Temperature",
        color: statusColor(weather.status),
        message: weather.explanation || "Temperature suitability assessed.",
        crop_range: `Optimal: ${optimalRange}`,
        forecast_range: `Sustainable: ${sustainableRange}`,
      }
    );

    // Humidity factor - compute weekly average from daily assessments
    const humidityValues = dailyAssessments
      .map(d => d.avg_humidity)
      .filter(v => v !== null && v !== undefined && !isNaN(v));
    const avgHumidity = humidityValues.length > 0
      ? (humidityValues.reduce((a, b) => a + b, 0) / humidityValues.length)
      : null;
    setFactor(
      "resHumidityStatus", "resHumidityDot", "resHumidityLabel", "resHumidityMessage",
      "resHumidityValue", null,
      {
        label: "Humidity",
        color: avgHumidity !== null ? statusColor(weather.status) : "grey",
        message: avgHumidity !== null
          ? `Weekly average humidity is ${formatHumidity(avgHumidity)}.`
          : "Humidity data not available.",
        value: avgHumidity,
        range: "--",
      },
      { singleDetail: true }
    );

    // Rainfall factor - compute weekly total
    const rainfallValues = dailyAssessments
      .map(d => d.total_rainfall)
      .filter(v => v !== null && v !== undefined && !isNaN(v));
    const totalRainfall = rainfallValues.length > 0
      ? rainfallValues.reduce((a, b) => a + b, 0)
      : null;
    setFactor(
      "resRainfallStatus", "resRainfallDot", "resRainfallLabel", "resRainfallMessage",
      "resRainfallTotal", null,
      {
        label: "Rainfall",
        color: totalRainfall !== null ? statusColor(weather.status) : "grey",
        message: totalRainfall !== null
          ? `Weekly total rainfall is ${formatRain(totalRainfall)}.`
          : "Rainfall data not available.",
        value: totalRainfall,
        range: "--",
      },
      { singleDetail: true }
    );

    // Wind speed factor - compute weekly average
    const windValues = dailyAssessments
      .map(d => d.avg_wind_speed)
      .filter(v => v !== null && v !== undefined && !isNaN(v));
    const avgWind = windValues.length > 0
      ? (windValues.reduce((a, b) => a + b, 0) / windValues.length)
      : null;
    setFactor(
      "resWindStatus", "resWindDot", "resWindLabel", "resWindMessage",
      "resWindValue", null,
      {
        label: "Wind speed",
        color: avgWind !== null ? statusColor(weather.status) : "grey",
        message: avgWind !== null
          ? `Weekly average wind speed is ${formatWind(avgWind)}.`
          : "Wind data not available.",
        value: avgWind,
        range: "--",
      },
      { singleDetail: true }
    );

    // Soil pH factor
    const phStatusColor = ph.status === "GOOD" ? "green" : ph.status === "MARGINAL" ? "amber" : ph.status === "BAD" ? "red" : "grey";
    const farmerPhDisplay = ph.farmer_ph !== null && ph.farmer_ph !== undefined
      ? formatNumber(ph.farmer_ph)
      : "Not provided";
    setFactor(
      "resPhStatus", "resPhDot", "resPhLabel", "resPhMessage",
      "resPhCropRange", "resPhFarmer",
      {
        label: "Soil pH",
        color: phStatusColor,
        message: ph.message || "pH analysis not available.",
        crop_range: `${formatNumber(ph.crop_min)}–${formatNumber(ph.crop_max)}`,
        farmer_ph: farmerPhDisplay,
      }
    );
  }

  function setFactor(statusId, dotId, labelId, messageId, detail1Id, detail2Id, factor, options = {}) {
    const statusEl = document.getElementById(statusId);
    const dotEl = document.getElementById(dotId);
    const labelEl = document.getElementById(labelId);
    const msgEl = document.getElementById(messageId);
    const d1El = document.getElementById(detail1Id);
    const d2El = document.getElementById(detail2Id);

    if (dotEl) dotEl.className = `cs-status-dot ${factor.color || "grey"}`;
    if (labelEl) labelEl.textContent = factor.label || "--";
    if (msgEl) msgEl.textContent = factor.message || "";

    if (options.singleDetail) {
      // Single detail layout: label + value only
      if (d1El) {
        d1El.innerHTML = `<span class="cs-detail-label">${getDetailLabel(factor)}:</span> <span class="cs-detail-value">${getDetailValue1(factor)}</span>`;
      }
      if (d2El) d2El.style.display = "none";
    } else {
      if (d1El && d2El) {
        d1El.innerHTML = `<span class="cs-detail-label">${getDetailLabel(factor)}:</span> <span class="cs-detail-value">${getDetailValue1(factor)}</span>`;
        d2El.innerHTML = `<span class="cs-detail-label">${getDetailLabel2(factor)}:</span> <span class="cs-detail-value">${getDetailValue2(factor)}</span>`;
      }
    }
  }

  function getDetailLabel(f) {
    if (f.label === "Temperature") return "Crop range";
    if (f.label === "Soil pH") return "Crop range";
    if (f.label === "Humidity") return "Weekly average";
    if (f.label === "Rainfall") return "Weekly total";
    if (f.label === "Wind speed") return "Weekly average";
    return "Value";
  }

  function getDetailValue1(f) {
    if (f.crop_range) return f.crop_range;
    if (f.value !== null && f.value !== undefined) {
      if (f.label === "Humidity") return formatHumidity(f.value);
      if (f.label === "Rainfall") return formatRain(f.value);
      if (f.label === "Wind speed") return formatWind(f.value);
      return formatNumber(f.value);
    }
    return "Not available";
  }

  function getDetailLabel2(f) {
    if (f.label === "Temperature") return "Sustainable range";
    if (f.label === "Soil pH") return "Your soil pH";
    return "";
  }

  function getDetailValue2(f) {
    if (f.forecast_range) return f.forecast_range;
    if (f.farmer_ph !== null && f.farmer_ph !== undefined && f.farmer_ph !== "Not available") return f.farmer_ph;
    if (f.range) return f.range;
    if (f.avg) return formatNumber(f.avg);
    return "Not available";
  }

  // ------------------------------------------------------------------
  // Custom Chart.js plugin: draw shaded horizontal reference bands
  // Used for optimal and sustainable temperature ranges on the temperature chart.
  // No external dependency required.
  // ------------------------------------------------------------------
  const referenceBandPlugin = {
    id: "referenceBand",
    beforeDraw(chart) {
      const ctx = chart.ctx;
      const chartArea = chart.chartArea;
      if (!chartArea) return;

      const bands = chart.options.referenceBands;
      if (!bands || !bands.length) return;

      const yScale = chart.scales.y;
      const xScale = chart.scales.x;

      ctx.save();
      // Draw bands behind the data (fill from left to right of chart area)
      bands.forEach((band) => {
        const topY = yScale.getPixelForValue(band.max);
        const bottomY = yScale.getPixelForValue(band.min);
        const leftX = xScale.getPixelForValue(0);
        const rightX = xScale.getPixelForValue(chart.data.labels.length - 1);

        ctx.fillStyle = band.color;
        ctx.fillRect(leftX, topY, rightX - leftX, bottomY - topY);
      });
      ctx.restore();
    },
  };

  // ------------------------------------------------------------------
  // Chart rendering (destroy existing instances first)
  // ------------------------------------------------------------------
  function destroyCharts() {
    Object.keys(chartInstances).forEach((key) => {
      try {
        if (chartInstances[key]) {
          chartInstances[key].destroy();
        }
      } catch (e) {
        // ignore
      }
    });
    chartInstances = {};
  }

  // Color palette
  const CHART_COLORS = {
    tempMax: "#153a25",       // dark green
    tempMin: "#dc2626",       // red
    optimalBand: "rgba(34, 197, 94, 0.14)",  // soft green
    sustainableBand: "rgba(245, 158, 11, 0.10)",  // light amber
    humidity: "#2563eb",      // blue
    rainfall: "#ef4444",      // red/coral
    wind: "#7c3aed",          // purple
  };

  function renderCharts(data, crop) {
    destroyCharts();

    const dailyAssessments = data.daily_assessments || [];

    // Build labels from daily assessments
    const labels = dailyAssessments.map((d, i) => {
      try {
        return d.date ? new Date(d.date).toLocaleDateString("en-IN", { weekday: "short", day: "numeric" }) : `Day ${i + 1}`;
      } catch (e) {
        return `Day ${i + 1}`;
      }
    });

    // Extract data arrays - missing values stay null (gaps, not zeros)
    const minTemps = dailyAssessments.map((d) => d.min_temperature);
    const maxTemps = dailyAssessments.map((d) => d.max_temperature);
    const humidities = dailyAssessments.map((d) => d.avg_humidity);
    const rainfalls = dailyAssessments.map((d) => d.total_rainfall);
    const winds = dailyAssessments.map((d) => d.avg_wind_speed);

    // Dynamic Y-axis ranges with padding (avoid wasting space with 0-100 when data is 40-70)
    const humRange = computeYRange(humidities, { minFloor: 0 });
    const rainRange = computeYRange(rainfalls, { minFloor: 0 });
    const windRange = computeYRange(winds, { minFloor: 0 });

    // Crop reference values (from CSV, may be null)
    const bestLow = crop.best_low_temp;
    const bestHigh = crop.best_high_temp;
    const lowTemp = crop.low_temp;
    const maxTemp = crop.max_temp;

    // Build reference bands for temperature chart
    const referenceBands = [];
    // Sustainable band (broader): low_temp to max_temp - light amber
    if (lowTemp !== null && maxTemp !== null) {
      referenceBands.push({
        min: lowTemp,
        max: maxTemp,
        color: CHART_COLORS.sustainableBand,
        label: "Sustainable range",
      });
    }
    // Optimal band (narrower): best_low_temp to best_high_temp - soft green
    if (bestLow !== null && bestHigh !== null) {
      referenceBands.push({
        min: bestLow,
        max: bestHigh,
        color: CHART_COLORS.optimalBand,
        label: "Optimal range",
      });
    }

    // Compute dynamic Y-axis range with padding so charts don't waste space
    // (e.g. humidity data 40-70 -> axis 30-80 instead of 0-100)
    function computeYRange(values, options = {}) {
      const { paddingPct = 0.1, minFloor = null, maxCeil = null } = options;
      const valid = values.filter((v) => v !== null && v !== undefined && !isNaN(v));
      if (valid.length === 0) return { min: 0, max: 100 };
      const dataMin = Math.min(...valid);
      const dataMax = Math.max(...valid);
      const range = dataMax - dataMin || 1;
      const pad = range * paddingPct;
      let min = dataMin - pad;
      let max = dataMax + pad;
      if (minFloor !== null) min = Math.max(min, minFloor);
      if (maxCeil !== null) max = Math.min(max, maxCeil);
      return { min, max };
    }

    // Common chart options
    const baseOptions = (title, yAxisLabel, yMin, yMax) => ({
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: {
          display: true,
          position: "top",
          labels: {
            font: { size: 11 },
            color: "#4a5568",
            padding: 16,
            boxWidth: 12,
          },
        },
        title: title ? { display: true, text: title, font: { size: 13, weight: "600" } } : { display: false },
        tooltip: {
          backgroundColor: "rgba(255, 255, 255, 0.95)",
          titleColor: "#1a202c",
          bodyColor: "#4a5568",
          borderColor: "#e2e8f0",
          borderWidth: 1,
          cornerRadius: 8,
          displayColors: false,
          padding: 10,
          callbacks: {
            label: function (ctx) {
              const val = ctx.parsed.y;
              if (val !== null && val !== undefined && !isNaN(val)) {
                return val.toFixed(1);
              }
              return "--";
            },
          },
        },
      },
      scales: {
        y: {
          beginAtZero: yMin === 0,
          min: yMin,
          max: yMax,
          title: { display: true, text: yAxisLabel, font: { size: 11, weight: "600" } },
          grid: { color: "rgba(0,0,0,0.06)", drawBorder: false },
          ticks: { font: { size: 10 }, color: "#718096" },
        },
        x: {
          grid: { display: false },
          ticks: { font: { size: 10 }, color: "#718096" },
        },
      },
      elements: {
        line: { tension: 0.4, borderWidth: 2 },
        point: { radius: 3, hoverRadius: 6, backgroundColor: "#ffffff", borderWidth: 2 },
      },
      animation: {
        duration: 800,
        easing: "easeInOutQuart",
      },
    });

    // ------------------------------------------------------------------
    // Temperature chart: min + max forecast lines + crop bands
    // ------------------------------------------------------------------
    const tempCtx = document.getElementById("chartTemperature");
    if (tempCtx) {
      const tempDatasets = [];

      // Max temperature line - dark green
      if (maxTemps.some((v) => v !== null && v !== undefined)) {
        tempDatasets.push({
          label: "Max temp",
          data: maxTemps,
          borderColor: CHART_COLORS.tempMax,
          backgroundColor: `rgba(21, 58, 37, 0.12)`,
          fill: false,
          pointRadius: 3,
          pointHoverRadius: 6,
          pointBackgroundColor: CHART_COLORS.tempMax,
          pointBorderColor: "#ffffff",
          pointBorderWidth: 2,
        });
      }

      // Min temperature line - red
      if (minTemps.some((v) => v !== null && v !== undefined)) {
        tempDatasets.push({
          label: "Min temp",
          data: minTemps,
          borderColor: CHART_COLORS.tempMin,
          backgroundColor: `rgba(220, 38, 38, 0.12)`,
          fill: false,
          pointRadius: 3,
          pointHoverRadius: 6,
          pointBackgroundColor: CHART_COLORS.tempMin,
          pointBorderColor: "#ffffff",
          pointBorderWidth: 2,
        });
      }

      chartInstances.temperature = new Chart(tempCtx, {
        type: "line",
        data: {
          labels: labels,
          datasets: tempDatasets,
        },
        options: baseOptions("Daily temperature (°C)", "°C", null, null),
        plugins: [referenceBandPlugin],
      });

      // Attach reference bands via options after creation
      chartInstances.temperature.options.referenceBands = referenceBands;
      chartInstances.temperature.update();
    }

    // ------------------------------------------------------------------
    // Humidity chart: blue line
    // ------------------------------------------------------------------
    const humCtx = document.getElementById("chartHumidity");
    if (humCtx) {
      chartInstances.humidity = new Chart(humCtx, {
        type: "line",
        data: {
          labels: labels,
          datasets: [
            {
              label: "Humidity",
              data: humidities,
              borderColor: CHART_COLORS.humidity,
              backgroundColor: "rgba(37, 99, 235, 0.12)",
              fill: false,
              pointRadius: 3,
              pointHoverRadius: 6,
              pointBackgroundColor: CHART_COLORS.humidity,
              pointBorderColor: "#ffffff",
              pointBorderWidth: 2,
            },
          ],
        },
        options: baseOptions("Daily humidity (%)", "%", humRange.min, humRange.max),
      });
    }

    // ------------------------------------------------------------------
    // Rainfall chart: red/coral line
    // ------------------------------------------------------------------
    const rainCtx = document.getElementById("chartRainfall");
    if (rainCtx) {
      chartInstances.rainfall = new Chart(rainCtx, {
        type: "line",
        data: {
          labels: labels,
          datasets: [
            {
              label: "Rainfall",
              data: rainfalls,
              borderColor: CHART_COLORS.rainfall,
              backgroundColor: "rgba(239, 68, 68, 0.12)",
              fill: false,
              pointRadius: 3,
              pointHoverRadius: 6,
              pointBackgroundColor: CHART_COLORS.rainfall,
              pointBorderColor: "#ffffff",
              pointBorderWidth: 2,
            },
          ],
        },
        options: baseOptions("Daily rainfall (mm)", "mm", rainRange.min, rainRange.max),
      });
    }

    // ------------------------------------------------------------------
    // Wind speed chart: purple line
    // ------------------------------------------------------------------
    const windCtx = document.getElementById("chartWind");
    if (windCtx) {
      chartInstances.wind = new Chart(windCtx, {
        type: "line",
        data: {
          labels: labels,
          datasets: [
            {
              label: "Wind speed",
              data: winds,
              borderColor: CHART_COLORS.wind,
              backgroundColor: "rgba(124, 58, 237, 0.12)",
              fill: false,
              pointRadius: 3,
              pointHoverRadius: 6,
              pointBackgroundColor: CHART_COLORS.wind,
              pointBorderColor: "#ffffff",
              pointBorderWidth: 2,
            },
          ],
        },
        options: baseOptions("Daily wind speed (m/s)", "m/s", windRange.min, windRange.max),
      });
    }
  }

  function renderAdvisory(weather, ph, crop) {
    const banner = document.getElementById("csAdvisoryBanner");
    const titleEl = document.getElementById("csAdvisoryTitle");
    const msgEl = document.getElementById("csAdvisoryMessage");

    const messages = [];

    if (weather.explanation) {
      messages.push({ title: "Weather insight", text: weather.explanation });
    }

    if (ph.explanation) {
      messages.push({ title: "Soil pH insight", text: ph.explanation });
    } else if (ph.status === "UNKNOWN") {
      messages.push({ title: "Soil pH", text: "Soil pH was not provided. pH suitability cannot be assessed." });
    }

    if (weather.status === "INSUFFICIENT_DATA") {
      messages.push({ title: "Data warning", text: "Weather data is insufficient for a reliable analysis." });
    }

    if (messages.length === 0) {
      banner.style.display = "none";
      return;
    }

    // Show the first message (or combine)
    const m = messages[0];
    titleEl.textContent = m.title;
    msgEl.textContent = m.text;
    banner.style.display = "flex";
  }

  // ------------------------------------------------------------------
  // Initialize categories
  // ------------------------------------------------------------------
  fetch(`${API_BASE}/categories`)
    .then((r) => r.json())
    .then((data) => {
      if (data.success && data.data) {
        window.CS_CATEGORIES_SERVER = data.data;
      }
    })
    .catch(() => {
      // Categories will be passed via template
    });
})();
