import json
import os
import tempfile
import threading
import time
import uuid
import config

from pathlib import Path
from typing import Dict, List

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, StreamingResponse
from pydantic import BaseModel

from core.chat_interface import ChatInterface
from core.document_manager import DocumentManager
from core.rag_system import RAGSystem
from core.user_store import UserStore
from ui.html_templates import AUTH_HTML, CHAT_HTML, DOCS_HTML
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
            max_bytes = config.MAX_UPLOAD_SIZE_MB * 1024 * 1024
            target_path = os.path.join(user_temp_dir, original_name)
            try:
                if f.size is not None and f.size > max_bytes:
                    rejected_files.append(f"{original_name} (exceeds {config.MAX_UPLOAD_SIZE_MB} MB limit)")
                    continue
                total_written = 0
                with open(target_path, "wb") as out_file:
                    while True:
                        chunk = await f.read(UPLOAD_CHUNK_SIZE)
                        if not chunk:
                            break
                        total_written += len(chunk)
                        if total_written > max_bytes:
                            raise MemoryError(
                                f"File exceeds size limit ({config.MAX_UPLOAD_SIZE_MB} MB)"
                            )
                        out_file.write(chunk)
                temp_paths.append(target_path)
            except MemoryError:
                try:
                    if os.path.exists(target_path):
                        os.remove(target_path)
                except Exception:
                    pass
                rejected_files.append(f"{original_name} (exceeds {config.MAX_UPLOAD_SIZE_MB} MB limit)")
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
                return JSONResponse(
                    {"ok": False, "message": message, "added": 0, "skipped": 0, "state": app_state(username, runtime, state)},
                    status_code=413,
                )

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
