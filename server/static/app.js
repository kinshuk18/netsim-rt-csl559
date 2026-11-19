// NetSim-RT Frontend Application Logic
// CSL559 Computer Systems Design - IIT Bhilai

let tracesMetadata = {};
let activeCharts = {};

document.addEventListener("DOMContentLoaded", () => {
  initTabs();
  checkHealth();
  loadPresets();
  loadTraces();
  initCustomTemplates();

  const simBtn = document.getElementById("btn-run-sim");
  if (simBtn) simBtn.addEventListener("click", handleSimulatorSubmit);
  const simForm = document.getElementById("sim-form");
  if (simForm) simForm.addEventListener("submit", handleSimulatorSubmit);
  document.getElementById("sweep-form").addEventListener("submit", handleSweepSubmit);
  document.getElementById("shootout-form").addEventListener("submit", handleShootoutSubmit);
  document.getElementById("btn-run-custom").addEventListener("click", handleCustomPolicySubmit);
  document.getElementById("btn-load-template").addEventListener("click", loadSelectedTemplate);
  document.getElementById("dataset-selector").addEventListener("change", handleDatasetChange);
});

// Tab Navigation
function initTabs() {
  const tabBtns = document.querySelectorAll(".tab-btn");
  tabBtns.forEach(btn => {
    btn.addEventListener("click", () => {
      tabBtns.forEach(b => b.classList.remove("active"));
      document.querySelectorAll(".tab-content").forEach(tc => tc.classList.remove("active"));
      btn.classList.add("active");
      const targetId = btn.dataset.tab;
      document.getElementById(targetId).classList.add("active");
      // Trigger ECharts resize
      setTimeout(() => {
        Object.values(activeCharts).forEach(c => c && c.resize && c.resize());
      }, 100);
    });
  });
}

// Health Check
async function checkHealth() {
  try {
    const res = await fetch("/api/health");
    if (res.ok) {
      const data = await res.json();
      const st = document.getElementById("server-status");
      st.textContent = `Online (${data.version})`;
      st.className = "badge badge-success";
    }
  } catch (e) {
    const st = document.getElementById("server-status");
    st.textContent = "Offline";
    st.className = "badge badge-outline";
  }
}

// Presets Tab
async function loadPresets() {
  const container = document.getElementById("presets-list");
  try {
    const res = await fetch("/api/presets");
    const presets = await res.json();
    container.innerHTML = "";
    presets.forEach(p => {
      const card = document.createElement("div");
      card.className = "preset-card";
      card.innerHTML = `
        <div class="preset-card-content">
          <span class="badge badge-primary mb-2">${p.config ? p.config.trace_name : 'Scenario'}</span>
          <h3>${p.title}</h3>
          <p>${p.description}</p>
        </div>
        <button class="btn-inspect" onclick="viewPreset('${p.id}')">Inspect Scenario</button>
      `;
      container.appendChild(card);
    });
  } catch (e) {
    container.innerHTML = `<div class="alert alert-danger">Failed to load presets: ${e.message}</div>`;
  }
}

async function viewPreset(presetId) {
  try {
    const res = await fetch(`/api/presets/${presetId}`);
    const data = await res.json();
    const box = document.getElementById("preset-view-container");
    box.classList.remove("hidden");
    document.getElementById("preset-view-title").textContent = data.title;
    document.getElementById("preset-view-desc").textContent = data.description;
    box.scrollIntoView({ behavior: "smooth" });

    if (data.sweep) {
      renderSweepPreset(data.sweep);
    } else if (data.results) {
      renderShootoutPreset(data.results, data.ranking || Object.keys(data.results));
    }
  } catch (e) {
    alert("Error loading preset: " + e.message);
  }
}

