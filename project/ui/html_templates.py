"""HTML templates used by the FastAPI UI."""

AUTH_HTML = """
<!doctype html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Login</title>
  <style>
    * { box-sizing: border-box; }
    body {
      margin: 0;
      min-height: 100vh;
      display: flex;
      align-items: center;
      justify-content: center;
      background: #f7f7f8;
      font-family: "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif;
      color: #111827;
      padding: 16px;
    }
    .card {
      width: 420px;
      max-width: 100%;
      background: #fff;
      border: 1px solid #e5e7eb;
      border-radius: 14px;
      padding: 18px;
    }
    h2 {
      margin: 0 0 12px 0;
      font-size: 24px;
    }
    .tabs {
      display: flex;
      gap: 6px;
      margin-bottom: 12px;
    }
    .tab {
      flex: 1;
      border: 1px solid #d1d5db;
      border-radius: 10px;
      background: #fff;
      padding: 8px 10px;
      cursor: pointer;
      font-size: 14px;
    }
    .tab.active {
      background: #111827;
      color: #fff;
      border-color: #111827;
    }
    .form {
      display: none;
      flex-direction: column;
      gap: 10px;
    }
    .form.active {
      display: flex;
    }
    input {
      border: 1px solid #d1d5db;
      border-radius: 10px;
      padding: 10px 12px;
      font-size: 14px;
      outline: none;
    }
    button.submit {
      border: none;
      border-radius: 10px;
      background: #111827;
      color: #fff;
      padding: 10px 12px;
      cursor: pointer;
      font-size: 14px;
    }
    #msg {
      min-height: 18px;
      color: #374151;
      font-size: 13px;
      margin-top: 4px;
    }
    #msg.error {
      color: #dc2626;
    }
    .success-modal {
      position: fixed;
      inset: 0;
      display: none;
      align-items: center;
      justify-content: center;
      background: rgba(0, 0, 0, 0.35);
      z-index: 1000;
    }
    .success-modal.open {
      display: flex;
    }
    .success-panel {
      width: 420px;
      max-width: calc(100vw - 32px);
      background: #ffffff;
      border-radius: 14px;
      padding: 18px;
      border: 1px solid #e5e7eb;
    }
    .success-panel h3 {
      margin: 0 0 8px 0;
      font-size: 20px;
    }
    .success-panel p {
      margin: 0 0 14px 0;
      color: #4b5563;
      font-size: 14px;
      line-height: 1.45;
    }
    .success-ok {
      border: none;
      border-radius: 10px;
      background: #111827;
      color: #fff;
      padding: 10px 12px;
      cursor: pointer;
      font-size: 14px;
      width: 100%;
    }
  </style>
</head>
<body>
  <div class="card">
    <h2>Welcome</h2>
    <div class="tabs">
      <button class="tab active" id="loginTab">Login</button>
      <button class="tab" id="registerTab">Register</button>
    </div>

    <form id="loginForm" class="form active">
      <input id="loginUsername" placeholder="Username" autocomplete="username" />
      <input id="loginPassword" type="password" placeholder="Password" autocomplete="current-password" />
      <button class="submit" type="submit">Login</button>
    </form>

    <form id="registerForm" class="form">
      <input id="registerUsername" placeholder="Username" autocomplete="username" />
      <input id="registerPassword" type="password" placeholder="Password (min 6 chars)" autocomplete="new-password" />
      <input id="registerPasswordConfirm" type="password" placeholder="Confirm password" autocomplete="new-password" />
      <button class="submit" type="submit">Register</button>
    </form>

    <div id="msg"></div>
  </div>
  <div id="registerSuccessModal" class="success-modal">
    <div class="success-panel">
      <h3>Registration Successful</h3>
      <p>Your account has been created. Please login to continue.</p>
      <button id="registerSuccessOkBtn" class="success-ok">OK</button>
    </div>
  </div>

  <script>
    const el = {
      loginTab: document.getElementById("loginTab"),
      registerTab: document.getElementById("registerTab"),
      loginForm: document.getElementById("loginForm"),
      registerForm: document.getElementById("registerForm"),
      loginUsername: document.getElementById("loginUsername"),
      loginPassword: document.getElementById("loginPassword"),
      registerUsername: document.getElementById("registerUsername"),
      registerPassword: document.getElementById("registerPassword"),
      registerPasswordConfirm: document.getElementById("registerPasswordConfirm"),
      msg: document.getElementById("msg"),
      registerSuccessModal: document.getElementById("registerSuccessModal"),
      registerSuccessOkBtn: document.getElementById("registerSuccessOkBtn")
    };

    function setTab(mode) {
      const login = mode === "login";
      el.loginTab.classList.toggle("active", login);
      el.registerTab.classList.toggle("active", !login);
      el.loginForm.classList.toggle("active", login);
      el.registerForm.classList.toggle("active", !login);
      el.msg.textContent = "";
      el.msg.classList.remove("error");
    }

    function setMessage(text, isError = false) {
      el.msg.textContent = text || "";
      el.msg.classList.toggle("error", isError);
    }

    async function submitAuth(path, payload, redirectOnSuccess = true) {
      try {
        const res = await fetch(path, {
          method: "POST",
          headers: {"Content-Type":"application/json"},
          body: JSON.stringify(payload)
        });
        let data = {};
        try {
          data = await res.json();
        } catch {
          data = {ok: false, message: "Server returned invalid response."};
        }
        if (!res.ok || !data.ok) {
          setMessage(data.message || "Request failed.", true);
          return data;
        }
        if (redirectOnSuccess) {
          window.location.href = "/";
        }
        return data;
      } catch (e) {
        setMessage("Network error. Please try again.", true);
        return {ok: false};
      }
    }

    el.loginTab.addEventListener("click", () => setTab("login"));
    el.registerTab.addEventListener("click", () => setTab("register"));

    el.loginForm.addEventListener("submit", async (e) => {
      e.preventDefault();
      await submitAuth("/api/auth/login", {
        username: (el.loginUsername.value || "").trim(),
        password: el.loginPassword.value || ""
      });
    });

    el.registerForm.addEventListener("submit", async (e) => {
      e.preventDefault();
      const username = (el.registerUsername.value || "").trim();
      const password = el.registerPassword.value || "";
      const confirmPassword = el.registerPasswordConfirm.value || "";
      if (password !== confirmPassword) {
        setMessage("Passwords do not match.", true);
        return;
      }
      const data = await submitAuth("/api/auth/register", {
        username,
        password
      }, false);
      if (!data || !data.ok) return;
      setTab("login");
      el.loginUsername.value = username;
      el.registerPassword.value = "";
      el.registerPasswordConfirm.value = "";
      el.registerSuccessModal.classList.add("open");
    });

    el.registerSuccessOkBtn.addEventListener("click", () => {
      el.registerSuccessModal.classList.remove("open");
    });
    el.registerSuccessModal.addEventListener("click", (e) => {
      if (e.target === el.registerSuccessModal) {
        el.registerSuccessModal.classList.remove("open");
      }
    });
  </script>
</body>
</html>
"""


