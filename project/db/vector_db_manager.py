import threading

import config
from langchain_ollama import OllamaEmbeddings
from langchain_qdrant import QdrantVectorStore, FastEmbedSparse, RetrievalMode
from qdrant_client import QdrantClient
from qdrant_client.http import models as qmodels
import time

class VectorDbManager:
    _shared_lock = threading.Lock()
    _shared_client = None
    _shared_dense_embeddings = None
    _shared_sparse_embeddings = None

    __client: QdrantClient
    __dense_embeddings: OllamaEmbeddings
    __sparse_embeddings: FastEmbedSparse
    
    def __init__(self):
        with VectorDbManager._shared_lock:
            if VectorDbManager._shared_client is None:
                VectorDbManager._shared_client = QdrantClient(path=config.QDRANT_DB_PATH)
                print("✅ Qdrant client initialized (in-memory mode)")

            if VectorDbManager._shared_dense_embeddings is None:
                VectorDbManager._shared_dense_embeddings = OllamaEmbeddings(model=config.DENSE_MODEL)

            if VectorDbManager._shared_sparse_embeddings is None:
                VectorDbManager._shared_sparse_embeddings = FastEmbedSparse(model_name=config.SPARSE_MODEL)
                time.sleep(0.5)

        self.__client = VectorDbManager._shared_client
        self.__dense_embeddings = VectorDbManager._shared_dense_embeddings
        self.__sparse_embeddings = VectorDbManager._shared_sparse_embeddings

    def create_collection(self, collection_name):
            try:
                print(f"📝 Creating collection: {collection_name}...")
                self.__client.create_collection(
                    collection_name=collection_name,
                    vectors_config=qmodels.VectorParams(
                        size=768, 
                        distance=qmodels.Distance.COSINE
                    ),
                    sparse_vectors_config={
                        config.SPARSE_VECTOR_NAME: qmodels.SparseVectorParams()
                    },
                )
                print(f"✅ Collection created: {collection_name}")
            except Exception as e:
                error_str = str(e)
                if "already exists" in error_str.lower():
                    print(f"✅ Collection exists: {collection_name}")
                else:
                    print(f"❌ Error: {e}")
                    raise

    def delete_collection(self, collection_name):
        try:
            self.__client.delete_collection(collection_name)
            print(f"✅ Collection deleted: {collection_name}")
        except Exception as e:
            print(f"⚠️ Could not delete: {e}")

    def collection_exists(self, collection_name: str) -> bool:
        try:
            return bool(self.__client.collection_exists(collection_name))
        except Exception:
            return False

    def get_collection(self, collection_name) -> QdrantVectorStore:
        try:
            return QdrantVectorStore(
                client=self.__client,
                collection_name=collection_name,
                embedding=self.__dense_embeddings,
                sparse_embedding=self.__sparse_embeddings,
                retrieval_mode=RetrievalMode.HYBRID,
                sparse_vector_name=config.SPARSE_VECTOR_NAME
            )
        except Exception as e:
            print(f"❌ Error getting collection: {e}")
            raise

    @staticmethod
    def _extract_source_from_payload(payload) -> str:
        if not isinstance(payload, dict):
            return ""

        metadata = payload.get("metadata")
        if isinstance(metadata, dict):
            source = metadata.get("source")
            if isinstance(source, str):
                return source

        source = payload.get("source")
        return source if isinstance(source, str) else ""

    def _scroll_points(self, collection_name: str, scroll_filter=None, with_payload: bool = False):
        points = []
        next_offset = None

        while True:
            batch, next_offset = self.__client.scroll(
                collection_name=collection_name,
                scroll_filter=scroll_filter,
                with_payload=with_payload,
                with_vectors=False,
                limit=256,
                offset=next_offset,
            )

            if not batch:
                break

            points.extend(batch)

            if next_offset is None:
                break

        return points

    def get_point_ids_by_source(self, collection_name: str, source_name: str) -> list:
        source_filter = qmodels.Filter(
            must=[
                qmodels.FieldCondition(
                    key="metadata.source",
                    match=qmodels.MatchValue(value=source_name),
                )
            ]
        )

        try:
            filtered_points = self._scroll_points(
                collection_name,
                scroll_filter=source_filter,
                with_payload=False,
            )
            point_ids = [p.id for p in filtered_points if p.id is not None]
            if point_ids:
                return point_ids
        except Exception as e:
            print(f"⚠️ Filter lookup failed for source '{source_name}': {e}")

        all_points = self._scroll_points(
            collection_name,
            scroll_filter=None,
            with_payload=True,
        )
        return [
            p.id
            for p in all_points
            if p.id is not None and self._extract_source_from_payload(p.payload) == source_name
        ]

    def count_documents_by_source(self, collection_name: str, source_name: str) -> int:
        return len(self.get_point_ids_by_source(collection_name, source_name))

    def count_points(self, collection_name: str) -> int:
        if not self.collection_exists(collection_name):
            return 0
        points = self._scroll_points(
            collection_name,
            scroll_filter=None,
            with_payload=False,
        )
        return len([p.id for p in points if p.id is not None])

    def clear_collection(self, collection_name: str) -> int:
        if not self.collection_exists(collection_name):
            self.create_collection(collection_name)
            return 0

        all_points = self._scroll_points(
            collection_name,
            scroll_filter=None,
            with_payload=False,
        )
        point_ids = [p.id for p in all_points if p.id is not None]

        if point_ids:
            try:
                self.__client.delete(
                    collection_name=collection_name,
                    points_selector=qmodels.PointIdsList(points=point_ids),
                    wait=True,
                )
            except Exception as e:
                raise RuntimeError(
                    f"Could not clear collection '{collection_name}': {e}"
                ) from e

        remaining_points = self.count_points(collection_name)
        if remaining_points > 0:
            raise RuntimeError(
                f"Incomplete collection clear for '{collection_name}': "
                f"{remaining_points} child chunks still remain."
            )

        return len(point_ids)

    def delete_documents_by_source(self, collection_name: str, source_name: str) -> int:
        """
        Delete all child chunks that belong to a specific source file.

        Source is stored under metadata.source (e.g. "DiffCSP.pdf").
        Returns number of deleted points.
        """
        point_ids = self.get_point_ids_by_source(collection_name, source_name)
        if not point_ids:
            return 0

        try:
            self.__client.delete(
                collection_name=collection_name,
                points_selector=qmodels.PointIdsList(points=point_ids),
                wait=True,
            )
        except Exception as e:
            raise RuntimeError(
                f"Could not delete source '{source_name}' from vector DB: {e}"
            ) from e

        remaining_ids = self.get_point_ids_by_source(collection_name, source_name)
        if remaining_ids:
            raise RuntimeError(
                f"Incomplete vector deletion for '{source_name}': "
                f"{len(remaining_ids)} child chunks still remain."
            )

        return len(point_ids)
