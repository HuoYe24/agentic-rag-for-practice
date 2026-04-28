from typing import List
from langchain_core.tools import tool
from db.parent_store_manager import ParentStoreManager
import config


class ToolFactory:
    
    def __init__(self, collection, parent_store_manager=None, llm=None):
        self.collection = collection
        self.parent_store_manager = parent_store_manager or ParentStoreManager()
        self.llm = llm
        self.reranker = None
        if config.RERANKER_ENABLED:
            from core.reranker import get_reranker
            self.reranker = get_reranker(config.RERANKER_TYPE, llm)
    
    def _search_child_chunks(self, query: str, limit: int) -> str:
        """Search for the top K most relevant child chunks, optionally reranked.
        
        This implements the pipeline:
        1. Initial retrieval: Top-K child chunks from vector search
        2. Reranking (optional): Rerank Top-K → Top-M using reranker
        3. Parent deduplication: Extract unique parent_ids from Top-M
        4. Output: Top-N parent chunks (N <= unique parent count)
        
        Args:
            query: Search query string
            limit: Maximum number of child chunks to retrieve initially (Top-K)
        """
        try:
            initial_k = max(int(limit or 0), config.INITIAL_SEARCH_TOP_K)
            results = self.collection.similarity_search(query, k=initial_k, score_threshold=0.7)
            
            if not results:
                return "NO_RELEVANT_CHUNKS"
            
            child_chunks = [
                {
                    "content": doc.page_content.strip(),
                    "parent_id": doc.metadata.get("parent_id", ""),
                    "source": doc.metadata.get("source", ""),
                    "metadata": doc.metadata,
                    "doc": doc
                }
                for doc in results
            ]
            
            reranked_chunks = child_chunks
            if self.reranker and getattr(self.reranker, "enabled", True):
                ranked_results = self.reranker.rerank(query, child_chunks)
                reranked_chunks = [chunk for chunk, _ in ranked_results]
                reranked_chunks = reranked_chunks[:config.RERANKER_TOP_M]
            
            parent_ids_seen = set()
            selected_chunks = []
            for chunk in reranked_chunks:
                parent_id = chunk.get("parent_id")
                if not parent_id or parent_id not in parent_ids_seen:
                    selected_chunks.append(chunk)
                if parent_id:
                    parent_ids_seen.add(parent_id)
                if len(selected_chunks) >= config.FINAL_OUTPUT_TOP_N:
                    break
            
            output_parts = []
            for i, chunk in enumerate(selected_chunks, 1):
                parent_id = chunk.get("parent_id", "")
                source = chunk.get("source", "")
                content = chunk.get("content", "")
                output_parts.append(
                    f"[Child Chunk {i}]\n"
                    f"Parent ID: {parent_id}\n"
                    f"File Name: {source}\n"
                    f"Content: {content}"
                )
            
            return "\n\n".join(output_parts)

        except Exception as e:
            return f"RETRIEVAL_ERROR: {str(e)}"
    
    def _retrieve_many_parent_chunks(self, parent_ids: List[str]) -> str:
        """Retrieve full parent chunks by their IDs.
    
        Args:
            parent_ids: List of parent chunk IDs to retrieve
        """
        try:
            ids = [parent_ids] if isinstance(parent_ids, str) else list(parent_ids)
            raw_parents = self.parent_store_manager.load_content_many(ids)
            if not raw_parents:
                return "NO_PARENT_DOCUMENTS"

            return "\n\n".join([
                f"Parent ID: {doc.get('parent_id', 'n/a')}\n"
                f"File Name: {doc.get('metadata', {}).get('source', 'unknown')}\n"
                f"Content: {doc.get('content', '').strip()}"
                for doc in raw_parents
            ])            

        except Exception as e:
            return f"PARENT_RETRIEVAL_ERROR: {str(e)}"
    
    def _retrieve_parent_chunks(self, parent_id: str) -> str:
        """Retrieve full parent chunks by their IDs.
    
        Args:
            parent_id: Parent chunk ID to retrieve
        """
        try:
            parent = self.parent_store_manager.load_content(parent_id)
            if not parent:
                return "NO_PARENT_DOCUMENT"

            return (
                f"Parent ID: {parent.get('parent_id', 'n/a')}\n"
                f"File Name: {parent.get('metadata', {}).get('source', 'unknown')}\n"
                f"Content: {parent.get('content', '').strip()}"
            )          

        except Exception as e:
            return f"PARENT_RETRIEVAL_ERROR: {str(e)}"
    
    def create_tools(self) -> List:
        """Create and return the list of tools."""
        search_tool = tool("search_child_chunks")(self._search_child_chunks)
        retrieve_tool = tool("retrieve_parent_chunks")(self._retrieve_parent_chunks)
        
        return [search_tool, retrieve_tool]
