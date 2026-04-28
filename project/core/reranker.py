"""Reranker implementations for LLM-based and model-based ranking."""

from abc import ABC, abstractmethod
from typing import List, Dict, Tuple


class BaseReranker(ABC):
    """Abstract base class for rerankers."""
    enabled = True
    
    @abstractmethod
    def rerank(self, query: str, chunks: List[Dict]) -> List[Tuple[Dict, float]]:
        """Rerank chunks and return them sorted by relevance score.
        
        Args:
            query: Query string
            chunks: List of chunk dictionaries with 'content' and 'metadata'
            
        Returns:
            List of (chunk, score) tuples sorted by score descending
        """
        pass


class LLMReranker(BaseReranker):
    """LLM-based reranker for semantic re-ranking."""
    
    def __init__(self, llm=None):
        """Initialize LLM reranker.
        
        Args:
            llm: LLM instance (optional, will use default from config if None)
        """
        self.llm = llm
        if self.llm is None:
            from langchain_openai import ChatOpenAI
            import config
            self.llm = ChatOpenAI(
                model=config.LLM_MODEL,
                temperature=0.1,
                base_url=config.LLM_BASE_URL,
                api_key=config.LLM_API_KEY
            )
    
    def rerank(self, query: str, chunks: List[Dict]) -> List[Tuple[Dict, float]]:
        """Rerank using LLM relevance scoring.
        
        Args:
            query: Query string
            chunks: List of chunk dictionaries
            
        Returns:
            List of (chunk, score) tuples sorted by relevance descending
        """
        if not chunks:
            return []
        
        from langchain_core.messages import SystemMessage, HumanMessage
        import json
        
        chunk_texts = "\n\n".join([
            f"[Chunk {i}]\n{chunk.get('content', '')[:300]}"
            for i, chunk in enumerate(chunks)
        ])
        
        system_prompt = """You are a relevance ranking expert. For each chunk, assign a relevance score (0-10) based on how well it answers the query.

Return ONLY valid JSON with chunk indices and scores, no extra text:
{
    "rankings": [
        {"index": 0, "score": 8.5},
        {"index": 1, "score": 6.2}
    ]
}
"""
        
        user_prompt = f"""Query: {query}

Chunks to rank:
{chunk_texts}

Rank each chunk by relevance (0-10, higher is more relevant)."""
        
        try:
            response = self.llm.invoke([
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_prompt)
            ])
            
            content = response.content.strip()
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0].strip()
            elif "```" in content:
                content = content.split("```")[1].split("```")[0].strip()
            
            data = json.loads(content)
            rankings = data.get("rankings", [])
            
            scored_chunks = []
            scored_indexes = set()
            for item in rankings:
                idx = item.get("index")
                score = item.get("score", 0)
                if 0 <= idx < len(chunks):
                    scored_chunks.append((chunks[idx], score))
                    scored_indexes.add(idx)

            for idx, chunk in enumerate(chunks):
                if idx not in scored_indexes:
                    scored_chunks.append((chunk, 0))
            
            return sorted(scored_chunks, key=lambda x: x[1], reverse=True)
        
        except Exception as e:
            print(f"⚠️ Reranking error: {e}. Returning original order.")
            return [(chunk, len(chunks) - i) for i, chunk in enumerate(chunks)]


class CrossEncoderReranker(BaseReranker):
    """Cross-encoder reranker for local semantic re-ranking."""
    
    def __init__(self, model_name: str = None):
        """Initialize cross-encoder reranker."""
        import config
        from sentence_transformers import CrossEncoder

        self.model_name = model_name or config.CROSS_ENCODER_RERANKER_MODEL
        self.model = CrossEncoder(self.model_name)
    
    def rerank(self, query: str, chunks: List[Dict]) -> List[Tuple[Dict, float]]:
        """Rerank using cross-encoder relevance scores.
        
        Args:
            query: Query string
            chunks: List of chunk dictionaries
            
        Returns:
            List of (chunk, score) tuples sorted by score descending
        """
        if not chunks:
            return []

        pairs = [(query, chunk.get("content", "")) for chunk in chunks]
        scores = self.model.predict(pairs)
        scored_chunks = [(chunk, float(score)) for chunk, score in zip(chunks, scores)]
        return sorted(scored_chunks, key=lambda x: x[1], reverse=True)


class NoReranker(BaseReranker):
    """Dummy reranker that returns chunks without reranking."""
    enabled = False
    
    def rerank(self, query: str, chunks: List[Dict]) -> List[Tuple[Dict, float]]:
        """Return chunks in original order with placeholder scores."""
        return [(chunk, 1.0) for chunk in chunks]


def get_reranker(reranker_type: str = None, llm=None) -> BaseReranker:
    """Factory function to get a reranker instance.
    
    Args:
        reranker_type: Type of reranker ('llm', 'cross_encoder', 'none', or None for config default)
        llm: LLM instance for LLMReranker
        
    Returns:
        Reranker instance
    """
    import config
    
    reranker_type = (reranker_type or getattr(config, "RERANKER_TYPE", "none")).strip().lower()
    
    if reranker_type == "llm":
        
        return LLMReranker(llm)
    elif reranker_type in {"cross_encoder", "cross-encoder", "bm25"}:
        if reranker_type == "bm25":
            print("⚠️ RERANKER_TYPE=bm25 is deprecated. Using cross-encoder reranker instead.")
        try:
            return CrossEncoderReranker()
        except Exception as e:
            print(f"⚠️ Could not initialize cross-encoder reranker: {e}. Reranker disabled.")
            return NoReranker()
    else:
        return NoReranker()