function renderShootoutPreset(results, ranking) {
  const chartDom = document.getElementById("preset-chart");
  if (!chartDom) return;
  if (activeCharts.preset) activeCharts.preset.dispose();
  const chart = echarts.init(chartDom, "dark");
  activeCharts.preset = chart;

  const policies = ranking || Object.keys(results);
  const p99Data = policies.map(p => results[p] ? results[p].latency.p99_ms : 0);
  const maxWaitData = policies.map(p => results[p] ? results[p].wait_time.max_ms : 0);

  chart.setOption({
    backgroundColor: "transparent",
    tooltip: { trigger: "axis" },
    legend: { data: ["p99 Latency (ms)", "Max Wait Time (ms)"] },
    xAxis: { type: "category", data: policies.map(p => p.toUpperCase()) },
    yAxis: { type: "value", name: "Time (ms)" },
    series: [
      { name: "p99 Latency (ms)", type: "bar", data: p99Data, itemStyle: { color: "#38bdf8" } },
      { name: "Max Wait Time (ms)", type: "bar", data: maxWaitData, itemStyle: { color: "#f87171" } }
    ]
  });
  document.getElementById("preset-chart-caption").textContent = "What am I looking at: Comparative bar chart of tail latency (p99) and starvation delay (max wait) across policies.";

  // Table
  let html = `<table><thead><tr><th>Policy</th><th>Throughput (req/s)</th><th>Goodput (req/s)</th><th>p50 (ms)</th><th>p99 (ms)</th><th>Max Wait (ms)</th><th>Fairness</th><th>Utilization</th></tr></thead><tbody>`;
  policies.forEach(p => {
    const r = results[p];
    if (r) {
      html += `<tr>
        <td><strong>${p.toUpperCase()}</strong></td>
        <td>${r.throughput_req_per_s.toFixed(1)}</td>
        <td>${r.goodput_req_per_s.toFixed(1)}</td>
        <td>${r.latency.p50_ms.toFixed(1)}</td>
        <td>${r.latency.p99_ms.toFixed(1)}</td>
        <td>${r.wait_time.max_ms.toFixed(1)}</td>
        <td>${r.jains_fairness_index.toFixed(3)}</td>
        <td>${(r.server_utilization * 100).toFixed(1)}%</td>
      </tr>`;
    }
  });
  html += `</tbody></table>`;
  document.getElementById("preset-table-container").innerHTML = html;
}

function renderSweepPreset(sweep) {
  const chartDom = document.getElementById("preset-chart");
  if (!chartDom) return;
  if (activeCharts.preset) activeCharts.preset.dispose();
  const chart = echarts.init(chartDom, "dark");
  activeCharts.preset = chart;

  const pts = sweep.points;
  const x = pts.map(p => p.offered_load_req_per_s);
  const p99 = pts.map(p => p.latency_p99_ms);

  const markPts = [];
  const sp = sweep.special_points;
  if (sp.knee) markPts.push({ name: "Knee", coord: [sp.knee.offered_load_req_per_s, sp.knee.p99_ms], itemStyle: { color: "#10b981" } });
  if (sp.inflection) markPts.push({ name: "Inflection", coord: [sp.inflection.offered_load_req_per_s, sp.inflection.p99_ms], itemStyle: { color: "#f59e0b" } });
  if (sp.breaking) markPts.push({ name: "Breaking", coord: [sp.breaking.offered_load_req_per_s, sp.breaking.p99_ms], itemStyle: { color: "#ef4444" } });

  chart.setOption({
    backgroundColor: "transparent",
    tooltip: { trigger: "axis" },
    xAxis: { type: "value", name: "Offered Load (req/s)" },
    yAxis: { type: "value", name: "p99 Latency (ms)" },
    series: [{
      name: "p99 Latency",
      type: "line",
      smooth: true,
      data: x.map((xv, i) => [xv, p99[i]]),
      markPoint: { data: markPts },
      itemStyle: { color: "#38bdf8" }
    }]
  });
  document.getElementById("preset-chart-caption").textContent = "What am I looking at: Load sweep curve with marked Knee (green), Inflection (orange), and Breaking Point (red).";
  document.getElementById("preset-table-container").innerHTML = "";
}

