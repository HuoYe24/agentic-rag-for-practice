from pathlib import Path
import shutil
import re
import json
import config
from utils import pdf_to_markdown, clear_directory_contents

class DocumentManager:

    def __init__(self, rag_system, markdown_dir=None):
        self.rag_system = rag_system
        self.markdown_dir = Path(markdown_dir or config.MARKDOWN_DIR)
        self.markdown_dir.mkdir(parents=True, exist_ok=True)
        self.source_map_path = self.markdown_dir / ".document_sources.json"

    def _load_source_map(self):
        if not self.source_map_path.exists():
            return {}
        try:
            return json.loads(self.source_map_path.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def _save_source_map(self, source_map):
        self.source_map_path.write_text(
            json.dumps(source_map, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _display_name_for_stem(self, document_stem):
        return self._load_source_map().get(document_stem, f"{document_stem}.pdf")
        
    def add_documents(self, document_paths, progress_callback=None):
        if not document_paths:
            return 0, 0
            
        document_paths = [document_paths] if isinstance(document_paths, str) else document_paths
        document_paths = [p for p in document_paths if p and Path(p).suffix.lower() in [".pdf", ".md"]]
        
        if not document_paths:
            return 0, 0
            
        added = 0
        skipped = 0
            
        for i, doc_path in enumerate(document_paths):
            if progress_callback:
                progress_callback((i + 1) / len(document_paths), f"Processing {Path(doc_path).name}")
                
            doc_name = Path(doc_path).stem
            md_path = self.markdown_dir / f"{doc_name}.md"
            
            if md_path.exists():
                skipped += 1
                continue
                
            try:            
                source_name = Path(doc_path).name
                if Path(doc_path).suffix.lower() == ".md":
                    shutil.copy(doc_path, md_path)
                else:
                    pdf_to_markdown(str(doc_path), str(self.markdown_dir))
                parent_chunks, child_chunks = self.rag_system.chunker.create_chunks_single(
                    md_path,
                    source_name=source_name,
                )
                
                if not child_chunks:
                    skipped += 1
                    continue
                
                collection = self.rag_system.vector_db.get_collection(self.rag_system.collection_name)
                collection.add_documents(child_chunks)
                self.rag_system.parent_store.save_many(parent_chunks)
                source_map = self._load_source_map()
                source_map[doc_name] = source_name
                self._save_source_map(source_map)
                
                added += 1
                
            except Exception as e:
                print(f"Error processing {doc_path}: {e}")
                skipped += 1
            
        return added, skipped
    
    def get_markdown_files(self):
        if not self.markdown_dir.exists():
            return []
        return sorted([self._display_name_for_stem(p.stem) for p in self.markdown_dir.glob("*.md")])

    def get_document_preview(self, display_name, max_chars=1600):
        document_stem = Path(display_name).stem
        md_path = self.markdown_dir / f"{document_stem}.md"
        if not md_path.exists():
            return ""
        text = md_path.read_text(encoding="utf-8", errors="ignore")
        text = re.sub(r"\s+", " ", text).strip()
        return text[:max_chars]

    def get_document_previews(self, max_chars_per_doc=1600):
        previews = []
        for display_name in self.get_markdown_files():
            previews.append(
                {
                    "name": display_name,
                    "preview": self.get_document_preview(display_name, max_chars=max_chars_per_doc),
                }
            )
        return previews
    
    def clear_all(self):
        self.markdown_dir.mkdir(parents=True, exist_ok=True)
        clear_directory_contents(self.markdown_dir)

        markdown_left = list(self.markdown_dir.iterdir())
        if markdown_left:
            raise RuntimeError(
                f"Incomplete markdown cleanup: {len(markdown_left)} files still remain."
            )

        self.rag_system.parent_store.clear_store()
        remaining_parents = self.rag_system.parent_store.count_all()
        if remaining_parents > 0:
            raise RuntimeError(
                f"Incomplete parent store cleanup: {remaining_parents} files still remain."
            )

        self.rag_system.vector_db.clear_collection(self.rag_system.collection_name)

    def delete_document(self, display_name):
        """
        Delete a single document and all its indexed artifacts.

        display_name usually comes from UI list (e.g. "DiffCSP.pdf").
        """
        if not display_name:
            return False, "No document selected."

        document_stem = Path(display_name).stem
        source_map = self._load_source_map()
        source_name = source_map.get(document_stem, display_name)
        md_path = self.markdown_dir / f"{document_stem}.md"
        md_exists = md_path.exists()
        parent_store = self.rag_system.parent_store
        vector_db = self.rag_system.vector_db
        collection_name = self.rag_system.collection_name

        parent_paths = parent_store.get_document_paths(document_stem)
        vector_count_before = vector_db.count_documents_by_source(collection_name, source_name)

        if not md_exists and not parent_paths and vector_count_before == 0:
            return False, f"Document not found: {display_name}"

        md_backup = md_path.read_bytes() if md_exists else None
        parent_backups = [(path, path.read_bytes()) for path in parent_paths]
        deleted_parents = 0
        deleted_vectors = 0

        try:
            if md_exists:
                md_path.unlink()

            deleted_parents = parent_store.delete_by_document_stem(document_stem)

            if md_path.exists():
                raise RuntimeError("Markdown file still exists after delete.")

            remaining_parents = parent_store.count_by_document_stem(document_stem)
            if remaining_parents > 0:
                raise RuntimeError(
                    f"Incomplete parent chunk deletion: {remaining_parents} parent chunks still remain."
                )

            deleted_vectors = vector_db.delete_documents_by_source(collection_name, source_name)
            remaining_vectors = vector_db.count_documents_by_source(collection_name, source_name)
            if remaining_vectors > 0:
                raise RuntimeError(
                    f"Incomplete child chunk deletion: {remaining_vectors} child chunks still remain."
                )

            if document_stem in source_map:
                source_map.pop(document_stem, None)
                try:
                    self._save_source_map(source_map)
                except Exception as e:
                    print(f"Warning: Could not update document source map: {e}")

        except Exception as e:
            if md_backup is not None and not md_path.exists():
                md_path.parent.mkdir(parents=True, exist_ok=True)
                md_path.write_bytes(md_backup)

            for file_path, content in parent_backups:
                if not file_path.exists():
                    file_path.parent.mkdir(parents=True, exist_ok=True)
                    file_path.write_bytes(content)

            try:
                self._save_source_map(source_map)
            except Exception as map_error:
                print(f"Warning: Could not restore document source map: {map_error}")

            return False, f"Delete failed for {display_name}: {e}"

        return (
            True,
            f"Deleted {display_name} | parent chunks: {deleted_parents}, child chunks: {deleted_vectors}",
        )
