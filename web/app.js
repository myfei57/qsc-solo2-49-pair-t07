const LAMP_SOURCES = [
  ["对中确认", (s) => s.aligned],
  ["张力已落盘", (s) => s.tension && s.tension.allowed],
  ["酸泵运行", (s) => s.pump && s.pump.running],
  ["喷淋开启", (s) => s.pickle && s.pickle.rinsing],
  ["排风建立", (s) => s.exit && s.exit.exhaust],
  ["烘干升温", (s) => s.dry && s.dry.heating],
  ["焊接联锁释放", (s) => s.weld && s.weld.interlock],
  ["带尾已冲净", (s) => s.strip && !s.strip.tailDirty],
];

const RESULT_TEXT = {
  ok: "成功",
  input: "参数填错",
  denied: "设备不允许",
  error: "系统故障",
};

function getOperator() {
  return localStorage.getItem("linecontrol.operator") || "";
}

function setOperator(name) {
  localStorage.setItem("linecontrol.operator", name);
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function noticeHtml(data) {
  const title = data.title || "操作失败";
  const hint = data.hint || data.error || "request failed";
  const code = data.code
    ? '<span class="notice-code">代码: ' + escapeHtml(data.code) + "</span>"
    : "";
  return (
    '<span class="notice-title">' +
    escapeHtml(title) +
    "</span>" +
    escapeHtml(hint) +
    code
  );
}

let noticeTimer = null;

function showNotice(category, html) {
  const node = document.getElementById("notice");
  if (!node) {
    return;
  }
  node.className = "notice " + category;
  node.innerHTML = html;
  if (noticeTimer) {
    clearTimeout(noticeTimer);
  }
  if (category === "ok") {
    noticeTimer = setTimeout(function () {
      node.classList.add("hidden");
    }, 3000);
  }
}

function showFailure(data) {
  showNotice(data.errorType || "error", noticeHtml(data));
}

function fmt(value, digits) {
  if (value === null || value === undefined) {
    return "-";
  }
  if (typeof value === "number") {
    return value.toFixed(digits === undefined ? 1 : digits);
  }
  return String(value);
}

async function loadJSON(path, options) {
  const response = await fetch(path, options);
  let data;
  try {
    data = await response.json();
  } catch (error) {
    throw {
      errorType: "error",
      title: RESULT_TEXT.error,
      hint: "服务器没有返回有效响应（HTTP " + response.status + "）",
      code: "http-" + response.status,
    };
  }
  if (!data.ok) {
    throw data;
  }
  return data;
}

function post(path, params) {
  const query = params ? "?" + new URLSearchParams(params).toString() : "";
  const headers = { Accept: "application/json" };
  const operator = getOperator();
  if (operator) {
    headers["X-Operator"] = operator;
  }
  return loadJSON(path + query, { method: "POST", headers });
}

function setText(id, value) {
  const node = document.getElementById(id);
  if (node) {
    node.textContent = value;
  }
}

function renderState(state) {
  const badge = document.getElementById("phase");
  badge.textContent = state.phase || "idle";
  badge.className = "badge " + (state.phase === "fault" ? "fault" : "running");
  setText("coil", state.coil || "-");
  setText("head", fmt(state.head, 1));
  setText("aligned", state.aligned ? "已确认" : "未确认");
  setText("track", fmt(state.strip ? state.strip.track : 0, 1));
  setText("tension", fmt(state.tension ? state.tension.setpoint : 0, 1));
  setText("effective", fmt(state.tension ? state.tension.effective : 0, 1));
  setText("concentration", fmt(state.pickle ? state.pickle.concentration : 0, 2));
  setText("level", fmt(state.pickle ? state.pickle.level : 0, 2));
  setText("rinsing", state.pickle && state.pickle.rinsing ? "开" : "关");
  setText("pump", state.pump && state.pump.running ? "运行" : "停");
  setText("dry", state.dry && state.dry.heating ? "升温" : "停");
  setText("tail", state.strip && state.strip.tailDirty ? "脏" : "净");
  setText("speed", fmt(state.strip ? state.strip.speed : 0, 2));
  setText("travel", fmt(state.strip ? state.strip.travel : 0, 1));

  const lamps = document.getElementById("lamps");
  lamps.innerHTML = "";
  LAMP_SOURCES.forEach(function (entry) {
    const li = document.createElement("li");
    const on = Boolean(entry[1](state));
    li.className = "lamp " + (on ? "on" : "off");
    li.textContent = entry[0];
    lamps.appendChild(li);
  });

  const alarms = document.getElementById("alarmList");
  alarms.innerHTML = "";
  const active = state.alarms || [];
  if (!active.length) {
    const li = document.createElement("li");
    li.className = "clear";
    li.textContent = "无活动告警";
    alarms.appendChild(li);
  } else {
    active.forEach(function (id) {
      const li = document.createElement("li");
      li.textContent = id;
      alarms.appendChild(li);
    });
  }
}

function renderEvents(events) {
  const list = document.getElementById("auditList");
  list.innerHTML = "";
  events.slice(-40).reverse().forEach(function (event) {
    const li = document.createElement("li");
    const when = event.at ? new Date(event.at).toLocaleTimeString() : "";
    li.textContent = when + " [" + event.kind + "] " + (event.message || "");
    list.appendChild(li);
  });
}

function renderSummary(summary) {
  const list = document.getElementById("summary");
  list.innerHTML = "";
  Object.keys(summary).sort().forEach(function (kind) {
    const li = document.createElement("li");
    li.textContent = kind + " x " + summary[kind];
    list.appendChild(li);
  });
}

function renderSequence(sequence) {
  const list = document.getElementById("sequenceList");
  list.innerHTML = "";
  if (!sequence) {
    return;
  }
  const head = document.createElement("li");
  head.textContent = "流程 " + (sequence.label || "-");
  list.appendChild(head);
  (sequence.steps || []).forEach(function (step) {
    const li = document.createElement("li");
    li.className = step.ok ? "step-ok" : "step-bad";
    li.textContent = (step.ok ? "通过 " : "失败 ") + step.name + (step.detail ? " :: " + step.detail : "");
    list.appendChild(li);
  });
}

async function refresh() {
  try {
    const data = await loadJSON("/api/state");
    renderState(data.state || {});
    renderSequence(data.state ? data.state.sequence : null);
    const summary = await loadJSON("/api/audit/summary");
    renderSummary(summary.summary || {});
  } catch (error) {
    console.error(error);
  }
}

async function refreshAudit(kind, limit) {
  const params = {};
  if (kind) {
    params.kind = kind;
  }
  if (limit) {
    params.limit = limit;
  }
  const query = new URLSearchParams(params).toString();
  const data = await loadJSON("/api/audit" + (query ? "?" + query : ""));
  renderEvents(data.events || []);
}

const OP_CALLS = {
  "weld-confirm": () => post("/api/weld/confirm"),
  "weld-alarm": () => post("/api/weld/alarm"),
  "weld-clear": () => post("/api/weld/clear"),
  "weld-release": () => post("/api/weld/release"),
  "dry-heat": () => post("/api/dry/heat"),
  "dry-reheat": () => post("/api/dry/reheat"),
  "entry-correct": () => post("/api/entry/correct"),
  "stop": () => post("/api/stop"),
  "strip-sag": async () => {
    const data = await loadJSON("/api/strip/sag");
    return "垂度 " + fmt(data.sag, 2) + " mm";
  },
};

const FORM_CALLS = {
  "weld-power": (form) => post("/api/weld/power", readForm(form)),
  "weld-splice": (form) => post("/api/weld/splice", readForm(form)),
  "tension-ramp": (form) => post("/api/tension/ramp", readForm(form)),
  "tension-calibrate": (form) => post("/api/tension/calibrate", readForm(form)),
  "pump-start": (form) => post("/api/pump/start", readForm(form)),
  "pump-replenish": (form) => post("/api/pump/replenish", readForm(form)),
  "pickle-calibrate": (form) => post("/api/pickle/calibrate", readForm(form)),
  "dry-dew": (form) => post("/api/dry/dew", readForm(form)),
  "dry-heat-target": (form) => post("/api/dry/heat-target", readForm(form)),
  "strip-advance": (form) => post("/api/strip/advance", readForm(form)),
  "strip-speed": (form) => post("/api/strip/speed", readForm(form)),
  "entry-offset": (form) => post("/api/entry/offset", readForm(form)),
  "entry-sample": (form) => post("/api/entry/sample", readForm(form)),
  "shear-offset": (form) => post("/api/exit/shear-offset", readForm(form)),
  "exit-weight": (form) => post("/api/exit/weight", readForm(form)),
  "cycle": (form) => post("/api/cycle", readForm(form)),
  "audit-query": (form) => refreshAudit(form.kind.value, form.limit.value),
};

function readForm(form) {
  const data = {};
  new FormData(form).forEach(function (value, key) {
    data[key] = value;
  });
  return data;
}

document.querySelectorAll("button[data-op]").forEach(function (button) {
  button.addEventListener("click", async function () {
    const call = OP_CALLS[button.dataset.op];
    if (!call) {
      return;
    }
    try {
      const detail = await call();
      showNotice(
        "ok",
        '<span class="notice-title">操作已执行</span>' + escapeHtml(detail || "")
      );
      await refresh();
    } catch (data) {
      showFailure(data);
    }
  });
});

document.querySelectorAll("form[data-form]").forEach(function (form) {
  form.addEventListener("submit", async function (event) {
    event.preventDefault();
    const call = FORM_CALLS[form.dataset.form];
    if (!call) {
      return;
    }
    try {
      const detail = await call(form);
      // 查询类表单刷新列表即可，不弹"已执行"
      if (form.dataset.form !== "audit-query") {
        showNotice(
          "ok",
          '<span class="notice-title">操作已执行</span>' + escapeHtml(detail || "")
        );
      }
      await refresh();
    } catch (data) {
      showFailure(data);
    }
  });
});

function renderRequests(records) {
  const tbody = document.querySelector("#requestTable tbody");
  if (!tbody) {
    return;
  }
  tbody.innerHTML = "";
  if (!records.length) {
    const tr = document.createElement("tr");
    const td = document.createElement("td");
    td.colSpan = 8;
    td.textContent = "暂无记录";
    td.style.color = "#627d98";
    tr.appendChild(td);
    tbody.appendChild(tr);
    return;
  }
  records.forEach(function (rec) {
    const tr = document.createElement("tr");
    if (rec.result === "denied" || rec.result === "error") {
      tr.className = "row-failed";
    } else if (rec.result === "input") {
      tr.className = "row-input";
    }
    const when = rec.at ? new Date(rec.at).toLocaleString() : "";
    const params = Object.keys(rec.params || {})
      .map(function (k) {
        return k + "=" + rec.params[k];
      })
      .join(" ");
    let reason = "";
    if (rec.ok) {
      reason = "成功";
    } else if (rec.result === "input") {
      reason = rec.message || "参数缺失或格式不对";
    } else {
      reason = rec.message || rec.code;
    }

    function addCell(text, className) {
      const td = document.createElement("td");
      td.textContent = text;
      if (className) {
        td.className = className;
      }
      tr.appendChild(td);
    }

    addCell(when);
    addCell(rec.operator || "-");
    addCell(rec.label || rec.action);
    const tag = document.createElement("td");
    const span = document.createElement("span");
    span.className = "tag " + rec.result;
    span.textContent = RESULT_TEXT[rec.result] || rec.result;
    tag.appendChild(span);
    tr.appendChild(tag);
    addCell(reason, "reason");
    addCell(params, "params");
    addCell(rec.durationMs >= 0 ? rec.durationMs + " ms" : "");
    addCell(rec.handle ? rec.handle.slice(0, 8) : "");
    if (rec.handle) {
      tr.title = "关联号: " + rec.handle;
    }
    tbody.appendChild(tr);
  });
}

async function refreshRequests() {
  const form = document.getElementById("requestQueryForm");
  const limit = form && form.limit.value ? form.limit.value : "50";
  const filter = form ? form.filter.value : "all";
  const params = new URLSearchParams({ limit: limit });
  if (filter === "failed") {
    params.set("failed", "1");
  }
  try {
    const data = await loadJSON("/api/audit/requests?" + params.toString());
    let records = data.requests || [];
    if (filter === "input" || filter === "denied") {
      records = records.filter(function (rec) {
        return rec.result === filter;
      });
    }
    renderRequests(records);
  } catch (error) {
    // 轮询失败保持安静，避免遮挡操作工正在看的反馈
  }
}

document.querySelectorAll("button.tab").forEach(function (button) {
  button.addEventListener("click", function () {
    document.querySelectorAll(".tabpage").forEach(function (page) {
      page.classList.add("hidden");
    });
    const target = document.getElementById("tab-" + button.dataset.tab);
    if (target) {
      target.classList.remove("hidden");
    }
    if (button.dataset.tab === "audit") {
      refreshRequests();
    }
  });
});

const operatorForm = document.getElementById("operatorForm");
const operatorInput = document.getElementById("operatorInput");
if (operatorInput) {
  operatorInput.value = getOperator();
}
if (operatorForm) {
  operatorForm.addEventListener("submit", function (event) {
    event.preventDefault();
    const name = operatorInput.value.trim();
    setOperator(name);
    showNotice(
      "ok",
      '<span class="notice-title">已记住工号</span>' +
        escapeHtml(name || "（未填，将用工位 IP 记录）")
    );
  });
}

const requestQueryForm = document.getElementById("requestQueryForm");
if (requestQueryForm) {
  requestQueryForm.addEventListener("submit", function (event) {
    event.preventDefault();
    refreshRequests();
  });
}

refresh();
setInterval(refresh, 3000);
setInterval(function () {
  const auditPage = document.getElementById("tab-audit");
  if (auditPage && !auditPage.classList.contains("hidden")) {
    refreshRequests();
  }
}, 5000);