// Simulator Tab
async function handleSimulatorSubmit(e) {
  e.preventDefault();
  const btn = document.getElementById("btn-run-sim");
  btn.textContent = "Simulating...";
  btn.disabled = true;

  const payload = {
    trace_name: document.getElementById("sim-trace").value,
    policy: document.getElementById("sim-policy").value,
    num_servers: parseInt(document.getElementById("sim-servers").value),
    load_multiplier: parseFloat(document.getElementById("sim-load").value),
    load_balancer: document.getElementById("sim-lb").value,
    admission_policy: document.getElementById("sim-admission").value,
    queue_capacity: parseInt(document.getElementById("sim-queue-cap").value),
    slo_target_ms: parseFloat(document.getElementById("sim-slo").value),
    max_requests: parseInt(document.getElementById("sim-max-req").value),
    client_timeout_s: parseFloat(document.getElementById("sim-timeout").value)
  };

  try {
    const res = await fetch("/api/simulate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });
    const data = await res.json();
    renderSimulatorResults(data);
  } catch (err) {
    alert("Simulation failed: " + err.message);
  } finally {
    btn.textContent = "Run Simulation";
    btn.disabled = false;
  }
}

function renderSimulatorResults(data) {
  document.getElementById("m-thr").textContent = data.throughput_req_per_s.toFixed(1);
  document.getElementById("m-goodput").textContent = data.goodput_req_per_s.toFixed(1);
  document.getElementById("m-p50").textContent = data.latency.p50_ms.toFixed(1);
  document.getElementById("m-p99").textContent = data.latency.p99_ms.toFixed(1);
  document.getElementById("m-util").textContent = (data.server_utilization * 100).toFixed(1);
  document.getElementById("m-jain").textContent = data.jains_fairness_index.toFixed(3);
  document.getElementById("m-drop").textContent = (data.drop_rate * 100).toFixed(2);
  document.getElementById("m-maxwait").textContent = data.wait_time.max_ms.toFixed(1);
  document.getElementById("sim-runtime").textContent = `Processed ${data.total_arrivals} requests (${data.events_per_sec.toFixed(0)} events/sec) in ${data.real_runtime_s.toFixed(3)}s.`;

  // Render Timeline Chart
  const chartDom = document.getElementById("sim-timeline-chart");
  if (!chartDom) return;
  if (activeCharts.simTimeline) activeCharts.simTimeline.dispose();
  const chart = echarts.init(chartDom, "dark");
  activeCharts.simTimeline = chart;

  const timeline = data.timeline || [];
  const times = timeline.map(t => t.time_s);
  const qDepths = timeline.map(t => t.queue_depth);
  const busy = timeline.map(t => t.active_servers);

  chart.setOption({
    backgroundColor: "transparent",
    tooltip: { trigger: "axis" },
    legend: { data: ["Queue Depth", "Active Servers"] },
    xAxis: { type: "category", data: times, name: "Simulation Time (s)" },
    yAxis: [
      { type: "value", name: "Queue Depth" },
      { type: "value", name: "Active Servers", max: data.num_servers }
    ],
    series: [
      { name: "Queue Depth", type: "line", data: qDepths, itemStyle: { color: "#38bdf8" }, areaStyle: { opacity: 0.2 } },
      { name: "Active Servers", type: "line", yAxisIndex: 1, data: busy, itemStyle: { color: "#34d399" } }
    ]
  });
}

// Sweep Tab
async function handleSweepSubmit(e) {
  e.preventDefault();
  const btn = document.getElementById("btn-run-sweep");
  btn.textContent = "Calculating Sweep...";
  btn.disabled = true;

  const payload = {
    trace_name: document.getElementById("sweep-trace").value,
    policy: document.getElementById("sweep-policy").value,
    num_servers: parseInt(document.getElementById("sweep-servers").value),
    num_points: parseInt(document.getElementById("sweep-points").value),
    min_multiplier: 1.0,
    max_multiplier: 400.0,
    max_requests: 4000
  };

  try {
    const res = await fetch("/api/sweep", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });
    const data = await res.json();
    renderSweepResults(data);
  } catch (err) {
    alert("Sweep failed: " + err.message);
  } finally {
    btn.textContent = "Run Load Sweep";
    btn.disabled = false;
  }
}

