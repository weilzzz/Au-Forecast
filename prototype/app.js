const number = new Intl.NumberFormat("zh-CN", {
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

const dateTime = new Intl.DateTimeFormat("zh-CN", {
  year: "numeric",
  month: "2-digit",
  day: "2-digit",
  hour: "2-digit",
  minute: "2-digit",
  hour12: false,
});

const shortDate = new Intl.DateTimeFormat("zh-CN", {
  month: "2-digit",
  day: "2-digit",
  hour: "2-digit",
  minute: "2-digit",
  hour12: false,
});

const signalClass = (code) => {
  if (["bullish", "slightly_bullish"].includes(code)) return "bullish";
  if (["bearish", "slightly_bearish"].includes(code)) return "bearish";
  return "neutral";
};

const signed = (value, suffix = "") => {
  if (value === null || value === undefined) return "—";
  const prefix = value > 0 ? "+" : "";
  return `${prefix}${number.format(value)}${suffix}`;
};

const escapeHtml = (value) =>
  String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");

let currentData = null;
let activeHistoryFilter = "all";

function setActivePage(name) {
  document.querySelectorAll(".tab-button").forEach((button) => {
    button.classList.toggle("active", button.dataset.tab === name);
  });
  document.querySelectorAll(".page").forEach((page) => {
    page.classList.toggle("active", page.dataset.page === name);
  });
  window.scrollTo({ top: 0, behavior: "smooth" });
}

function renderMarketQuotes(data) {
  const quotes = data.market_quotes || [
    {
      symbol: data.instrument.symbol,
      name: data.instrument.name,
      description: "全球场外现货黄金兑美元报价",
      price: data.instrument.price,
      unit: "USD/oz",
      change_percent: data.instrument.change_percent,
    },
  ];

  document.getElementById("marketQuotes").innerHTML = quotes
    .map(
      (quote, index) => `
        <article class="quote ${index === 0 ? "active" : ""}">
          <div class="quote-name">
            <span class="live-dot"></span>
            <div>
              <p>${escapeHtml(quote.symbol)}
                <button class="info-button" type="button" title="${escapeHtml(quote.description)}">i</button>
              </p>
              <small>${escapeHtml(quote.name)}${index === 0 ? ` · ${escapeHtml(data.instrument.session)}` : quote.contract ? ` · ${escapeHtml(quote.contract)}` : ""}</small>
            </div>
          </div>
          <div class="ticker-price">
            <strong>${number.format(quote.price)}</strong>
            <span>${escapeHtml(quote.unit)}</span>
            <em>${signed(quote.change_percent, "%")}</em>
          </div>
        </article>
      `
    )
    .join("");
}

function historyStatus(record) {
  if (record.outcome.status === "pending") return "pending";
  return record.outcome.direction_hit ? "hit" : "miss";
}

function formatDateOnly(value) {
  if (!value) return "—";
  return value.replaceAll("-", ".");
}

function renderHistory(history) {
  if (!history || !history.records) return;
  const records = history.records;
  const evaluated = records.filter((record) => record.outcome.status === "evaluated");
  const pending = records.filter((record) => record.outcome.status === "pending");
  const directionHits = evaluated.filter((record) => record.outcome.direction_hit).length;
  const rangeHits = evaluated.filter((record) => record.outcome.range_hit).length;
  const directionAccuracy = evaluated.length ? (directionHits / evaluated.length) * 100 : 0;
  const rangeAccuracy = evaluated.length ? (rangeHits / evaluated.length) * 100 : 0;

  document.getElementById("directionAccuracy").textContent =
    evaluated.length ? `${directionAccuracy.toFixed(1)}%` : "—";
  document.getElementById("rangeAccuracy").textContent =
    evaluated.length ? `${rangeAccuracy.toFixed(1)}%` : "—";
  document.getElementById("evaluatedCount").textContent = evaluated.length;
  document.getElementById("pendingCount").textContent = pending.length;
  document.getElementById("accuracyRing").style.setProperty(
    "--accuracy-angle",
    `${directionAccuracy * 3.6}deg`
  );
  document.getElementById("evaluationDescription").textContent =
    history.evaluation_rule.description;

  let conclusion = "暂无足够记录，暂不能判断系统有效性。";
  if (evaluated.length > 0 && evaluated.length < 20) {
    conclusion = `当前命中 ${directionHits}/${evaluated.length} 次，准确率 ${directionAccuracy.toFixed(1)}%。样本仍少，只能作为初步观察。`;
  } else if (directionAccuracy >= 65) {
    conclusion = `当前准确率 ${directionAccuracy.toFixed(1)}%，表现具有一定参考价值，仍需结合回撤与更多样本验证。`;
  } else if (directionAccuracy >= 50) {
    conclusion = `当前准确率 ${directionAccuracy.toFixed(1)}%，尚未显示出稳定优势。`;
  } else {
    conclusion = `当前准确率 ${directionAccuracy.toFixed(1)}%，规则需要重新校准。`;
  }
  document.getElementById("accuracyConclusion").textContent = conclusion;

  document.getElementById("performanceStrip").innerHTML = records
    .map((record) => {
      const status = historyStatus(record);
      return `<i class="performance-point ${status}" data-label="${escapeHtml(record.forecast_date.slice(5).replace("-", "."))}" title="${escapeHtml(record.forecast_date)} · ${status === "hit" ? "命中" : status === "miss" ? "未命中" : "等待验证"}"></i>`;
    })
    .join("");
  document.getElementById("recentPerformanceLabel").textContent =
    `近${evaluated.length}次已验证`;

  renderHistoryRows(records);
}

function renderHistoryRows(records) {
  const filtered = records.filter((record) => {
    const status = historyStatus(record);
    return activeHistoryFilter === "all" || status === activeHistoryFilter;
  });

  document.getElementById("historyRows").innerHTML = filtered
    .map((record) => {
      const outcome = record.outcome;
      const status = historyStatus(record);
      const isPending = status === "pending";
      const returnClass =
        outcome.return_percent > 0 ? "positive-text" :
        outcome.return_percent < 0 ? "negative-text" : "";
      const resultText = status === "hit" ? "方向命中" : status === "miss" ? "方向未命中" : "等待验证";
      const rangeText = isPending ? "待验证" : outcome.range_hit ? "命中" : "未命中";
      return `
        <tr>
          <td class="numeric">${formatDateOnly(record.forecast_date)}</td>
          <td class="prediction-cell">
            <strong>${escapeHtml(record.prediction.direction)}</strong>
            <small>${escapeHtml(record.horizon)}</small>
          </td>
          <td class="numeric">${signed(record.prediction.score, "")} / ${record.prediction.confidence}%</td>
          <td class="numeric">${number.format(record.prediction.start_price)}</td>
          <td class="numeric">${isPending ? "—" : number.format(outcome.close_price)}<br><small>${formatDateOnly(record.evaluation_date)}</small></td>
          <td class="${returnClass}">
            ${isPending ? "等待收盘" : `${escapeHtml(outcome.actual_direction)} ${signed(outcome.return_percent, "%")}`}
          </td>
          <td><span class="range-result ${isPending ? "" : outcome.range_hit ? "hit" : "miss"}">${rangeText}</span></td>
          <td><span class="result-badge ${status}">${resultText}</span></td>
        </tr>
      `;
    })
    .join("");

  if (!filtered.length) {
    document.getElementById("historyRows").innerHTML =
      `<tr><td colspan="8" class="empty-history">当前筛选下没有记录</td></tr>`;
  }
}

function render(data) {
  currentData = data;
  renderMarketQuotes(data);
  document.getElementById("marketAsOf").textContent = dateTime
    .format(new Date(data.market_as_of))
    .replaceAll("/", ".");

  document.getElementById("horizon").textContent = data.forecast.horizon;
  document.getElementById("direction").textContent = data.forecast.direction;
  document.getElementById("score").textContent = signed(data.forecast.score);
  document.getElementById("driverPageScore").textContent = signed(data.forecast.score);
  document.getElementById("scoreMarker").style.left =
    `${Math.max(0, Math.min(100, (data.forecast.score + 100) / 2))}%`;
  document.getElementById("confidence").textContent = data.forecast.confidence;
  document.getElementById("confidenceBar").style.width = `${data.forecast.confidence}%`;
  document.getElementById("summary").textContent = data.forecast.summary;
  document.getElementById("benchmarkName").textContent =
    data.forecast.benchmark_name || data.instrument.name;
  document.getElementById("expectedRange").textContent =
    `$${number.format(data.forecast.expected_range.low)} — ` +
    `$${number.format(data.forecast.expected_range.high)}`;

  document.getElementById("eventList").innerHTML = data.events
    .map((event) => {
      const date = new Date(event.scheduled_at);
      return `
        <div class="event-item">
          <div class="event-date">${String(date.getMonth() + 1).padStart(2, "0")}.${String(date.getDate()).padStart(2, "0")}<br>${String(date.getHours()).padStart(2, "0")}:${String(date.getMinutes()).padStart(2, "0")}</div>
          <div>
            <strong>${escapeHtml(event.name)}</strong>
            <small>${escapeHtml(event.expected_effect)}</small>
          </div>
          <span class="event-level">${event.importance === "high" ? "高影响" : "关注"}</span>
        </div>
      `;
    })
    .join("");
  if (!data.events.length) {
    document.getElementById("eventList").innerHTML =
      `<div class="empty-state">暂未配置近期重要事件</div>`;
  }

  document.getElementById("factorGrid").innerHTML = data.factors
    .map((factor, index) => {
      const width = Math.min(100, Math.abs(factor.score / factor.weight) * 100);
      return `
        <article class="factor-card ${signalClass(factor.signal_code)}">
          <div class="factor-top">
            <span class="factor-index">0${index + 1}</span>
            <span class="factor-weight">${factor.weight}%</span>
          </div>
          <h3>${escapeHtml(factor.name)}</h3>
          <div class="factor-score">${signed(factor.score)} <small>/ ${factor.weight}</small></div>
          <div class="factor-meter"><i style="width:${width}%"></i></div>
          <p>${escapeHtml(factor.summary)}</p>
        </article>
      `;
    })
    .join("");

  document.getElementById("referenceList").innerHTML = data.reference_systems
    .map(
      (reference) => `
        <button class="reference-item" type="button" data-reference-id="${escapeHtml(reference.id)}">
          <span class="reference-icon">${reference.id === "commodities" ? "CMD" : "FX"}</span>
          <div class="reference-copy">
            <strong>${escapeHtml(reference.name)}</strong>
            <small>${escapeHtml(reference.summary)}</small>
          </div>
          <div class="reference-status">
            <strong>${escapeHtml(reference.signal)} · ${escapeHtml(reference.relationship)}</strong>
            <small>一致度 ${reference.agreement}%</small>
          </div>
        </button>
      `
    )
    .join("");
  document.querySelectorAll("[data-reference-id]").forEach((button) => {
    button.addEventListener("click", () => openReferenceDrawer(button.dataset.referenceId));
  });

  document.getElementById("completeness").textContent = `${data.data_quality.completeness}%`;
  document.getElementById("freshness").textContent = `${data.data_quality.freshness}%`;
  document.getElementById("qualityMessage").textContent = data.data_quality.message;

  document.getElementById("driverCount").textContent = String(data.drivers.length).padStart(2, "0");
  document.getElementById("driverList").innerHTML = data.drivers
    .map(
      (item) => `
        <div class="insight-item">
          <strong>${escapeHtml(item.title)}</strong>
          <p>${escapeHtml(item.detail)}</p>
        </div>
      `
    )
    .join("");

  document.getElementById("riskCount").textContent = String(data.risks.length).padStart(2, "0");
  document.getElementById("riskList").innerHTML = data.risks
    .map(
      (item) => `
        <div class="insight-item">
          <strong>${escapeHtml(item.title)}</strong>
          <p>${escapeHtml(item.detail)}</p>
        </div>
      `
    )
    .join("");

  document.getElementById("indicatorRows").innerHTML = data.indicators
    .map((item) => {
      const changeClass = item.change_1d > 0 ? "positive-text" : item.change_1d < 0 ? "negative-text" : "";
      const statusText = item.status === "ok" ? "正常" : item.status === "delayed" ? "延迟" : "缺失";
      return `
        <tr>
          <td><strong>${escapeHtml(item.name)}</strong></td>
          <td class="numeric">${item.value === null ? "—" : `${number.format(item.value)} ${escapeHtml(item.unit)}`}</td>
          <td class="numeric ${changeClass}">${signed(item.change_1d)}</td>
          <td class="numeric">${signed(item.change_5d)}</td>
          <td>${escapeHtml(item.signal)}</td>
          <td class="numeric">${item.updated_at ? escapeHtml(shortDate.format(new Date(item.updated_at))) : "—"}</td>
          <td>
            <span class="status-cell status-${item.status}">
              <i class="status-dot"></i>${statusText}
            </span>
          </td>
        </tr>
      `;
    })
    .join("");

  renderHistory(data.validation_history);
  document.getElementById("disclaimer").textContent = data.disclaimer;
}

function openReferenceDrawer(referenceId) {
  if (!currentData) return;
  const reference = currentData.reference_systems.find((item) => item.id === referenceId);
  if (!reference) return;

  document.getElementById("drawerTitle").textContent = reference.name;
  document.getElementById("drawerSignal").textContent =
    `${reference.signal} · ${reference.relationship}`;
  document.getElementById("drawerAgreement").textContent = `${reference.agreement}%`;
  document.getElementById("drawerSummary").textContent = reference.summary;
  document.getElementById("drawerComponents").innerHTML = (reference.components || [])
    .map((item) => {
      const dayClass = item.change_1d > 0 ? "positive-text" : item.change_1d < 0 ? "negative-text" : "";
      return `
        <article class="component-item">
          <div class="component-head">
            <div class="component-name">
              <strong>${escapeHtml(item.name)}</strong>
              <small>${escapeHtml(item.symbol)}</small>
            </div>
            <div class="component-value">
              <strong>${number.format(item.value)} ${escapeHtml(item.unit)}</strong>
              <small>${escapeHtml(item.trend)}</small>
            </div>
          </div>
          <div class="component-change">
            <span class="${dayClass}">1日 ${signed(item.change_1d, "%")}</span>
            <span>5日 ${signed(item.change_5d, "%")}</span>
            <b>${escapeHtml(item.trend)}</b>
          </div>
        </article>
      `;
    })
    .join("");
  document.getElementById("drawerUpdates").innerHTML = (reference.updates || [])
    .map(
      (item) => `
        <article class="update-item">
          <strong>${escapeHtml(item.title)}</strong>
          <p>${escapeHtml(item.summary)}</p>
          <small>${escapeHtml(item.source_name)} · ${escapeHtml(shortDate.format(new Date(item.published_at)))}</small>
        </article>
      `
    )
    .join("");
  if (!(reference.updates || []).length) {
    document.getElementById("drawerUpdates").innerHTML =
      `<div class="empty-state">当前数据源暂未提供相关新闻或事件</div>`;
  }

  document.getElementById("referenceDrawer").classList.add("open");
  document.getElementById("referenceDrawer").setAttribute("aria-hidden", "false");
  document.getElementById("drawerBackdrop").classList.add("open");
  document.body.style.overflow = "hidden";
}

function closeReferenceDrawer() {
  document.getElementById("referenceDrawer").classList.remove("open");
  document.getElementById("referenceDrawer").setAttribute("aria-hidden", "true");
  document.getElementById("drawerBackdrop").classList.remove("open");
  document.body.style.overflow = "";
}

function showToast(message) {
  const toast = document.getElementById("toast");
  toast.textContent = message;
  toast.classList.add("show");
  window.setTimeout(() => toast.classList.remove("show"), 2200);
}

async function requestAnalysis(refresh = false) {
  const response = await fetch(refresh ? "/api/refresh" : "/api/analysis", {
    method: refresh ? "POST" : "GET",
    cache: "no-store",
  });
  if (!response.ok) {
    let message = `HTTP ${response.status}`;
    try {
      const error = await response.json();
      message = error.message || message;
    } catch {
      // Keep the HTTP status when the response is not JSON.
    }
    throw new Error(message);
  }
  return response.json();
}

async function loadData({ refresh = false, allowMockFallback = false } = {}) {
  try {
    const data = await requestAnalysis(refresh);
    render(data);
    document.querySelector(".market-status").innerHTML = "<i></i> 真实数据";
    if (data._warning) showToast(data._warning);
    return data;
  } catch (error) {
    if (!allowMockFallback) throw error;
    const response = await fetch("./mock-analysis.json", { cache: "no-store" });
    if (!response.ok) throw error;
    const data = await response.json();
    render(data);
    document.querySelector(".market-status").innerHTML = "<i></i> 原型回退";
    return data;
  }
}

document.querySelectorAll(".tab-button").forEach((button) => {
  button.addEventListener("click", () => setActivePage(button.dataset.tab));
});

document.querySelectorAll("[data-jump]").forEach((button) => {
  button.addEventListener("click", () => setActivePage(button.dataset.jump));
});

document.querySelectorAll("[data-history-filter]").forEach((button) => {
  button.addEventListener("click", () => {
    activeHistoryFilter = button.dataset.historyFilter;
    document.querySelectorAll("[data-history-filter]").forEach((item) => {
      item.classList.toggle("active", item === button);
    });
    if (currentData?.validation_history?.records) {
      renderHistoryRows(currentData.validation_history.records);
    }
  });
});

document.getElementById("drawerClose").addEventListener("click", closeReferenceDrawer);
document.getElementById("drawerBackdrop").addEventListener("click", closeReferenceDrawer);
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape") closeReferenceDrawer();
});

document.getElementById("refreshButton").addEventListener("click", async (event) => {
  const button = event.currentTarget;
  button.classList.add("loading");
  button.disabled = true;
  await new Promise((resolve) => window.setTimeout(resolve, 650));
  try {
    await loadData({ refresh: true });
    showToast("今日分析已刷新");
  } catch (error) {
    showToast(`更新失败：${error.message}`);
  } finally {
    button.classList.remove("loading");
    button.disabled = false;
  }
});

loadData({ allowMockFallback: true })
  .then((data) => {
    const isMock = data.schema_version === "1.0.0";
    showToast(isMock ? "当前为原型回退数据" : "真实市场数据已载入");
  })
  .catch((error) => showToast(`数据载入失败：${error.message}`));
