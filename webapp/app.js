(function () {
  const tg = window.Telegram && window.Telegram.WebApp ? window.Telegram.WebApp : null;
  const state = {
    duration: 5,
    busy: false,
    apiBase: resolveApiBase(),
    route: "Local API",
  };

  const elements = {
    laptopStatus: document.getElementById("laptopStatus"),
    cameraStatus: document.getElementById("cameraStatus"),
    laptopDot: document.getElementById("laptopDot"),
    cameraDot: document.getElementById("cameraDot"),
    uptime: document.getElementById("uptimeValue"),
    lastCommand: document.getElementById("lastCommandValue"),
    route: document.getElementById("routeValue"),
    toast: document.getElementById("toast"),
    photoButton: document.getElementById("photoButton"),
    recordButton: document.getElementById("recordButton"),
    refreshButton: document.getElementById("refreshButton"),
    restartButton: document.getElementById("restartButton"),
    themeButton: document.getElementById("themeButton"),
    segments: Array.from(document.querySelectorAll(".segment")),
  };

  function resolveApiBase() {
    const saved = window.localStorage.getItem("cameraApiBase");
    if (saved) return saved.replace(/\/$/, "");
    if (window.location.hostname === "localhost" || window.location.hostname === "127.0.0.1") {
      return window.location.origin;
    }
    return "http://127.0.0.1:8000";
  }

  function ownerId() {
    return tg && tg.initDataUnsafe && tg.initDataUnsafe.user ? tg.initDataUnsafe.user.id : null;
  }

  function setBusy(value) {
    state.busy = value;
    elements.photoButton.disabled = value;
    elements.recordButton.disabled = value;
    elements.refreshButton.disabled = value;
    elements.restartButton.disabled = value;
  }

  function showToast(message) {
    elements.toast.textContent = message;
    elements.toast.classList.add("visible");
    window.clearTimeout(showToast.timer);
    showToast.timer = window.setTimeout(() => {
      elements.toast.classList.remove("visible");
    }, 2800);
  }

  function applyTheme() {
    const saved = window.localStorage.getItem("cameraTheme");
    const telegramScheme = tg && tg.colorScheme ? tg.colorScheme : "dark";
    const theme = saved || telegramScheme;
    document.documentElement.classList.toggle("light", theme === "light");
  }

  function toggleTheme() {
    const next = document.documentElement.classList.contains("light") ? "dark" : "light";
    window.localStorage.setItem("cameraTheme", next);
    applyTheme();
  }

  function updateStatus(data) {
    const cameraOk = Boolean(data.camera_available);
    elements.laptopStatus.textContent = data.laptop_online ? "Online" : "Offline";
    elements.cameraStatus.textContent = cameraOk ? "Available" : "Unavailable";
    elements.uptime.textContent = data.uptime || "--";
    elements.lastCommand.textContent = data.last_command
      ? `${data.last_command} / ${data.last_command_status || "n/a"}`
      : "--";
    elements.laptopDot.className = `status-dot ${data.laptop_online ? "online" : "offline"}`;
    elements.cameraDot.className = `status-dot ${cameraOk ? "online" : "offline"}`;
    elements.route.textContent = state.route;
  }

  async function localRequest(path, options) {
    const response = await fetch(`${state.apiBase}${path}`, {
      mode: "cors",
      cache: "no-store",
      ...options,
      headers: {
        "Content-Type": "application/json",
        ...(options && options.headers ? options.headers : {}),
      },
    });

    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error(data.detail || `HTTP ${response.status}`);
    }
    return data;
  }

  function sendViaTelegram(payload) {
    if (!tg || typeof tg.sendData !== "function") {
      throw new Error("Telegram Mini App bridge is not available.");
    }
    tg.sendData(JSON.stringify(payload));
    state.route = "Telegram";
    elements.route.textContent = state.route;
  }

  async function sendCommand(command, duration) {
    const userId = ownerId();
    const payload = { user_id: userId || 0, command, duration };
    setBusy(true);

    try {
      if (!userId) {
        throw new Error("No Telegram user id in Mini App context.");
      }

      const result = await localRequest("/api/command", {
        method: "POST",
        body: JSON.stringify(payload),
      });
      state.route = "Local API";
      elements.route.textContent = state.route;
      showToast(result.message || "Command sent");
      await refreshStatus(false);
    } catch (error) {
      try {
        sendViaTelegram({ command, duration });
        showToast("Sent through Telegram");
      } catch (fallbackError) {
        showToast(fallbackError.message || error.message);
      }
    } finally {
      setBusy(false);
    }
  }

  async function refreshStatus(showResult) {
    const userId = ownerId();
    try {
      if (!userId) {
        throw new Error("No Telegram user id in Mini App context.");
      }
      const data = await localRequest(`/api/status?user_id=${encodeURIComponent(userId)}`, {
        method: "GET",
      });
      state.route = "Local API";
      updateStatus(data);
      if (showResult) showToast("Status refreshed");
    } catch (error) {
      state.route = "Telegram";
      elements.route.textContent = state.route;
      elements.cameraStatus.textContent = "Via Telegram";
      elements.cameraDot.className = "status-dot unknown";
      try {
        sendViaTelegram({ command: "status" });
        if (showResult) showToast("Status requested in Telegram");
      } catch (fallbackError) {
        if (showResult) showToast(fallbackError.message || error.message);
      }
    }
  }

  function bindEvents() {
    elements.photoButton.addEventListener("click", () => sendCommand("photo"));
    elements.recordButton.addEventListener("click", () => sendCommand("video", state.duration));
    elements.refreshButton.addEventListener("click", () => refreshStatus(true));
    elements.restartButton.addEventListener("click", () => sendCommand("restart"));
    elements.themeButton.addEventListener("click", toggleTheme);

    elements.segments.forEach((button) => {
      button.addEventListener("click", () => {
        state.duration = Number(button.dataset.duration);
        elements.segments.forEach((item) => item.classList.toggle("active", item === button));
      });
    });
  }

  function bootTelegram() {
    if (!tg) return;
    tg.ready();
    tg.expand();
    if (tg.MainButton) tg.MainButton.hide();
  }

  bootTelegram();
  applyTheme();
  bindEvents();
  refreshStatus(false);
})();