function renderSweepResults(data) {
  const sp = data.special_points;
  // Update Cards
  if (sp.knee) {
    document.getElementById("pt-knee-val").textContent = `${sp.knee.offered_load_req_per_s.toFixed(1)} req/s`;
    document.getElementById("pt-knee-sub").textContent = `ρ = ${sp.knee.rho.toFixed(3)}, p99 = ${sp.knee.p99_ms.toFixed(1)} ms`;
  }
  if (sp.inflection) {
    document.getElementById("pt-inf-val").textContent = `${sp.inflection.offered_load_req_per_s.toFixed(1)} req/s`;
    document.getElementById("pt-inf-sub").textContent = `ρ = ${sp.inflection.rho.toFixed(3)}, p99 = ${sp.inflection.p99_ms.toFixed(1)} ms`;
  }
  if (sp.breaking) {
    document.getElementById("pt-break-val").textContent = `${sp.breaking.offered_load_req_per_s.toFixed(1)} req/s`;
    document.getElementById("pt-break-sub").textContent = `ρ = ${sp.breaking.rho.toFixed(3)}, p99 = ${sp.breaking.p99_ms.toFixed(1)} ms (${sp.breaking.reason})`;
  }

  // Latency Chart
  const latDom = document.getElementById("sweep-latency-chart");
  if (activeCharts.sweepLat) activeCharts.sweepLat.dispose();
  const chartLat = echarts.init(latDom, "dark");
  activeCharts.sweepLat = chartLat;

  const pts = data.points;
  const x = pts.map(p => p.offered_load_req_per_s);
  const p99 = pts.map(p => p.latency_p99_ms);
  const markPts = [];
  if (sp.knee) markPts.push({ name: "Knee", coord: [sp.knee.offered_load_req_per_s, sp.knee.p99_ms], itemStyle: { color: "#10b981" } });
  if (sp.inflection) markPts.push({ name: "Inflection", coord: [sp.inflection.offered_load_req_per_s, sp.inflection.p99_ms], itemStyle: { color: "#f59e0b" } });
  if (sp.breaking) markPts.push({ name: "Breaking", coord: [sp.breaking.offered_load_req_per_s, sp.breaking.p99_ms], itemStyle: { color: "#ef4444" } });

  chartLat.setOption({
    backgroundColor: "transparent",
    tooltip: { trigger: "axis" },
    xAxis: { type: "value", name: "Offered Load (req/s)" },
    yAxis: { type: "value", name: "p99 Latency (ms)" },
    series: [{
      name: "p99 Latency",
      type: "line",
      smooth: true,
      data: x.map((xv, i) => [xv, p99[i]]),
      markPoint: { data: markPts },
      itemStyle: { color: "#38bdf8" }
    }]
  });

  // Goodput Chart
  const gpDom = document.getElementById("sweep-goodput-chart");
  if (activeCharts.sweepGp) activeCharts.sweepGp.dispose();
  const chartGp = echarts.init(gpDom, "dark");
  activeCharts.sweepGp = chartGp;

  const offered = pts.map(p => p.offered_load_req_per_s);
  const thr = pts.map(p => p.throughput_req_per_s);
  const goodput = pts.map(p => p.goodput_req_per_s);

  chartGp.setOption({
    backgroundColor: "transparent",
    tooltip: { trigger: "axis" },
    legend: { data: ["Offered Load", "Throughput", "Goodput (Within SLO)"] },
    xAxis: { type: "value", name: "Offered Load (req/s)" },
    yAxis: { type: "value", name: "Rate (req/s)" },
    series: [
      { name: "Offered Load", type: "line", lineStyle: { type: "dashed" }, data: offered.map((v, i) => [v, v]), itemStyle: { color: "#94a3b8" } },
      { name: "Throughput", type: "line", data: offered.map((v, i) => [v, thr[i]]), itemStyle: { color: "#34d399" } },
      { name: "Goodput (Within SLO)", type: "line", data: offered.map((v, i) => [v, goodput[i]]), itemStyle: { color: "#38bdf8" } }
    ]
  });
}

// Shootout Tab
async function handleShootoutSubmit(e) {
  e.preventDefault();
  const btn = document.getElementById("btn-run-shootout");
  btn.textContent = "Comparing...";
  btn.disabled = true;

  const payload = {
    trace_name: document.getElementById("shootout-trace").value,
    num_servers: parseInt(document.getElementById("shootout-servers").value),
    load_multiplier: parseFloat(document.getElementById("shootout-load").value),
    policies: ["fcfs", "sjf", "srtf", "rr", "static_priority", "mlfq", "wfq"],
    max_requests: 4000
  };

  try {
    const res = await fetch("/api/shootout", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });
    const data = await res.json();
    renderShootoutResults(data.results, data.ranking);
  } catch (err) {
    alert("Shootout failed: " + err.message);
  } finally {
    btn.textContent = "Run Shootout";
    btn.disabled = false;
  }
}

