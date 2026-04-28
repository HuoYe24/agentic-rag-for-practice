import json
import os
import tempfile
import threading
import time
import uuid
from pathlib import Path
from typing import Dict, List

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, StreamingResponse
from pydantic import BaseModel

from core.chat_interface import ChatInterface
from core.document_manager import DocumentManager
from core.rag_system import RAGSystem
from core.user_store import UserStore
from utils import current_pdf_parser_name

TEMP_UPLOAD_DIR = os.path.join(tempfile.gettempdir(), "agentic_rag_uploads")
UPLOAD_CHUNK_SIZE = 1024 * 1024
os.makedirs(TEMP_UPLOAD_DIR, exist_ok=True)


class MessageIn(BaseModel):
    message: str


class RenameIn(BaseModel):
    title: str


class AuthIn(BaseModel):
    username: str
    password: str


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


def create_app() -> FastAPI:
    app = FastAPI()
    user_store = UserStore()
    session_cookie_name = "rag_session"
    session_ttl_seconds = 7 * 24 * 60 * 60

    runtime_lock = threading.Lock()
    runtimes: Dict[str, Dict] = {}

    def get_runtime(username: str) -> Dict:
        with runtime_lock:
            runtime = runtimes.get(username)
            if runtime:
                return runtime
            rag_system = RAGSystem(
                collection_name=user_store.get_collection_name(username),
                parent_store_path=user_store.get_parent_store_dir(username),
            )
            rag_system.initialize()
            doc_manager = DocumentManager(rag_system, markdown_dir=user_store.get_markdown_dir(username))
            chat_interface = ChatInterface(rag_system)
            runtime = {
                "lock": threading.Lock(),
                "rag_system": rag_system,
                "doc_manager": doc_manager,
                "chat_interface": chat_interface,
                "upload_jobs": {},
                "upload_jobs_lock": threading.Lock(),
            }
            runtimes[username] = runtime
            return runtime

    def current_user(request: Request) -> str:
        token = request.cookies.get(session_cookie_name)
        username = user_store.get_user_by_session(token)
        if not username:
            raise HTTPException(status_code=401, detail="Unauthorized")
        return username

    def maybe_user(request: Request) -> str:
        token = request.cookies.get(session_cookie_name)
        return user_store.get_user_by_session(token)

    def parse_chat_number(chat_id: str) -> int:
        try:
            if chat_id.startswith("chat_"):
                return int(chat_id.split("_", 1)[1])
        except Exception:
            pass
        return 0

    def build_chat_item(documents_version: int, *, unpinned_rank: int = 0) -> Dict:
        return {
            "title": "新会话",
            "thread_id": str(uuid.uuid4()),
            "document_context_version": documents_version,
            "history": [],
            "is_pinned": False,
            "unpinned_rank": unpinned_rank,
        }

    def next_unpinned_rank(state: Dict) -> int:
        ranks = []
        for item in state.get("conversations", {}).get("items", {}).values():
            try:
                ranks.append(int(item.get("unpinned_rank", 0)))
            except Exception:
                continue
        return min(ranks) - 1 if ranks else 0

    def rebuild_conversation_order(state: Dict) -> None:
        conversations = state.setdefault("conversations", {})
        items = conversations.setdefault("items", {})
        current_order = [cid for cid in conversations.setdefault("order", []) if cid in items]
        for cid in items:
            if cid not in current_order:
                current_order.append(cid)

        positions = {cid: idx for idx, cid in enumerate(current_order)}

        def sort_key(cid: str):
            item = items[cid]
            try:
                rank = int(item.get("unpinned_rank", positions[cid]))
            except Exception:
                rank = positions[cid]
            return (rank, positions[cid])

        pinned_ids = [cid for cid in current_order if items[cid].get("is_pinned", False)]
        unpinned_ids = sorted(
            [cid for cid in current_order if not items[cid].get("is_pinned", False)],
            key=sort_key,
        )
        conversations["order"] = pinned_ids + unpinned_ids

    def normalize_state(state: Dict) -> Dict:
        def default_state() -> Dict:
            return user_store._build_default_chat_state()

        if not isinstance(state, dict):
            return default_state()

        migrated_documents_version = "documents_version" not in state
        if migrated_documents_version:
            state["documents_version"] = 1
        else:
            try:
                state["documents_version"] = max(int(state.get("documents_version", 0) or 0), 0)
            except Exception:
                state["documents_version"] = 0

        documents_version = state["documents_version"]

        conversations = state.setdefault("conversations", {})
        order = conversations.setdefault("order", [])
        items = conversations.setdefault("items", {})

        order = [cid for cid in order if cid in items]
        for cid in list(items.keys()):
            if cid not in order:
                order.append(cid)

        for idx, cid in enumerate(order):
            item = items[cid]
            item.setdefault("title", cid)
            item.setdefault("history", [])
            item.setdefault("is_pinned", False)
            if not item.get("thread_id"):
                item["thread_id"] = str(uuid.uuid4())
            try:
                item["unpinned_rank"] = int(item.get("unpinned_rank", idx))
            except Exception:
                item["unpinned_rank"] = idx
            if "document_context_version" not in item:
                item["document_context_version"] = 0 if migrated_documents_version else documents_version
            else:
                try:
                    item["document_context_version"] = max(
                        int(item.get("document_context_version", documents_version) or 0),
                        0,
                    )
                except Exception:
                    item["document_context_version"] = 0

        if not order:
            next_count = max(int(state.get("chat_count", 0) or 0), 0) + 1
            chat_id = f"chat_{next_count}"
            items[chat_id] = build_chat_item(documents_version, unpinned_rank=0)
            order = [chat_id]
            state["chat_count"] = next_count

        max_seen = max([parse_chat_number(cid) for cid in order], default=1)
        state["chat_count"] = max(int(state.get("chat_count", 0) or 0), max_seen)
        conversations["order"] = order
        rebuild_conversation_order(state)
        selected = state.get("selected_chat_id")
        if selected not in items:
            state["selected_chat_id"] = conversations["order"][0]
        return state

    def load_state(username: str) -> Dict:
        state = user_store.load_chat_state(username)
        state = normalize_state(state)
        user_store.save_chat_state(username, state)
        return state

    def parse_checkbox_flag(raw_value: str) -> bool:
        return str(raw_value or "").strip().lower() in {"1", "true", "yes", "on"}

    def current_documents_version(state: Dict) -> int:
        try:
            return max(int(state.get("documents_version", 0) or 0), 0)
        except Exception:
            return 0

    def bump_documents_version(state: Dict) -> int:
        new_version = current_documents_version(state) + 1
        state["documents_version"] = new_version
        return new_version

    def assign_fresh_thread(chat: Dict, documents_version: int) -> None:
        chat["thread_id"] = str(uuid.uuid4())
        chat["document_context_version"] = documents_version

    def refresh_chat_thread_if_stale(state: Dict, chat_id: str) -> bool:
        chat = state["conversations"]["items"].get(chat_id)
        if not chat:
            return False

        documents_version = current_documents_version(state)
        try:
            chat_version = int(chat.get("document_context_version", 0) or 0)
        except Exception:
            chat_version = 0

        if chat_version == documents_version:
            return False

        assign_fresh_thread(chat, documents_version)
        return True

    def refresh_all_chat_threads(state: Dict) -> int:
        documents_version = current_documents_version(state)
        refreshed = 0
        for chat in state["conversations"]["items"].values():
            assign_fresh_thread(chat, documents_version)
            refreshed += 1
        return refreshed

    def conversation_summaries(state: Dict) -> List[Dict]:
        items = state["conversations"]["items"]
        return [
            {
                "id": cid,
                "title": items[cid]["title"],
                "is_pinned": items[cid].get("is_pinned", False),
                "is_empty": not bool(items[cid].get("history")),
            }
            for cid in state["conversations"]["order"]
            if cid in items
        ]

    def app_state(username: str, runtime: Dict, state: Dict, sid: str = None) -> Dict:
        items = state["conversations"]["items"]
        order = state["conversations"]["order"]
        current_sid = sid or state.get("selected_chat_id")
        if current_sid not in items and order:
            current_sid = order[0]
        state["selected_chat_id"] = current_sid
        return {
            "documents": runtime["doc_manager"].get_markdown_files(),
            "conversations": conversation_summaries(state),
            "selected_chat_id": current_sid,
            "history": items.get(current_sid, {}).get("history", []),
            "current_user": username,
        }

    def set_upload_job(runtime: Dict, job_id: str, payload: Dict) -> None:
        with runtime["upload_jobs_lock"]:
            runtime["upload_jobs"][job_id] = payload

    def get_upload_job(runtime: Dict, job_id: str) -> Dict:
        with runtime["upload_jobs_lock"]:
            return runtime["upload_jobs"].get(job_id)

    def upload_processing_message(paths: List[str]) -> str:
        if any(Path(p).suffix.lower() == ".pdf" for p in paths):
            return f"Upload complete. Processing PDFs with {current_pdf_parser_name()}..."
        return "Upload complete. Processing uploaded documents..."

    def document_inventory_message(documents: List[str]) -> str:
        if not documents:
            return (
                "当前文档库为空，没有可列出的文档。\n\n"
                "请先进入 Documents 页面上传至少一个 PDF 或 Markdown 文档。"
            )

        lines = [f"当前文档库中共有 {len(documents)} 个文档：", ""]
        lines.extend(f"- {name}" for name in documents)
        return "\n".join(lines)

    def empty_documents_chat_message() -> str:
        return (
            "当前文档库为空，无法执行文档检索。\n\n"
            "请先进入 Documents 页面上传至少一个 PDF 或 Markdown 文档，然后再继续提问。"
        )

    @app.get("/", response_class=HTMLResponse)
    async def index(request: Request):
        if not maybe_user(request):
            return RedirectResponse(url="/auth", status_code=302)
        return CHAT_HTML

    @app.get("/auth", response_class=HTMLResponse)
    async def auth_page(request: Request):
        if maybe_user(request):
            return RedirectResponse(url="/", status_code=302)
        return AUTH_HTML

    @app.get("/documents", response_class=HTMLResponse)
    async def documents_page(request: Request):
        if not maybe_user(request):
            return RedirectResponse(url="/auth", status_code=302)
        return DOCS_HTML

    @app.post("/api/auth/register")
    async def register(body: AuthIn):
        username = body.username.strip()
        password = body.password
        ok, msg = user_store.register_user(username, password)
        if not ok:
            return JSONResponse({"ok": False, "message": msg}, status_code=400)
        return JSONResponse({"ok": True, "message": "Registered successfully."})

    @app.post("/api/auth/login")
    async def login(body: AuthIn):
        username = body.username.strip()
        password = body.password
        if not user_store.verify_user(username, password):
            return JSONResponse({"ok": False, "message": "Invalid username or password."}, status_code=400)
        token = user_store.create_session(username, session_ttl_seconds)
        response = JSONResponse({"ok": True, "message": "Login successful."})
        response.set_cookie(
            key=session_cookie_name,
            value=token,
            max_age=session_ttl_seconds,
            expires=session_ttl_seconds,
            httponly=True,
            samesite="lax",
        )
        return response

    @app.post("/api/auth/logout")
    async def logout(request: Request):
        token = request.cookies.get(session_cookie_name)
        user_store.delete_session(token)
        response = JSONResponse({"ok": True})
        response.delete_cookie(session_cookie_name)
        return response

    @app.get("/api/auth/me")
    async def me(request: Request):
        username = current_user(request)
        return {"ok": True, "username": username}

    @app.get("/api/state")
    async def get_state(request: Request):
        username = current_user(request)
        runtime = get_runtime(username)
        with runtime["lock"]:
            state = load_state(username)
            selected_chat_id = state.get("selected_chat_id")
            items = state["conversations"]["items"]
            order = state["conversations"]["order"]
            if selected_chat_id not in items and order:
                selected_chat_id = order[0]
                state["selected_chat_id"] = selected_chat_id
            if selected_chat_id in items:
                runtime["chat_interface"].set_thread(items[selected_chat_id]["thread_id"])
            return app_state(username, runtime, state)

    @app.post("/api/chats")
    async def create_chat(request: Request):
        username = current_user(request)
        runtime = get_runtime(username)
        with runtime["lock"]:
            state = load_state(username)
            selected_chat_id = state.get("selected_chat_id")
            selected_chat = state["conversations"]["items"].get(selected_chat_id, {})
            if not selected_chat.get("history"):
                return JSONResponse(
                    {
                        "ok": False,
                        "message": "当前已有一个空白新会话，请先在该会话中发送消息，或切换到其他已有内容的会话。",
                        "state": app_state(username, runtime, state, selected_chat_id),
                    },
                    status_code=400,
                )
            state["chat_count"] = int(state.get("chat_count", 0)) + 1
            cid = f"chat_{state['chat_count']}"
            state["conversations"]["items"][cid] = build_chat_item(
                current_documents_version(state),
                unpinned_rank=next_unpinned_rank(state),
            )
            rebuild_conversation_order(state)
            state["selected_chat_id"] = cid
            user_store.save_chat_state(username, state)
            return app_state(username, runtime, state, cid)

    @app.post("/api/chats/{chat_id}/select")
    async def select_chat(chat_id: str, request: Request):
        username = current_user(request)
        runtime = get_runtime(username)
        with runtime["lock"]:
            state = load_state(username)
            if chat_id not in state["conversations"]["items"]:
                raise HTTPException(status_code=404, detail="Chat not found")
            state["selected_chat_id"] = chat_id
            runtime["chat_interface"].set_thread(state["conversations"]["items"][chat_id]["thread_id"])
            user_store.save_chat_state(username, state)
            return app_state(username, runtime, state, chat_id)

    @app.post("/api/chats/{chat_id}/rename")
    async def rename_chat(chat_id: str, body: RenameIn, request: Request):
        username = current_user(request)
        runtime = get_runtime(username)
        with runtime["lock"]:
            state = load_state(username)
            if chat_id not in state["conversations"]["items"]:
                raise HTTPException(status_code=404, detail="Chat not found")
            title = body.title.strip()
            if title:
                state["conversations"]["items"][chat_id]["title"] = title
                user_store.save_chat_state(username, state)
            return app_state(username, runtime, state, chat_id)

    @app.post("/api/chats/{chat_id}/pin-toggle")
    async def pin_toggle(chat_id: str, request: Request):
        username = current_user(request)
        runtime = get_runtime(username)
        with runtime["lock"]:
            state = load_state(username)
            if chat_id not in state["conversations"]["items"]:
                raise HTTPException(status_code=404, detail="Chat not found")
            item = state["conversations"]["items"][chat_id]
            pinned = item.get("is_pinned", False)
            if not pinned:
                state["conversations"]["order"] = [chat_id] + [
                    cid for cid in state["conversations"]["order"] if cid != chat_id
                ]
                item["is_pinned"] = True
            else:
                item["is_pinned"] = False
            rebuild_conversation_order(state)
            user_store.save_chat_state(username, state)
            return app_state(username, runtime, state, chat_id)

    @app.delete("/api/chats/{chat_id}")
    async def delete_chat(chat_id: str, request: Request):
        username = current_user(request)
        runtime = get_runtime(username)
        with runtime["lock"]:
            state = load_state(username)
            items = state["conversations"]["items"]
            order = state["conversations"]["order"]

            if chat_id not in items:
                raise HTTPException(status_code=404, detail="Chat not found")

            del items[chat_id]
            state["conversations"]["order"] = [cid for cid in order if cid != chat_id]

            if not state["conversations"]["order"]:
                state["chat_count"] = int(state.get("chat_count", 0)) + 1
                cid = f"chat_{state['chat_count']}"
                state["conversations"]["items"][cid] = build_chat_item(
                    current_documents_version(state),
                    unpinned_rank=0,
                )
                rebuild_conversation_order(state)
                state["selected_chat_id"] = cid
                runtime["chat_interface"].set_thread(state["conversations"]["items"][cid]["thread_id"])
                user_store.save_chat_state(username, state)
                return app_state(username, runtime, state, cid)

            selected_chat_id = state.get("selected_chat_id")
            if selected_chat_id == chat_id or selected_chat_id not in state["conversations"]["items"]:
                empty_chat_id = next(
                    (cid for cid in state["conversations"]["order"] if not state["conversations"]["items"][cid]["history"]),
                    None,
                )
                if empty_chat_id:
                    state["selected_chat_id"] = empty_chat_id
                else:
                    state["chat_count"] = int(state.get("chat_count", 0)) + 1
                    cid = f"chat_{state['chat_count']}"
                    state["conversations"]["items"][cid] = build_chat_item(
                        current_documents_version(state),
                        unpinned_rank=next_unpinned_rank(state),
                    )
                    rebuild_conversation_order(state)
                    state["selected_chat_id"] = cid
                runtime["chat_interface"].set_thread(
                    state["conversations"]["items"][state["selected_chat_id"]]["thread_id"]
                )

            user_store.save_chat_state(username, state)
            return app_state(username, runtime, state, state["selected_chat_id"])

    @app.post("/api/chats/stop")
    async def stop_chat(request: Request):
        username = current_user(request)
        runtime = get_runtime(username)
        runtime["chat_interface"].request_stop()
        return {"ok": True}

    @app.post("/api/chats/{chat_id}/messages/stream")
    async def stream_chat(chat_id: str, body: MessageIn, request: Request):
        username = current_user(request)
        runtime = get_runtime(username)
        chat_interface = runtime["chat_interface"]
        message = body.message.strip()
        if not message:
            raise HTTPException(status_code=400, detail="Message is empty")

        with runtime["lock"]:
            state = load_state(username)
            items = state["conversations"]["items"]
            if chat_id not in items:
                raise HTTPException(status_code=404, detail="Chat not found")
            state["selected_chat_id"] = chat_id
            thread_refreshed = refresh_chat_thread_if_stale(state, chat_id)
            chat = items[chat_id]
            chat_interface.set_thread(chat["thread_id"])
            previous_history = list(chat["history"])
            reasoning_history = [] if thread_refreshed else list(previous_history)
            current_documents = runtime["doc_manager"].get_markdown_files()
            document_previews = (
                runtime["doc_manager"].get_document_previews()
                if current_documents
                else []
            )
            user_msg = {"role": "user", "content": message}
            if not previous_history and chat["title"] == "新会话":
                chat["title"] = message[:24] + ("..." if len(message) > 24 else "")
            chat["history"] = previous_history + [user_msg]
            user_store.save_chat_state(username, state)
            first_state = app_state(username, runtime, state, chat_id)

        def gen():
            def persist_history(assistant_msgs):
                latest_history = previous_history + [user_msg] + assistant_msgs
                with runtime["lock"]:
                    state = load_state(username)
                    items = state["conversations"]["items"]
                    if chat_id in items:
                        items[chat_id]["history"] = latest_history
                        user_store.save_chat_state(username, state)
                        return app_state(username, runtime, state, chat_id)
                    return app_state(username, runtime, state)

            yield json.dumps({"state": first_state}, ensure_ascii=False) + "\n"

            chat_stream = chat_interface.chat(
                message,
                reasoning_history,
                current_documents,
                document_previews,
            )

            for chunk in chat_stream:
                assistant_msgs = [{"role": "assistant", "content": chunk}] if isinstance(chunk, str) else chunk
                state_payload = persist_history(assistant_msgs)
                yield json.dumps({"state": state_payload}, ensure_ascii=False) + "\n"
            yield json.dumps({"done": True}, ensure_ascii=False) + "\n"

        return StreamingResponse(gen(), media_type="application/x-ndjson")

    @app.get("/api/documents")
    async def documents(request: Request):
        username = current_user(request)
        runtime = get_runtime(username)
        with runtime["lock"]:
            return {"documents": runtime["doc_manager"].get_markdown_files()}

    @app.get("/api/documents/parser")
    async def document_parser(request: Request):
        current_user(request)
        return {"parser": current_pdf_parser_name()}

    @app.post("/api/documents/upload")
    async def upload_documents(
        request: Request,
        files: List[UploadFile] = File(...),
        reset_threads_after_upload: str = Form("0"),
    ):
        username = current_user(request)
        runtime = get_runtime(username)
        reset_threads_after_upload = parse_checkbox_flag(reset_threads_after_upload)
        user_temp_dir = os.path.join(TEMP_UPLOAD_DIR, user_store.get_collection_name(username))
        os.makedirs(user_temp_dir, exist_ok=True)
        temp_paths = []
        rejected_files = []
        with runtime["upload_jobs_lock"]:
            now_ts = int(time.time())
            processing_job_id = None
            for jid, job in runtime["upload_jobs"].items():
                if not job or job.get("status") != "processing":
                    continue
                started_at = int(job.get("started_at", now_ts))
                if now_ts - started_at > 3600:
                    runtime["upload_jobs"][jid] = {
                        "status": "error",
                        "message": "Upload job timed out.",
                        "added": 0,
                        "skipped": 0,
                        "state": job.get("state"),
                        "started_at": started_at,
                    }
                    continue
                processing_job_id = jid
                break
        if processing_job_id:
            return JSONResponse(
                {
                    "ok": False,
                    "message": "Another upload is still processing.",
                    "job_id": processing_job_id,
                },
                status_code=409,
            )

        for f in files:
            suffix = Path(f.filename or "").suffix.lower()
            if suffix not in {".pdf", ".md"}:
                if f.filename:
                    rejected_files.append(Path(f.filename).name)
                continue
            original_name = Path(f.filename or "").name
            if not original_name:
                continue
            target_path = os.path.join(user_temp_dir, original_name)
            try:
                with open(target_path, "wb") as out_file:
                    while True:
                        chunk = await f.read(UPLOAD_CHUNK_SIZE)
                        if not chunk:
                            break
                        out_file.write(chunk)
                temp_paths.append(target_path)
            except Exception as e:
                try:
                    if os.path.exists(target_path):
                        os.remove(target_path)
                except Exception:
                    pass
                return JSONResponse(
                    {
                        "ok": False,
                        "message": f"Failed to save upload `{original_name}`: {e}",
                    },
                    status_code=400,
                )
            finally:
                await f.close()

        if not temp_paths:
            with runtime["lock"]:
                state = load_state(username)
                message = "No supported files were uploaded. Only .pdf and .md are accepted."
                if rejected_files:
                    message = f"{message} Rejected: {', '.join(rejected_files[:5])}"
                return {"ok": False, "message": message, "added": 0, "skipped": 0, "state": app_state(username, runtime, state)}

        job_id = uuid.uuid4().hex
        processing_message = upload_processing_message(temp_paths)
        set_upload_job(
            runtime,
            job_id,
            {
                "status": "processing",
                "message": processing_message,
                "added": 0,
                "skipped": 0,
                "started_at": int(time.time()),
            },
        )

        def worker():
            try:
                with runtime["lock"]:
                    added, skipped = runtime["doc_manager"].add_documents(temp_paths)
                    state = load_state(username)
                    if added > 0:
                        bump_documents_version(state)
                        if reset_threads_after_upload:
                            refresh_all_chat_threads(state)
                        user_store.save_chat_state(username, state)
                    state_payload = app_state(username, runtime, state)
                set_upload_job(
                    runtime,
                    job_id,
                    {
                        "status": "done",
                        "message": "Upload processing completed.",
                        "added": added,
                        "skipped": skipped,
                        "state": state_payload,
                        "started_at": int(time.time()),
                    },
                )
            except Exception as e:
                with runtime["lock"]:
                    state = load_state(username)
                    state_payload = app_state(username, runtime, state)
                set_upload_job(
                    runtime,
                    job_id,
                    {
                        "status": "error",
                        "message": f"Upload processing failed: {e}",
                        "added": 0,
                        "skipped": 0,
                        "state": state_payload,
                        "started_at": int(time.time()),
                    },
                )
            finally:
                for p in temp_paths:
                    try:
                        os.remove(p)
                    except Exception:
                        pass

        threading.Thread(target=worker, daemon=True).start()
        with runtime["lock"]:
            state = load_state(username)
            return {"ok": True, "job_id": job_id, "message": processing_message, "state": app_state(username, runtime, state)}

    @app.get("/api/documents/upload-status/{job_id}")
    async def upload_status(job_id: str, request: Request):
        username = current_user(request)
        runtime = get_runtime(username)
        job = get_upload_job(runtime, job_id)
        if not job:
            return JSONResponse({"status": "error", "message": "Upload job not found."}, status_code=404)
        return job

    @app.delete("/api/documents")
    async def clear_documents(request: Request):
        username = current_user(request)
        runtime = get_runtime(username)
        with runtime["lock"]:
            state = load_state(username)
            try:
                runtime["doc_manager"].clear_all()
                bump_documents_version(state)
                user_store.save_chat_state(username, state)
                return {"ok": True, "message": "All documents cleared.", "state": app_state(username, runtime, state)}
            except Exception as e:
                user_store.save_chat_state(username, state)
                return JSONResponse(
                    {
                        "ok": False,
                        "message": f"Clear all failed: {e}",
                        "state": app_state(username, runtime, state),
                    },
                    status_code=400,
                )

    @app.delete("/api/documents/{doc_name}")
    async def delete_document(doc_name: str, request: Request):
        username = current_user(request)
        runtime = get_runtime(username)
        with runtime["lock"]:
            success, msg = runtime["doc_manager"].delete_document(doc_name)
            state = load_state(username)
            if success:
                bump_documents_version(state)
                user_store.save_chat_state(username, state)
            return {"ok": success, "message": msg, "state": app_state(username, runtime, state)}

    return app