CHAT_HTML = """
<!doctype html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Agentic RAG Chat</title>
  <style>
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif;
      background: #f7f7f8;
      color: #111827;
    }
    .app {
      height: 100vh;
      display: flex;
      overflow: hidden;
    }
    .sidebar {
      width: 260px;
      min-width: 260px;
      max-width: 260px;
      border-right: 1px solid #e5e7eb;
      background: #fbfbfb;
      display: flex;
      flex-direction: column;
      padding: 10px;
      gap: 8px;
    }
    .top-btn {
      width: 100%;
      border: 1px solid #d1d5db;
      border-radius: 10px;
      background: #ffffff;
      color: #111827;
      padding: 10px 12px;
      text-align: left;
      cursor: pointer;
      font-size: 14px;
    }
    .top-btn:hover { background: #f3f4f6; }
    .sidebar-title {
      margin: 6px 4px 2px 4px;
      color: #6b7280;
      font-size: 12px;
      font-weight: 600;
    }
    .chat-list {
      flex: 1;
      overflow-y: auto;
      padding-right: 2px;
    }
    .sidebar-footer {
      border-top: 1px solid #e5e7eb;
      padding-top: 8px;
      display: flex;
      flex-direction: column;
      gap: 8px;
    }
    .user-name {
      padding: 8px 10px;
      font-size: 13px;
      color: #374151;
      border: 1px solid #e5e7eb;
      border-radius: 10px;
      background: #ffffff;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }
    .chat-item {
      position: relative;
      display: flex;
      align-items: center;
      gap: 6px;
      border-radius: 10px;
      padding: 8px 6px 8px 10px;
      margin-bottom: 2px;
      cursor: pointer;
    }
    .chat-item:hover { background: #f3f4f6; }
    .chat-item.active { background: #e5e7eb; }
    .chat-title {
      flex: 1;
      font-size: 14px;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }
    .chat-pin {
      color: #9ca3af;
      font-size: 12px;
    }
    .chat-menu-btn {
      width: 26px;
      height: 24px;
      border: none;
      background: transparent;
      border-radius: 6px;
      color: #4b5563;
      cursor: pointer;
      opacity: 0;
    }
    .chat-item:hover .chat-menu-btn, .chat-item.active .chat-menu-btn {
      opacity: 1;
    }
    .chat-menu-btn:hover { background: #e5e7eb; }
    .chat-menu {
      position: absolute;
      top: 34px;
      right: 8px;
      z-index: 20;
      width: 180px;
      border: 1px solid #e5e7eb;
      border-radius: 10px;
      background: #ffffff;
      box-shadow: 0 12px 24px rgba(0, 0, 0, 0.12);
      padding: 6px;
      display: none;
    }
    .chat-menu.open { display: block; }
    .chat-menu button {
      width: 100%;
      text-align: left;
      border: none;
      background: #fff;
      color: #111827;
      border-radius: 8px;
      padding: 8px 10px;
      cursor: pointer;
      font-size: 13px;
    }
    .chat-menu button:hover { background: #f3f4f6; }
    .chat-menu button.danger { color: #dc2626; }
    .rename-inline {
      flex: 1;
      display: flex;
      gap: 4px;
      align-items: center;
    }
    .rename-inline input {
      flex: 1;
      border: 1px solid #d1d5db;
      border-radius: 8px;
      padding: 4px 8px;
      font-size: 13px;
      min-width: 0;
    }
    .rename-inline button {
      border: none;
      background: #f3f4f6;
      border-radius: 6px;
      width: 24px;
      height: 24px;
      cursor: pointer;
    }
    .main {
      flex: 1;
      display: flex;
      flex-direction: column;
      min-width: 0;
      background: #ffffff;
    }
    .messages {
      flex: 1;
      overflow-y: auto;
      padding: 18px 22px;
      background: #ffffff;
    }
    .msg-row {
      margin-bottom: 10px;
      display: flex;
    }
    .msg-row.user { justify-content: flex-end; }
    .msg-bubble {
      max-width: 88%;
      padding: 10px 12px;
      border-radius: 12px;
      line-height: 1.5;
      font-size: 14px;
      white-space: pre-wrap;
      word-break: break-word;
    }
    .msg-row.user .msg-bubble {
      background: #111827;
      color: #fff;
    }
    .msg-row.assistant .msg-bubble {
      background: #f3f4f6;
      color: #111827;
    }
    .msg-row.assistant .msg-bubble.answer-basis {
      background: #eef6ff;
      border: 1px solid #bfdbfe;
      color: #1e3a8a;
      max-width: 620px;
    }
    .msg-row.assistant .msg-bubble.answer-basis .msg-title {
      color: #1d4ed8;
    }
    .msg-title {
      font-size: 12px;
      color: #6b7280;
      margin-bottom: 4px;
      font-weight: 600;
    }
    .input-wrap {
      border-top: 1px solid #e5e7eb;
      padding: 12px;
      background: #fff;
    }
    .input-row {
      display: flex;
      gap: 8px;
      align-items: flex-end;
    }
    .chat-input {
      flex: 1;
      min-height: 44px;
      max-height: 180px;
      resize: vertical;
      border: 1px solid #d1d5db;
      border-radius: 10px;
      padding: 10px 12px;
      font-size: 14px;
      line-height: 1.4;
      outline: none;
    }
    .action-btn {
      border: none;
      border-radius: 50%;
      width: 38px;
      height: 38px;
      font-size: 18px;
      cursor: pointer;
      background: #111827;
      color: #fff;
      display: flex;
      align-items: center;
      justify-content: center;
      padding: 0;
    }
    .action-btn.stop {
      background: #ef4444;
      font-size: 16px;
    }
    .confirm-modal {
      position: fixed;
      inset: 0;
      background: rgba(0, 0, 0, 0.35);
      display: none;
      align-items: center;
      justify-content: center;
      z-index: 1000;
    }
    .confirm-modal.open { display: flex; }
    .confirm-panel {
      width: 560px;
      max-width: calc(100vw - 32px);
      background: #fff;
      border-radius: 22px;
      padding: 30px 36px;
      box-shadow: 0 24px 40px rgba(0, 0, 0, 0.18);
    }
    .confirm-title {
      margin: 0 0 14px 0;
      font-size: 38px;
      line-height: 1.05;
      letter-spacing: -1px;
      font-weight: 700;
      color: #111827;
    }
    .confirm-desc {
      margin: 0;
      color: #374151;
      font-size: 20px;
      line-height: 1.45;
    }
    .confirm-actions {
      margin-top: 28px;
      display: flex;
      justify-content: flex-end;
      gap: 10px;
    }
    .confirm-btn {
      border: 1px solid #d1d5db;
      border-radius: 999px;
      background: #fff;
      color: #374151;
      padding: 10px 26px;
      font-size: 20px;
      cursor: pointer;
    }
    .confirm-btn:hover { background: #f3f4f6; }
    .confirm-btn.danger {
      border-color: #ef4444;
      color: #ef4444;
      background: #fff;
    }
    .confirm-btn.danger:hover {
      background: #fef2f2;
    }
  </style>
</head>
<body>
  <div class="app">
    <aside class="sidebar">
      <button class="top-btn" id="newChatBtn">+ New Chat</button>
      <button class="top-btn" id="docsBtn">Documents</button>
      <div class="sidebar-title">Recent</div>
      <div class="chat-list" id="chatList"></div>
      <div class="sidebar-footer">
        <div class="user-name" id="currentUser">User: -</div>
        <button class="top-btn" id="logoutBtn">Logout</button>
      </div>
    </aside>

    <main class="main">
      <div class="messages" id="messages"></div>
      <div class="input-wrap">
        <div class="input-row">
          <textarea id="chatInput" class="chat-input" placeholder="Type your message..."></textarea>
          <button id="actionBtn" class="action-btn" title="Send">↑</button>
        </div>
      </div>
    </main>
  </div>

  <div id="deleteModal" class="confirm-modal">
    <div class="confirm-panel">
      <h3 class="confirm-title">Delete Conversation</h3>
      <p class="confirm-desc">This conversation cannot be recovered after deletion. Are you sure?</p>
      <div class="confirm-actions">
        <button id="deleteCancelBtn" class="confirm-btn">Cancel</button>
        <button id="deleteConfirmBtn" class="confirm-btn danger">Delete</button>
      </div>
    </div>
  </div>

  <script>
    const state = {
      conversations: [],
      selected_chat_id: null,
      history: [],
      current_user: "",
      sending: false,
      streamController: null,
      renameChatId: null,
      pendingDeleteChatId: null
    };

    const el = {
      chatList: document.getElementById("chatList"),
      messages: document.getElementById("messages"),
      chatInput: document.getElementById("chatInput"),
      actionBtn: document.getElementById("actionBtn"),
      newChatBtn: document.getElementById("newChatBtn"),
      docsBtn: document.getElementById("docsBtn"),
      currentUser: document.getElementById("currentUser"),
      logoutBtn: document.getElementById("logoutBtn"),
      deleteModal: document.getElementById("deleteModal"),
      deleteCancelBtn: document.getElementById("deleteCancelBtn"),
      deleteConfirmBtn: document.getElementById("deleteConfirmBtn")
    };

    async function apiJson(url, options = {}) {
      const res = await fetch(url, options);
      if (res.status === 401) {
        window.location.href = "/auth";
        throw new Error("Unauthorized");
      }

      const contentType = (res.headers.get("content-type") || "").toLowerCase();
      const isJson = contentType.includes("application/json");
      const payload = isJson ? await res.json() : await res.text();

      if (!res.ok) {
        if (typeof payload === "object" && payload) {
          throw new Error(payload.message || `Request failed (${res.status})`);
        }
        const text = String(payload || "").trim();
        throw new Error(text ? `Request failed (${res.status}): ${text.slice(0, 180)}` : `Request failed (${res.status})`);
      }

      return payload;
    }

    function setSending(isSending) {
      state.sending = isSending;
      updateNewChatAvailability();
      if (isSending) {
        el.actionBtn.classList.add("stop");
        el.actionBtn.textContent = "■";
        el.actionBtn.title = "Stop";
      } else {
        el.actionBtn.classList.remove("stop");
        el.actionBtn.textContent = "↑";
        el.actionBtn.title = "Send";
      }
    }

    function selectedChatIsEmpty() {
      return !state.history || state.history.length === 0;
    }

    function updateNewChatAvailability() {
      const blockedByEmptyChat = selectedChatIsEmpty();
      el.newChatBtn.disabled = state.sending || blockedByEmptyChat;
      if (state.sending) {
        el.newChatBtn.title = "";
      } else if (blockedByEmptyChat) {
        el.newChatBtn.title = "请先在当前新会话中发送第一条消息，或切换到已有内容的会话。";
      } else {
        el.newChatBtn.title = "";
      }
    }

    function applyServerState(serverState) {
      state.conversations = serverState.conversations || [];
      state.selected_chat_id = serverState.selected_chat_id || null;
      state.history = serverState.history || [];
      state.current_user = serverState.current_user || "";
      el.currentUser.textContent = "User: " + (state.current_user || "-");
      updateNewChatAvailability();
      renderConversations();
      renderMessages();
    }

    function closeMenus() {
      document.querySelectorAll(".chat-menu.open").forEach((m) => m.classList.remove("open"));
    }

    function openDeleteModal(chatId) {
      state.pendingDeleteChatId = chatId;
      el.deleteModal.classList.add("open");
    }

    function closeDeleteModal() {
      state.pendingDeleteChatId = null;
      el.deleteModal.classList.remove("open");
    }

    function renderConversations() {
      el.chatList.innerHTML = "";
      state.conversations.forEach((chat) => {
        const row = document.createElement("div");
        row.className = "chat-item" + (chat.id === state.selected_chat_id ? " active" : "");
        row.dataset.id = chat.id;

        if (state.renameChatId === chat.id) {
          const renameWrap = document.createElement("div");
          renameWrap.className = "rename-inline";

          const input = document.createElement("input");
          input.value = chat.title;
          renameWrap.appendChild(input);

          const ok = document.createElement("button");
          ok.textContent = "✓";
          ok.onclick = async (e) => {
            e.stopPropagation();
            const nextTitle = input.value.trim();
            if (!nextTitle) return;
            await apiJson(`/api/chats/${encodeURIComponent(chat.id)}/rename`, {
              method: "POST",
              headers: {"Content-Type":"application/json"},
              body: JSON.stringify({title: nextTitle})
            }).then(applyServerState);
            state.renameChatId = null;
            renderConversations();
          };
          renameWrap.appendChild(ok);

          const cancel = document.createElement("button");
          cancel.textContent = "✕";
          cancel.onclick = (e) => {
            e.stopPropagation();
            state.renameChatId = null;
            renderConversations();
          };
          renameWrap.appendChild(cancel);

          row.appendChild(renameWrap);
        } else {
          const title = document.createElement("div");
          title.className = "chat-title";
          title.textContent = chat.title;
          title.onclick = () => selectChat(chat.id);
          row.appendChild(title);
        }

        if (chat.is_pinned) {
          const pin = document.createElement("div");
          pin.className = "chat-pin";
          pin.textContent = "📌";
          row.appendChild(pin);
        }

        if (state.renameChatId !== chat.id) {
          const menuBtn = document.createElement("button");
          menuBtn.className = "chat-menu-btn";
          menuBtn.textContent = "⋯";
          row.appendChild(menuBtn);

          const menu = document.createElement("div");
          menu.className = "chat-menu";
          menuBtn.onclick = (e) => {
            e.stopPropagation();
            closeMenus();
            menu.classList.add("open");
          };

          const renameBtn = document.createElement("button");
          renameBtn.textContent = "Rename";
          renameBtn.onclick = (e) => {
            e.stopPropagation();
            closeMenus();
            state.renameChatId = chat.id;
            renderConversations();
          };
          menu.appendChild(renameBtn);

          const pinBtn = document.createElement("button");
          pinBtn.textContent = chat.is_pinned ? "Unpin" : "Top";
          pinBtn.onclick = async (e) => {
            e.stopPropagation();
            closeMenus();
            await apiJson(`/api/chats/${encodeURIComponent(chat.id)}/pin-toggle`, {
              method: "POST"
            }).then(applyServerState);
          };
          menu.appendChild(pinBtn);

          const deleteBtn = document.createElement("button");
          deleteBtn.className = "danger";
          deleteBtn.textContent = "Delete";
          deleteBtn.onclick = async (e) => {
            e.stopPropagation();
            closeMenus();
            openDeleteModal(chat.id);
          };
          menu.appendChild(deleteBtn);

          row.appendChild(menu);
        }

        el.chatList.appendChild(row);
      });
    }

    function renderMessages() {
      el.messages.innerHTML = "";
      (state.history || []).forEach((msg) => {
        const role = msg.role === "user" ? "user" : "assistant";
        const row = document.createElement("div");
        row.className = `msg-row ${role}`;

        const bubble = document.createElement("div");
        bubble.className = "msg-bubble";
        if (msg.metadata && msg.metadata.node === "answer_basis") {
          bubble.classList.add("answer-basis");
        }

        if (msg.metadata && msg.metadata.title) {
          const title = document.createElement("div");
          title.className = "msg-title";
          title.textContent = msg.metadata.title;
          bubble.appendChild(title);
        }

        const content = document.createElement("div");
        content.textContent = msg.content || "";
        bubble.appendChild(content);

        row.appendChild(bubble);
        el.messages.appendChild(row);
      });
      el.messages.scrollTop = el.messages.scrollHeight;
    }

    async function selectChat(chatId) {
      await apiJson(`/api/chats/${encodeURIComponent(chatId)}/select`, {method: "POST"})
        .then(applyServerState);
    }

    async function sendMessage() {
      if (state.sending) return;
      const message = (el.chatInput.value || "").trim();
      if (!message || !state.selected_chat_id) return;

      const previousHistory = Array.isArray(state.history) ? [...state.history] : [];
      setSending(true);
      el.chatInput.value = "";
      state.history = [...previousHistory, {role: "user", content: message}];
      updateNewChatAvailability();
      renderMessages();

      state.streamController = new AbortController();

      try {
        const res = await fetch(`/api/chats/${encodeURIComponent(state.selected_chat_id)}/messages/stream`, {
          method: "POST",
          headers: {"Content-Type":"application/json"},
          body: JSON.stringify({message}),
          signal: state.streamController.signal
        });
        if (res.status === 401) {
          window.location.href = "/auth";
          return;
        }
        if (!res.ok) {
          throw new Error("Failed to send message");
        }

        const reader = res.body.getReader();
        const decoder = new TextDecoder();
        let buffer = "";

        while (true) {
          const {value, done} = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, {stream: true});
          const lines = buffer.split("\\n");
          buffer = lines.pop() || "";

          for (const line of lines) {
            if (!line.trim()) continue;
            const payload = JSON.parse(line);
            if (payload.state) {
              applyServerState(payload.state);
            }
          }
        }
      } catch (e) {
        if (e.name !== "AbortError") {
          console.error(e);
        }
        state.history = previousHistory;
        updateNewChatAvailability();
        renderMessages();
      } finally {
        state.streamController = null;
        setSending(false);
      }
    }

    async function stopMessage() {
      if (state.streamController) {
        state.streamController.abort();
      }
      await apiJson("/api/chats/stop", {method: "POST"});
      setSending(false);
    }

    async function bootstrap() {
      await apiJson("/api/state").then(applyServerState);
    }

    el.newChatBtn.addEventListener("click", async () => {
      try {
        await apiJson("/api/chats", {method: "POST"}).then(applyServerState);
      } catch (e) {
        if (e && e.message) {
          alert(e.message);
        }
      }
    });

    el.docsBtn.addEventListener("click", () => {
      window.location.href = "/documents";
    });
    el.logoutBtn.addEventListener("click", async () => {
      await apiJson("/api/auth/logout", {method: "POST"});
      window.location.href = "/auth";
    });

    el.actionBtn.addEventListener("click", () => {
      if (state.sending) {
        stopMessage();
      } else {
        sendMessage();
      }
    });

    el.chatInput.addEventListener("keydown", (e) => {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        if (!state.sending) sendMessage();
      }
    });

    el.deleteCancelBtn.addEventListener("click", closeDeleteModal);
    el.deleteConfirmBtn.addEventListener("click", async () => {
      if (!state.pendingDeleteChatId) return;
      await apiJson(`/api/chats/${encodeURIComponent(state.pendingDeleteChatId)}`, {
        method: "DELETE"
      }).then(applyServerState);
      closeDeleteModal();
    });
    el.deleteModal.addEventListener("click", (e) => {
      if (e.target === el.deleteModal) closeDeleteModal();
    });

    document.addEventListener("click", closeMenus);
    bootstrap();
  </script>
</body>
</html>
"""