function renderShootoutResults(results, ranking) {
  const chartDom = document.getElementById("shootout-bar-chart");
  if (activeCharts.shootout) activeCharts.shootout.dispose();
  const chart = echarts.init(chartDom, "dark");
  activeCharts.shootout = chart;

  const policies = ranking;
  const p99s = policies.map(p => results[p].latency.p99_ms);
  const maxWaits = policies.map(p => results[p].wait_time.max_ms);

  chart.setOption({
    backgroundColor: "transparent",
    tooltip: { trigger: "axis" },
    legend: { data: ["p99 Latency (ms)", "Max Wait Time (ms - Starvation)"] },
    xAxis: { type: "category", data: policies.map(p => p.toUpperCase()) },
    yAxis: { type: "value", name: "Time (ms)" },
    series: [
      { name: "p99 Latency (ms)", type: "bar", data: p99s, itemStyle: { color: "#38bdf8" } },
      { name: "Max Wait Time (ms - Starvation)", type: "bar", data: maxWaits, itemStyle: { color: "#f87171" } }
    ]
  });

  let html = `<table><thead><tr><th>Rank</th><th>Policy</th><th>p99 Latency (ms)</th><th>p50 Latency (ms)</th><th>Max Wait (ms)</th><th>Goodput (req/s)</th><th>Fairness Index</th></tr></thead><tbody>`;
  policies.forEach((p, idx) => {
    const r = results[p];
    html += `<tr>
      <td>#${idx + 1}</td>
      <td><strong>${p.toUpperCase()}</strong></td>
      <td>${r.latency.p99_ms.toFixed(1)}</td>
      <td>${r.latency.p50_ms.toFixed(1)}</td>
      <td>${r.wait_time.max_ms.toFixed(1)}</td>
      <td>${r.goodput_req_per_s.toFixed(1)}</td>
      <td>${r.jains_fairness_index.toFixed(3)}</td>
    </tr>`;
  });
  html += `</tbody></table>`;
  document.getElementById("shootout-table-box").innerHTML = html;
}

// Custom Policy Tab
let policyTemplates = {};
async function initCustomTemplates() {
  try {
    const res = await fetch("/api/templates");
    policyTemplates = await res.json();
    loadSelectedTemplate();
  } catch (e) {}
}

function loadSelectedTemplate() {
  const sel = document.getElementById("custom-template-select").value;
  if (policyTemplates[sel]) {
    document.getElementById("custom-code-editor").value = policyTemplates[sel].code;
  }
}

async function handleCustomPolicySubmit() {
  const btn = document.getElementById("btn-run-custom");
  btn.textContent = "Executing Sandbox...";
  btn.disabled = true;

  const code = document.getElementById("custom-code-editor").value;
  const payload = {
    code: code,
    trace_name: "epa",
    num_servers: 2,
    load_multiplier: 2.0,
    max_requests: 3000
  };

  try {
    const res = await fetch("/api/custom_policy", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });
    const data = await res.json();
    renderCustomResults(data);
  } catch (err) {
    alert("Sandbox request failed: " + err.message);
  } finally {
    btn.textContent = "Execute Sandboxed Simulation";
    btn.disabled = false;
  }
}

