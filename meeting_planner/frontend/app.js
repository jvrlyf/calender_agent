

const API_BASE = "";   // same origin
const SESSION_KEY = "mp_session_id";

// ── session id ──────────────────────────────────────
function getSessionId() {
  let id = localStorage.getItem(SESSION_KEY);
  if (!id) {
    id = crypto.randomUUID ? crypto.randomUUID() : "s-" + Date.now();
    localStorage.setItem(SESSION_KEY, id);
  }
  return id;
}

const sessionId = getSessionId();

// ── DOM refs ────────────────────────────────────────
const messagesEl = document.getElementById("messages");
const inputEl    = document.getElementById("userInput");
const sendBtn    = document.getElementById("sendBtn");

// ── helpers ─────────────────────────────────────────
function scrollToBottom() {
  const container = document.getElementById("chatContainer");
  container.scrollTop = container.scrollHeight;
}

function addMessage(role, text) {
  const div = document.createElement("div");
  div.className = `message ${role}`;

  const bubble = document.createElement("div");
  bubble.className = "bubble";
  bubble.textContent = text;

  div.appendChild(bubble);
  messagesEl.appendChild(div);
  scrollToBottom();
}

function showTyping() {
  const div = document.createElement("div");
  div.className = "typing-indicator";
  div.id = "typingIndicator";
  div.innerHTML = "<span></span><span></span><span></span>";
  messagesEl.appendChild(div);
  scrollToBottom();
}

function hideTyping() {
  const el = document.getElementById("typingIndicator");
  if (el) el.remove();
}

function setInputEnabled(enabled) {
  inputEl.disabled = !enabled;
  sendBtn.disabled = !enabled;
}

// ── send message ────────────────────────────────────
async function sendMessage() {
  const text = inputEl.value.trim();
  if (!text) return;

  addMessage("user", text);
  inputEl.value = "";
  setInputEnabled(false);
  showTyping();

  try {
    const res = await fetch(`${API_BASE}/api/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ session_id: sessionId, message: text }),
    });

    hideTyping();

    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: "Server error" }));
      addMessage("assistant", `❌ Error: ${err.detail || res.statusText}`);
      return;
    }

    const data = await res.json();
    addMessage("assistant", data.response);
  } catch (err) {
    hideTyping();
    addMessage("assistant", `❌ Network error: ${err.message}`);
  } finally {
    setInputEnabled(true);
    inputEl.focus();
  }
}

// ── enter key ───────────────────────────────────────
inputEl.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    sendMessage();
  }
});

// ── new session button (optional: clear) ────────────
function clearSession() {
  fetch(`${API_BASE}/api/session/${sessionId}`, { method: "DELETE" })
    .then(() => {
      localStorage.removeItem(SESSION_KEY);
      location.reload();
    });
}