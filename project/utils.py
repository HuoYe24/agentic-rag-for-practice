import os
import shutil
import config
import pymupdf.layout
import pymupdf4llm
from pathlib import Path
import glob
import tiktoken


def clear_directory_contents(directory: Path) -> None:
    """Delete everything under directory but not the directory itself (safe for Docker volume / bind mount roots)."""
    directory = Path(directory)
    if not directory.is_dir():
        return
    for child in directory.iterdir():
        if child.is_dir():
            shutil.rmtree(child)
        else:
            child.unlink()


os.environ["TOKENIZERS_PARALLELISM"] = "false"

LLAMA_PARSE_DEFAULT_TIMEOUT_SECONDS = 900
LLAMA_PARSE_DEFAULT_LANGUAGES = ["en", "ch_sim"]


def is_llamaparse_enabled():
    return bool(os.environ.get("LLAMA_CLOUD_API_KEY") or os.environ.get("LLAMA_PARSE_API_KEY"))


def current_pdf_parser_name():
    return "LlamaParse" if is_llamaparse_enabled() else "PyMuPDF4LLM"


def _write_markdown_output(markdown_text, source_path, output_dir):
    md_cleaned = markdown_text.encode("utf-8", errors="surrogatepass").decode("utf-8", errors="ignore")
    output_path = Path(output_dir) / Path(source_path).stem
    Path(output_path).with_suffix(".md").write_bytes(md_cleaned.encode("utf-8"))


def _pdf_to_markdown_legacy(pdf_path, output_dir):
    doc = pymupdf.open(pdf_path)
    md = pymupdf4llm.to_markdown(
        doc,
        header=False,
        footer=False,
        page_separators=True,
        ignore_images=True,
        write_images=False,
        image_path=None,
    )
    _write_markdown_output(md, doc.name, output_dir)


def _llamacloud_markdown_to_text(result):
    if getattr(result, "markdown_full", None):
        return result.markdown_full

    markdown = getattr(result, "markdown", None)
    pages = getattr(markdown, "pages", None) if markdown else None
    if not pages:
        return ""

    page_texts = []
    for page in pages:
        if getattr(page, "success", False) and getattr(page, "markdown", None):
            page_texts.append(page.markdown)

    return "\n\n---\n\n".join(page_texts)


def _pdf_to_markdown_with_llamacloud(pdf_path, output_dir):
    try:
        from llama_cloud import LlamaCloud
    except ModuleNotFoundError as e:
        raise RuntimeError("LlamaParse support requires `llama-cloud`. Install dependencies again to enable it.") from e

    client = LlamaCloud()
    result = client.parsing.parse(
        tier="agentic",
        version="latest",
        upload_file=Path(pdf_path),
        expand=["markdown"],
        output_options={
            "markdown": {
                "inline_images": False,
                "tables": {
                    "output_tables_as_markdown": True,
                    "merge_continued_tables": True,
                },
            },
        },
        processing_options={
            "aggressive_table_extraction": True,
            "ignore": {
                "ignore_text_in_image": False,
            },
            "ocr_parameters": {
                "languages": LLAMA_PARSE_DEFAULT_LANGUAGES,
            },
        },
        polling_interval=2.0,
        max_interval=8.0,
        timeout=LLAMA_PARSE_DEFAULT_TIMEOUT_SECONDS,
    )

    markdown_text = _llamacloud_markdown_to_text(result)
    if not markdown_text.strip():
        raise RuntimeError(f"LlamaParse returned empty markdown for {Path(pdf_path).name}.")

    _write_markdown_output(markdown_text, pdf_path, output_dir)


def pdf_to_markdown(pdf_path, output_dir):
    if is_llamaparse_enabled():
        return _pdf_to_markdown_with_llamacloud(pdf_path, output_dir)
    return _pdf_to_markdown_legacy(pdf_path, output_dir)

def pdfs_to_markdowns(path_pattern, overwrite: bool = False):
    output_dir = Path(config.MARKDOWN_DIR)
    output_dir.mkdir(parents=True, exist_ok=True)

    for pdf_path in map(Path, glob.glob(path_pattern)):
        md_path = (output_dir / pdf_path.stem).with_suffix(".md")
        if overwrite or not md_path.exists():
            pdf_to_markdown(pdf_path, output_dir)

def estimate_context_tokens(messages: list) -> int:
    try:
        encoding = tiktoken.encoding_for_model("qwen-max")
    except:
        encoding = tiktoken.get_encoding("cl100k_base")
    return sum(len(encoding.encode(str(msg.content))) for msg in messages if hasattr(msg, 'content') and msg.content)