function renderCustomResults(data) {
  const badge = document.getElementById("custom-status-badge");
  const alertBox = document.getElementById("custom-error-alert");

  if (data.custom_policy_status === "rejected" || data.custom_policy_status === "error" || data.custom_policy_status === "timeout") {
    badge.className = "badge badge-danger";
    badge.textContent = `Status: ${data.custom_policy_status.toUpperCase()} (Fell back to FCFS)`;
    alertBox.textContent = data.custom_policy_error;
    alertBox.classList.remove("hidden");
  } else {
    badge.className = "badge badge-success";
    badge.textContent = "Status: SUCCESS (Sandboxed Subprocess)";
    alertBox.classList.add("hidden");
  }

  document.getElementById("cust-pol").textContent = data.policy;
  document.getElementById("cust-thr").textContent = data.throughput_req_per_s.toFixed(1);
  document.getElementById("cust-p99").textContent = data.latency.p99_ms.toFixed(1);
  document.getElementById("cust-maxwait").textContent = data.wait_time.max_ms.toFixed(1);
  document.getElementById("cust-jain").textContent = data.jains_fairness_index.toFixed(3);
  document.getElementById("cust-drop").textContent = (data.drop_rate * 100).toFixed(2);

  // Render small bar comparison vs standard
  const chartDom = document.getElementById("custom-comparison-chart");
  if (activeCharts.customComp) activeCharts.customComp.dispose();
  const chart = echarts.init(chartDom, "dark");
  activeCharts.customComp = chart;

  chart.setOption({
    backgroundColor: "transparent",
    tooltip: { trigger: "axis" },
    xAxis: { type: "category", data: ["p99 Latency (ms)", "Max Wait (ms)"] },
    yAxis: { type: "value" },
    series: [{
      type: "bar",
      data: [data.latency.p99_ms, data.wait_time.max_ms],
      itemStyle: { color: "#38bdf8" }
    }]
  });
}

// Datasets Tab
async function loadTraces() {
  try {
    const res = await fetch("/api/traces");
    tracesMetadata = await res.json();
    const sel = document.getElementById("dataset-selector");
    sel.innerHTML = "";
    Object.keys(tracesMetadata).forEach(k => {
      const opt = document.createElement("option");
      opt.value = k;
      opt.textContent = `${k.toUpperCase()} (${tracesMetadata[k].total_requests.toLocaleString()} reqs)`;
      sel.appendChild(opt);
    });
    handleDatasetChange();
  } catch (e) {}
}

function handleDatasetChange() {
  const selKey = document.getElementById("dataset-selector").value;
  const d = tracesMetadata[selKey];
  if (!d) return;

  document.getElementById("ds-total").textContent = d.total_requests.toLocaleString();
  document.getElementById("ds-dur").textContent = `${d.duration_days.toFixed(1)} days (${d.duration_seconds.toFixed(0)}s)`;
  document.getElementById("ds-rate").textContent = `${d.avg_req_per_s.toFixed(2)}`;
  document.getElementById("ds-st").textContent = `${d.service_time_distribution.mean_ms.toFixed(2)}`;
  document.getElementById("ds-hurst").textContent = `${d.burstiness.hurst_parameter}`;
  document.getElementById("ds-book").textContent = `${d.class_breakdown.book_ratio_pct.toFixed(1)}%`;

  // Timeline
  const tlDom = document.getElementById("dataset-timeline-chart");
  if (activeCharts.dsTimeline) activeCharts.dsTimeline.dispose();
  const chartTl = echarts.init(tlDom, "dark");
  activeCharts.dsTimeline = chartTl;

  const diurnal = d.diurnal_hourly_rates || [];
  chartTl.setOption({
    backgroundColor: "transparent",
    tooltip: { trigger: "axis" },
    xAxis: { type: "category", data: Array.from({length: diurnal.length}, (_, i) => `Hour ${i}`), name: "Hour" },
    yAxis: { type: "value", name: "Avg Arrival Rate (req/s)" },
    series: [{
      name: "Arrival Rate",
      type: "bar",
      data: diurnal,
      itemStyle: { color: "#38bdf8" }
    }]
  });

  // Size distribution
  const distDom = document.getElementById("dataset-dist-chart");
  if (activeCharts.dsDist) activeCharts.dsDist.dispose();
  const chartDist = echarts.init(distDom, "dark");
  activeCharts.dsDist = chartDist;

  const st = d.service_time_distribution;
  chartDist.setOption({
    backgroundColor: "transparent",
    tooltip: { trigger: "axis" },
    xAxis: { type: "category", data: ["p50", "p90", "p95", "p99", "Mean"] },
    yAxis: { type: "value", name: "Service Time (ms)" },
    series: [{
      name: "Service Time (ms)",
      type: "bar",
      data: [st.p50_ms, st.p90_ms, st.p95_ms, st.p99_ms, st.mean_ms],
      itemStyle: { color: "#34d399" }
    }]
  });
}