DOCS_HTML = """
<!doctype html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Documents</title>
  <style>
    body {
      margin: 0;
      font-family: "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif;
      background: #f7f7f8;
      color: #111827;
    }
    .wrap {
      max-width: 760px;
      margin: 28px auto;
      padding: 0 16px;
    }
    .card {
      background: #ffffff;
      border: 1px solid #e5e7eb;
      border-radius: 14px;
      padding: 18px;
    }
    .section {
      border: 1px solid #e5e7eb;
      border-radius: 12px;
      padding: 14px;
      margin-bottom: 12px;
      background: #fafafa;
    }
    .section h3 {
      margin: 0 0 10px 0;
      font-size: 18px;
      color: #111827;
    }
    .row {
      display: flex;
      gap: 10px;
      align-items: center;
      margin-bottom: 10px;
      flex-wrap: wrap;
    }
    .btn {
      border: 1px solid #d1d5db;
      border-radius: 10px;
      background: #fff;
      padding: 10px 12px;
      cursor: pointer;
      font-size: 14px;
    }
    .btn:hover { background: #f3f4f6; }
    .btn.primary {
      background: #111827;
      color: #ffffff;
      border-color: #111827;
    }
    .btn.primary:hover {
      background: #1f2937;
    }
    .btn.danger {
      color: #dc2626;
      border-color: #fca5a5;
    }
    .upload-head {
      display: flex;
      align-items: center;
      gap: 8px;
      margin-bottom: 8px;
    }
    .upload-icon {
      width: 28px;
      height: 28px;
      border-radius: 8px;
      background: #eef2ff;
      color: #1d4ed8;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      font-size: 16px;
    }
    #selectedFiles {
      color: #374151;
      font-size: 13px;
      margin-top: 6px;
      word-break: break-word;
    }
    .hint {
      margin: 6px 0 0 0;
      color: #6b7280;
      font-size: 12px;
    }
    .parser-hint {
      margin: 8px 0 0 0;
      color: #374151;
      font-size: 12px;
    }
    .option-box {
      margin-top: 10px;
      border: 1px solid #e5e7eb;
      border-radius: 12px;
      background: #fafafa;
      padding: 10px 12px;
    }
    .option-label {
      display: flex;
      align-items: flex-start;
      gap: 10px;
      cursor: pointer;
      color: #111827;
      font-size: 14px;
    }
    .option-label input {
      margin-top: 3px;
    }
    .option-title {
      font-weight: 600;
    }
    .option-desc {
      margin-top: 4px;
      color: #6b7280;
      font-size: 12px;
      line-height: 1.5;
    }
    .progress-wrap {
      display: none;
      margin-top: 10px;
    }
    .progress-wrap.open {
      display: block;
    }
    .progress-bar {
      width: 100%;
      height: 10px;
      border-radius: 999px;
      background: #e5e7eb;
      overflow: hidden;
    }
    .progress-fill {
      width: 0%;
      height: 100%;
      background: #111827;
      transition: width 0.15s ease;
    }
    .progress-text {
      margin-top: 6px;
      color: #6b7280;
      font-size: 12px;
    }
    #docList {
      border: 1px solid #e5e7eb;
      border-radius: 10px;
      padding: 10px;
      min-height: 90px;
      background: #fafafa;
      margin-top: 10px;
      margin-bottom: 10px;
      font-size: 14px;
      white-space: pre-wrap;
    }
    #status {
      color: #6b7280;
      font-size: 13px;
      min-height: 18px;
      margin-top: 6px;
    }
    .confirm-modal {
      position: fixed;
      inset: 0;
      background: rgba(0, 0, 0, 0.35);
      display: none;
      align-items: center;
      justify-content: center;
      z-index: 1000;
    }
    .confirm-modal.open { display: flex; }
    .confirm-panel {
      width: 560px;
      max-width: calc(100vw - 32px);
      background: #fff;
      border-radius: 22px;
      padding: 30px 36px;
      box-shadow: 0 24px 40px rgba(0, 0, 0, 0.18);
    }
    .confirm-title {
      margin: 0 0 14px 0;
      font-size: 38px;
      line-height: 1.05;
      letter-spacing: -1px;
      font-weight: 700;
      color: #111827;
    }
    .confirm-desc {
      margin: 0;
      color: #374151;
      font-size: 20px;
      line-height: 1.45;
    }
    .confirm-actions {
      margin-top: 28px;
      display: flex;
      justify-content: flex-end;
      gap: 10px;
    }
    .confirm-btn {
      border: 1px solid #d1d5db;
      border-radius: 999px;
      background: #fff;
      color: #374151;
      padding: 10px 26px;
      font-size: 20px;
      cursor: pointer;
    }
    .confirm-btn:hover { background: #f3f4f6; }
    .confirm-btn.danger {
      border-color: #ef4444;
      color: #ef4444;
      background: #fff;
    }
    .confirm-btn.danger:hover {
      background: #fef2f2;
    }
  </style>
</head>
<body>
  <div class="wrap">
    <div class="card">
      <div class="row">
        <button class="btn" id="backBtn">← Back To Chat</button>
      </div>
      <h2 style="margin: 0 0 12px 0;">Documents</h2>

      <div class="section">
        <div class="upload-head">
          <span class="upload-icon">⇪</span>
          <h3 style="margin: 0;">Upload Files</h3>
        </div>
        <div class="row">
          <input id="docFiles" type="file" multiple accept=".pdf,.md" style="display:none;" />
          <button class="btn" id="pickBtn">Select Files</button>
          <button class="btn" id="clearSelectedBtn">Clear Selected Files</button>
          <button class="btn primary" id="uploadBtn">Add Documents</button>
        </div>
        <div id="selectedFiles">No files selected.</div>
        <p id="parserHint" class="parser-hint">Current PDF parser: -</p>
        <div class="option-box">
          <div class="option-title">Upload behavior</div>
          <div class="option-desc">
            After you click Add Documents, the system will ask whether these files are supplemental material for the current topic or the start of a new topic.
            This choice controls whether all chat retrieval threads are refreshed immediately.
          </div>
        </div>
        <div id="uploadProgressWrap" class="progress-wrap">
          <div class="progress-bar">
            <div id="uploadProgressFill" class="progress-fill"></div>
          </div>
          <div id="uploadProgressText" class="progress-text">Uploading: 0%</div>
        </div>
        <p class="hint">Supported file types: PDF (.pdf), Markdown (.md)</p>
      </div>

      <div class="section">
        <h3>File Management</h3>
        <div class="row">
          <input
            id="docSearch"
            type="text"
            placeholder="Search document to delete..."
            style="min-width:280px; height:36px; padding: 0 10px; border:1px solid #d1d5db; border-radius:10px;"
          />
        </div>
        <div class="row">
          <select id="docSelect" style="min-width:280px; height:36px;"></select>
          <button class="btn" id="deleteBtn">Delete Selected Document</button>
          <button class="btn danger" id="clearBtn">Clear All Documents</button>
        </div>
        <div id="docList"></div>
      </div>
      <div id="status"></div>
    </div>
  </div>

  <div id="confirmModal" class="confirm-modal">
    <div class="confirm-panel">
      <h3 id="confirmTitle" class="confirm-title">Confirm Action</h3>
      <p id="confirmDesc" class="confirm-desc">Please confirm this action.</p>
      <div class="confirm-actions">
        <button id="confirmCancelBtn" class="confirm-btn">Cancel</button>
        <button id="confirmOkBtn" class="confirm-btn danger">Confirm</button>
      </div>
    </div>
  </div>

  <div id="uploadModeModal" class="confirm-modal">
    <div class="confirm-panel">
      <h3 class="confirm-title">Upload Intent</h3>
      <p class="confirm-desc">
        Are these files supplemental material for the current topic, or do they start a new topic / mostly replace the current document library?
      </p>
      <div class="confirm-actions">
        <button id="uploadModeCancelBtn" class="confirm-btn">Cancel</button>
        <button id="uploadModeSupplementBtn" class="confirm-btn">Supplement Current Topic</button>
        <button id="uploadModeNewTopicBtn" class="confirm-btn danger">Start New Topic</button>
      </div>
    </div>
  </div>

  <script>
    const el = {
      backBtn: document.getElementById("backBtn"),
      docFiles: document.getElementById("docFiles"),
      pickBtn: document.getElementById("pickBtn"),
      clearSelectedBtn: document.getElementById("clearSelectedBtn"),
      uploadBtn: document.getElementById("uploadBtn"),
      docSearch: document.getElementById("docSearch"),
      docSelect: document.getElementById("docSelect"),
      deleteBtn: document.getElementById("deleteBtn"),
      clearBtn: document.getElementById("clearBtn"),
      docList: document.getElementById("docList"),
      selectedFiles: document.getElementById("selectedFiles"),
      parserHint: document.getElementById("parserHint"),
      uploadProgressWrap: document.getElementById("uploadProgressWrap"),
      uploadProgressFill: document.getElementById("uploadProgressFill"),
      uploadProgressText: document.getElementById("uploadProgressText"),
      status: document.getElementById("status"),
      confirmModal: document.getElementById("confirmModal"),
      confirmTitle: document.getElementById("confirmTitle"),
      confirmDesc: document.getElementById("confirmDesc"),
      confirmCancelBtn: document.getElementById("confirmCancelBtn"),
      confirmOkBtn: document.getElementById("confirmOkBtn"),
      uploadModeModal: document.getElementById("uploadModeModal"),
      uploadModeCancelBtn: document.getElementById("uploadModeCancelBtn"),
      uploadModeSupplementBtn: document.getElementById("uploadModeSupplementBtn"),
      uploadModeNewTopicBtn: document.getElementById("uploadModeNewTopicBtn"),
    };
    let allDocs = [];
    let confirmAction = null;

    async function apiJson(url, options = {}) {
      const res = await fetch(url, options);
      if (res.status === 401) {
        window.location.href = "/auth";
        throw new Error("Unauthorized");
      }

      const contentType = (res.headers.get("content-type") || "").toLowerCase();
      const isJson = contentType.includes("application/json");
      const payload = isJson ? await res.json() : await res.text();

      if (!res.ok) {
        if (typeof payload === "object" && payload) {
          throw new Error(payload.message || `Request failed (${res.status})`);
        }
        const text = String(payload || "").trim();
        throw new Error(text ? `Request failed (${res.status}): ${text.slice(0, 180)}` : `Request failed (${res.status})`);
      }

      return payload;
    }

    function renderSelectedFiles() {
      const files = el.docFiles.files;
      if (!files || !files.length) {
        el.selectedFiles.textContent = "No files selected.";
        return;
      }
      el.selectedFiles.textContent = Array.from(files).map((f) => f.name).join(", ");
    }

    function renderDocs(docs) {
      allDocs = docs || [];
      const keyword = (el.docSearch.value || "").trim().toLowerCase();
      const list = keyword ? allDocs.filter((d) => d.toLowerCase().includes(keyword)) : allDocs;
      el.docList.textContent = list.length ? list.join("\\n") : (allDocs.length ? "No matching documents" : "No documents");
      el.docSelect.innerHTML = "";
      if (!list.length) {
        const opt = document.createElement("option");
        opt.value = "";
        opt.textContent = allDocs.length ? "No matching documents" : "No documents";
        el.docSelect.appendChild(opt);
        return;
      }
      list.forEach((d) => {
        const opt = document.createElement("option");
        opt.value = d;
        opt.textContent = d;
        el.docSelect.appendChild(opt);
      });
    }

    async function refreshDocs() {
      await apiJson("/api/documents").then((data) => renderDocs(data.documents));
    }

    async function refreshParserHint() {
      const data = await apiJson("/api/documents/parser");
      el.parserHint.textContent = `Current PDF parser: ${data.parser || "-"}`;
    }

    function setUploadProgress(percent, text) {
      el.uploadProgressWrap.classList.add("open");
      el.uploadProgressFill.style.width = `${percent}%`;
      el.uploadProgressText.textContent = text;
    }

    function setUploadUiState(text, percent) {
      el.status.textContent = text;
      setUploadProgress(percent, text);
    }

    function resetUploadProgress() {
      el.uploadProgressWrap.classList.remove("open");
      el.uploadProgressFill.style.width = "0%";
      el.uploadProgressText.textContent = "Uploading: 0%";
    }

    function uploadWithProgress(url, formData) {
      return new Promise((resolve, reject) => {
        const xhr = new XMLHttpRequest();
        xhr.open("POST", url, true);
        xhr.responseType = "text";

        xhr.upload.onprogress = (event) => {
          if (!event.lengthComputable) return;
          const percent = Math.min(100, Math.round((event.loaded / event.total) * 100));
          if (percent >= 100) {
            setUploadUiState("Upload complete. Waiting for server response...", 100);
          } else {
            setUploadUiState(`Uploading: ${percent}%`, percent);
          }
        };

        xhr.onerror = () => reject(new Error("Network error during upload."));

        xhr.onload = () => {
          if (xhr.status === 401) {
            window.location.href = "/auth";
            reject(new Error("Unauthorized"));
            return;
          }

          const contentType = (xhr.getResponseHeader("content-type") || "").toLowerCase();
          const isJson = contentType.includes("application/json");
          const payload = isJson ? JSON.parse(xhr.responseText || "{}") : (xhr.responseText || "");

          if (xhr.status < 200 || xhr.status >= 300) {
            if (typeof payload === "object" && payload) {
              reject(new Error(payload.message || `Request failed (${xhr.status})`));
              return;
            }
            const text = String(payload).trim();
            reject(new Error(text ? `Request failed (${xhr.status}): ${text.slice(0, 180)}` : `Request failed (${xhr.status})`));
            return;
          }

          resolve(payload);
        };

        xhr.send(formData);
      });
    }

    function openConfirmModal(title, desc, actionText, action) {
      el.confirmTitle.textContent = title;
      el.confirmDesc.textContent = desc;
      el.confirmOkBtn.textContent = actionText;
      confirmAction = action;
      el.confirmModal.classList.add("open");
    }

    function closeConfirmModal() {
      el.confirmModal.classList.remove("open");
      confirmAction = null;
    }

    function openUploadModeModal() {
      const files = el.docFiles.files;
      if (!files || !files.length) {
        el.status.textContent = "Please select files first.";
        return;
      }
      el.uploadModeModal.classList.add("open");
    }

    function closeUploadModeModal() {
      el.uploadModeModal.classList.remove("open");
    }

    async function uploadDocs(resetThreadsAfterUpload) {
      const files = el.docFiles.files;
      if (!files || !files.length) {
        el.status.textContent = "Please select files first.";
        return;
      }
      el.uploadBtn.disabled = true;
      const selectedFiles = Array.from(files);
      setUploadUiState("Uploading: 0%", 0);
      try {
        let data = null;
        let attempt = 0;
        const maxAttempts = 3;
          while (attempt < maxAttempts) {
            attempt += 1;
            const formData = new FormData();
            selectedFiles.forEach((f) => formData.append("files", f));
            formData.append(
              "reset_threads_after_upload",
              resetThreadsAfterUpload ? "1" : "0"
            );
            try {
              data = await uploadWithProgress("/api/documents/upload", formData);
              break;
            } catch (e) {
            if (attempt >= maxAttempts) throw e;
            setUploadUiState(`Network unstable, retrying upload (${attempt}/${maxAttempts})...`, 0);
            await new Promise((r) => setTimeout(r, 1200 * attempt));
          }
        }

        if (data && data.ok === false) {
          if (data.job_id) {
            el.status.textContent = data.message || "Another upload is processing. Tracking existing job...";
            await pollUploadStatus(data.job_id);
            return;
          }
          el.status.textContent = data.message || "Upload failed.";
          return;
        }
        el.docFiles.value = "";
        renderSelectedFiles();

        if (data.job_id) {
          setUploadUiState(data.message || "Upload complete. Processing document chunks...", 100);
          await pollUploadStatus(data.job_id);
          return;
        }

        renderDocs((data.state || {}).documents || []);
        el.status.textContent = `Added: ${data.added || 0}, Skipped: ${data.skipped || 0}`;
      } catch (e) {
        el.status.textContent = e && e.message ? e.message : "Upload failed.";
      } finally {
        resetUploadProgress();
        el.uploadBtn.disabled = false;
      }
    }

    async function pollUploadStatus(jobId) {
      while (true) {
        let data = null;
        try {
          data = await apiJson(`/api/documents/upload-status/${encodeURIComponent(jobId)}`);
        } catch (e) {
          el.status.textContent = e && e.message ? `${e.message} Retrying status check...` : "Network unstable, retrying status check...";
          await new Promise((r) => setTimeout(r, 1500));
          continue;
        }

        if (data.status === "processing") {
          setUploadUiState(data.message || "Processing...", 100);
          await new Promise((r) => setTimeout(r, 1200));
          continue;
        }

        if (data.state) {
          renderDocs((data.state || {}).documents || []);
        }

        if (data.status === "done") {
          el.status.textContent = `Added: ${data.added || 0}, Skipped: ${data.skipped || 0}`;
        } else {
          el.status.textContent = data.message || "Upload failed.";
        }
        return;
      }
    }

    async function deleteSelected() {
      const name = el.docSelect.value;
      if (!name) return;
      openConfirmModal(
        "Delete Document",
        `Delete ${name}? This action cannot be undone.`,
        "Delete",
        async () => {
          await apiJson(`/api/documents/${encodeURIComponent(name)}`, {method: "DELETE"})
            .then((data) => {
              renderDocs((data.state || {}).documents || []);
              el.status.textContent = data.message || "";
            });
        }
      );
    }

    async function clearAll() {
      openConfirmModal(
        "Clear All Documents",
        "Delete all documents from the knowledge base? This action cannot be undone.",
        "Clear All",
        async () => {
          await apiJson("/api/documents", {method: "DELETE"})
            .then((data) => {
              renderDocs((data.state || {}).documents || []);
              el.status.textContent = "All documents cleared.";
            });
        }
      );
    }

    el.backBtn.addEventListener("click", () => window.location.href = "/");
    el.pickBtn.addEventListener("click", () => el.docFiles.click());
    el.docFiles.addEventListener("change", renderSelectedFiles);
    el.clearSelectedBtn.addEventListener("click", () => {
      el.docFiles.value = "";
      renderSelectedFiles();
      el.status.textContent = "Selected files cleared.";
    });
    el.uploadBtn.addEventListener("click", openUploadModeModal);
    el.docSearch.addEventListener("input", () => renderDocs(allDocs));
    el.deleteBtn.addEventListener("click", deleteSelected);
    el.clearBtn.addEventListener("click", clearAll);
    el.confirmCancelBtn.addEventListener("click", closeConfirmModal);
    el.confirmOkBtn.addEventListener("click", async () => {
      const action = confirmAction;
      closeConfirmModal();
      if (action) {
        try {
          await action();
        } catch (e) {
          el.status.textContent = e && e.message ? e.message : "Action failed.";
        }
      }
    });
    el.confirmModal.addEventListener("click", (event) => {
      if (event.target === el.confirmModal) {
        closeConfirmModal();
      }
    });
    el.uploadModeCancelBtn.addEventListener("click", closeUploadModeModal);
    el.uploadModeSupplementBtn.addEventListener("click", async () => {
      closeUploadModeModal();
      await uploadDocs(false);
    });
    el.uploadModeNewTopicBtn.addEventListener("click", async () => {
      closeUploadModeModal();
      await uploadDocs(true);
    });
    el.uploadModeModal.addEventListener("click", (event) => {
      if (event.target === el.uploadModeModal) {
        closeUploadModeModal();
      }
    });

    refreshDocs();
    refreshParserHint();
    renderSelectedFiles();
    resetUploadProgress();
  </script>
</body>
</html>
"""

