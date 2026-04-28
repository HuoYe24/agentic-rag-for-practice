import hashlib
import json
import secrets
import threading
import time
import uuid
from pathlib import Path
from typing import Dict, Optional, Tuple

import bcrypt

import config


class UserStore:
    def __init__(self, base_dir: str = None):
        root = Path(base_dir) if base_dir else Path(config._BASE_DIR) / "data"
        self.base_dir = root
        self.base_dir.mkdir(parents=True, exist_ok=True)

        self.users_file = self.base_dir / "users.json"
        self.sessions_file = self.base_dir / "sessions.json"
        self.chats_dir = self.base_dir / "chats"
        self.user_data_dir = self.base_dir / "user_data"

        self.chats_dir.mkdir(parents=True, exist_ok=True)
        self.user_data_dir.mkdir(parents=True, exist_ok=True)

        self._lock = threading.Lock()
        self._ensure_files()

    def _ensure_files(self) -> None:
        if not self.users_file.exists():
            self._write_json(self.users_file, {"users": {}})
        if not self.sessions_file.exists():
            self._write_json(self.sessions_file, {"sessions": {}})

    @staticmethod
    def _read_json(path: Path, default: Dict) -> Dict:
        if not path.exists():
            return default
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return default

    @staticmethod
    def _write_json(path: Path, data: Dict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    @staticmethod
    def _build_default_chat_state() -> Dict:
        return {
            "chat_count": 1,
            "documents_version": 0,
            "selected_chat_id": "chat_1",
            "conversations": {
                "order": ["chat_1"],
                "items": {
                    "chat_1": {
                        "title": "新会话",
                        "thread_id": str(uuid.uuid4()),
                        "document_context_version": 0,
                        "history": [],
                        "is_pinned": False,
                        "unpinned_rank": 0,
                    }
                },
            },
        }

    @staticmethod
    def _validate_username(username: str) -> Tuple[bool, str]:
        if not username:
            return False, "Username is required."
        if " " in username:
            return False, "Username cannot contain spaces."
        if len(username) < 3 or len(username) > 32:
            return False, "Username length must be 3-32."
        return True, ""

    @staticmethod
    def _validate_password(password: str) -> Tuple[bool, str]:
        if not password:
            return False, "Password is required."
        if len(password) < 6:
            return False, "Password must be at least 6 characters."
        return True, ""

    @staticmethod
    def _user_id(username: str) -> str:
        return hashlib.sha256(username.encode("utf-8")).hexdigest()[:16]

    def _chat_file(self, username: str) -> Path:
        return self.chats_dir / f"{self._user_id(username)}.json"

    def register_user(self, username: str, password: str) -> Tuple[bool, str]:
        username = (username or "").strip()
        password = password or ""

        ok, msg = self._validate_username(username)
        if not ok:
            return False, msg
        ok, msg = self._validate_password(password)
        if not ok:
            return False, msg

        with self._lock:
            users_data = self._read_json(self.users_file, {"users": {}})
            users = users_data.setdefault("users", {})
            if username in users:
                return False, "Username already exists."

            hashed = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
            users[username] = {
                "password_hash": hashed,
                "user_id": self._user_id(username),
                "created_at": int(time.time()),
            }
            self._write_json(self.users_file, users_data)

            chat_file = self._chat_file(username)
            if not chat_file.exists():
                self._write_json(chat_file, self._build_default_chat_state())

            return True, "Registered successfully."

    def verify_user(self, username: str, password: str) -> bool:
        username = (username or "").strip()
        password = password or ""
        with self._lock:
            users_data = self._read_json(self.users_file, {"users": {}})
            user = users_data.get("users", {}).get(username)
            if not user:
                return False
            stored_hash = user.get("password_hash", "")
            if not stored_hash:
                return False
            try:
                return bcrypt.checkpw(password.encode("utf-8"), stored_hash.encode("utf-8"))
            except Exception:
                return False

    def create_session(self, username: str, ttl_seconds: int) -> str:
        token = secrets.token_urlsafe(32)
        now = int(time.time())
        expires_at = now + ttl_seconds

        with self._lock:
            data = self._read_json(self.sessions_file, {"sessions": {}})
            sessions = data.setdefault("sessions", {})
            sessions = {
                t: s for t, s in sessions.items()
                if int(s.get("expires_at", 0)) > now
            }
            sessions[token] = {"username": username, "expires_at": expires_at}
            data["sessions"] = sessions
            self._write_json(self.sessions_file, data)
        return token

    def get_user_by_session(self, token: Optional[str]) -> Optional[str]:
        if not token:
            return None

        now = int(time.time())
        with self._lock:
            data = self._read_json(self.sessions_file, {"sessions": {}})
            sessions = data.setdefault("sessions", {})
            session = sessions.get(token)
            if not session:
                return None
            if int(session.get("expires_at", 0)) <= now:
                sessions.pop(token, None)
                self._write_json(self.sessions_file, data)
                return None
            return session.get("username")

    def delete_session(self, token: Optional[str]) -> None:
        if not token:
            return
        with self._lock:
            data = self._read_json(self.sessions_file, {"sessions": {}})
            sessions = data.setdefault("sessions", {})
            if token in sessions:
                sessions.pop(token, None)
                self._write_json(self.sessions_file, data)

    def load_chat_state(self, username: str) -> Dict:
        with self._lock:
            chat_file = self._chat_file(username)
            if not chat_file.exists():
                state = self._build_default_chat_state()
                self._write_json(chat_file, state)
                return state
            return self._read_json(chat_file, self._build_default_chat_state())

    def save_chat_state(self, username: str, state: Dict) -> None:
        with self._lock:
            self._write_json(self._chat_file(username), state)

    def get_markdown_dir(self, username: str) -> str:
        path = self.user_data_dir / self._user_id(username) / "markdown_docs"
        path.mkdir(parents=True, exist_ok=True)
        return str(path)

    def get_parent_store_dir(self, username: str) -> str:
        path = self.user_data_dir / self._user_id(username) / "parent_store"
        path.mkdir(parents=True, exist_ok=True)
        return str(path)

    def get_collection_name(self, username: str) -> str:
        return f"{config.CHILD_COLLECTION}_{self._user_id(username)}"
