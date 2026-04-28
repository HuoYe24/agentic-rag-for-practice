import os
import sys
import logging
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

# ONNX Runtime int32/int64 patch
import numpy as np
import onnxruntime as ort

_original_run = ort.InferenceSession.run


def _patched_run(self, output_names, input_feed, run_options=None):
    patched_feed = {}
    for k, v in input_feed.items():
        if isinstance(v, np.ndarray) and v.dtype == np.int32:
            patched_feed[k] = v.astype(np.int64)
        else:
            patched_feed[k] = v
    return _original_run(self, output_names, patched_feed, run_options)


ort.InferenceSession.run = _patched_run

sys.path.insert(0, os.path.dirname(__file__))

from ui.fastapi_ui import create_app


class _SuppressOtelDetachWarning(logging.Filter):
    def filter(self, record):
        return "Failed to detach context" not in record.getMessage()


logging.getLogger("opentelemetry.context").addFilter(_SuppressOtelDetachWarning())

PROJECT_DIR = os.path.dirname(__file__)


def _env_flag(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


if __name__ == "__main__":
    import uvicorn

    host = os.environ.get("APP_HOST", "127.0.0.1")
    port = int(os.environ.get("APP_PORT", "7860"))
    auto_reload = _env_flag("APP_AUTO_RELOAD", True)

    print("\n🔨 Creating RAG Assistant...")
    print(f"\n🚀 Launching on http://{host}:{port}")

    if auto_reload:
        print("♻️ Auto reload is ON. Save backend code, then refresh the browser.")
        uvicorn.run(
            "app:create_app",
            host=host,
            port=port,
            reload=True,
            reload_dirs=[PROJECT_DIR],
            factory=True,
        )
    else:
        uvicorn.run("app:create_app", host=host, port=port, factory=True)
