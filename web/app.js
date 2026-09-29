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

// Backend outcome tag -> banner style and operator-facing wording.
const ERROR_INFO = {
  input: {
    label: "输入有误",
    hint: "请检查刚填写的数值后重试",
    cls: "notice-input",
  },
  rejected: {
    label: "设备不允许",
    hint: "当前工况不满足条件，请按提示处理设备后再操作",
    cls: "notice-rejected",
  },
  failure: {
    label: "系统故障",
    hint: "请联系维护人员，并凭错误编号查询操作记录",
    cls: "notice-failure",
  },
};

const OUTCOME_LABELS = {
  ok: "成功",
  input: "参数错误",
  rejected: "设备拒绝",
  failure: "系统错误",
};

const OPERATOR_KEY = "linecontrol.operator";
let noticeTimer = null;

function fmt(value, digits) {
  if (value === null || value === undefined) {
    return "-";
  }
  if (typeof value === "number") {
    return value.toFixed(digits === undefined ? 1 : digits);
  }
  return String(value);
}

function operatorName() {
  return (localStorage.getItem(OPERATOR_KEY) || "").trim();
}

function requestHeaders(automatic) {
  const headers = { Accept: "application/json" };
  const name = operatorName();
  if (name) {
    headers["X-Operator"] = name;
  }
  if (automatic) {
    headers["X-Auto-Request"] = "1";
  }
  return headers;
}

async function loadJSON(path, options, automatic) {
  const settings = Object.assign(
    { headers: requestHeaders(Boolean(automatic)) },
    options || {}
  );
  let response;
  try {
    response = await fetch(path, settings);
  } catch (networkError) {
    const error = new Error("无法连接控制台服务，请检查网络");
    error.kind = "failure";
    error.ref = "";
    throw error;
  }
  let data = null;
  try {
    data = await response.json();
  } catch (parseError) {
    data = null;
  }
  if (!response.ok || !data || data.ok === false) {
    const kind =
      data && ERROR_INFO[data.type] ? data.type
      : response.status === 400 ? "input"
      : response.status === 409 ? "rejected"
      : "failure";
    const info = ERROR_INFO[kind];
    const detail = data && data.detail && data.detail.detail ? data.detail.detail : null;
    const message = (data && data.error) || detail || info.hint;
    const error = new Error(message);
    error.kind = kind;
    error.code = (data && data.code) || "";
    error.ref = (data && data.ref) || "";
    throw error;
  }
  return data;
}

function post(path, params) {
  const query = params ? "?" + new URLSearchParams(params).toString() : "";
  return loadJSON(path + query, { method: "POST" }, false);
}

function showNotice(kind, message, code, ref) {
  const node = document.getElementById("notice");
  if (!node) {
    return;
  }
  if (kind === "ok") {
    node.className = "notice notice-ok";
    node.innerHTML = "<span class=\"notice-tag\">成功</span><span>" +
      (message || "操作已执行") + "</span>";
  } else {
    const info = ERROR_INFO[kind] || ERROR_INFO.failure;
    node.className = "notice " + info.cls;
    const parts = [
      "<span class=\"notice-tag\">" + info.label + "</span>",
      "<span class=\"notice-msg\">" + message + "</span>",
    ];
    if (code) {
      parts.push("<span class=\"notice-meta\">代码 " + code + "</span>");
    }
    if (ref) {
      parts.push("<span class=\"notice-meta\">编号 " + ref + "</span>");
    }
    node.innerHTML = parts.join("");
  }
  node.classList.remove("hidden");
  if (noticeTimer) {
    clearTimeout(noticeTimer);
  }
  const ttl = kind === "ok" ? 2500 : 8000;
  noticeTimer = setTimeout(function () {
    node.classList.add("hidden");
  }, ttl);
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

function fmtStamp(iso) {
  if (!iso) {
    return "";
  }
  const when = new Date(iso);
  return when.toLocaleString();
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

function renderRequests(records) {
  const list = document.getElementById("requestList");
  list.innerHTML = "";
  (records || []).forEach(function (record) {
    const li = document.createElement("li");
    li.className = "req req-" + record.outcome;
    const label = OUTCOME_LABELS[record.outcome] || record.outcome;
    const params = Object.keys(record.params || {})
      .map(function (key) { return key + "=" + record.params[key]; })
      .join(" ");
    const tail = record.message
      ? " — " + record.message + (record.code ? " (" + record.code + ")" : "")
      : "";
    li.textContent =
      fmtStamp(record.at) + " " + label + " " +
      (record.operator || "-") + " " +
      record.method + " " + record.path +
      (params ? " ?" + params : "") + tail;
    li.title = record.ref ? "记录编号 " + record.ref : "";
    list.appendChild(li);
  });
  if (!list.children.length) {
    const li = document.createElement("li");
    li.className = "req-empty";
    li.textContent = "无匹配记录";
    list.appendChild(li);
  }
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
    const data = await loadJSON("/api/state", {}, true);
    renderState(data.state || {});
    renderSequence(data.state ? data.state.sequence : null);
    const summary = await loadJSON("/api/audit/summary", {}, true);
    renderSummary(summary.summary || {});
  } catch (error) {
    // Background polling stays quiet so it never covers a real operator error.
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
  const data = await loadJSON("/api/audit" + (query ? "?" + query : ""), {}, true);
  renderEvents(data.events || []);
}

async function refreshRequests(outcome, limit) {
  const params = {};
  if (outcome) {
    params.outcome = outcome;
  }
  if (limit) {
    params.limit = limit;
  }
  const query = new URLSearchParams(params).toString();
  const data = await loadJSON(
    "/api/requests" + (query ? "?" + query : ""),
    {},
    true
  );
  renderRequests(data.requests || []);
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
    showNotice("ok", "垂度 " + fmt(data.sag, 2) + " mm");
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
  "request-query": (form) =>
    refreshRequests(form.outcome.value, form.limit.value),
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
      await call();
      await refresh();
      if (button.dataset.op !== "strip-sag") {
        showNotice("ok", "操作已执行");
      }
    } catch (error) {
      showNotice(error.kind || "failure", error.message, error.code, error.ref);
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
      await call(form);
      await refresh();
      if (form.dataset.form !== "audit-query" &&
          form.dataset.form !== "request-query") {
        showNotice("ok", "操作已执行");
      }
    } catch (error) {
      showNotice(error.kind || "failure", error.message, error.code, error.ref);
    }
  });
});

document.querySelectorAll("button.tab").forEach(function (button) {
  button.addEventListener("click", function () {
    document.querySelectorAll(".tabpage").forEach(function (page) {
      page.classList.add("hidden");
    });
    const target = document.getElementById("tab-" + button.dataset.tab);
    if (target) {
      target.classList.remove("hidden");
    }
  });
});

(function initOperator() {
  const input = document.getElementById("operator");
  if (!input) {
    return;
  }
  input.value = operatorName();
  input.addEventListener("change", function () {
    const name = input.value.trim().slice(0, 32);
    input.value = name;
    if (name) {
      localStorage.setItem(OPERATOR_KEY, name);
    } else {
      localStorage.removeItem(OPERATOR_KEY);
    }
  });
})();

refresh();
refreshRequests("", 30);
setInterval(refresh, 3000);
