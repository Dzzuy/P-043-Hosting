import logging

from langchain_core.embeddings import Embeddings

from src.knowledge.chunking import chunk_embedding_text
from src.knowledge.schemas import KnowledgeChunk
from src.observability import span
from src.services.llm import get_embeddings

logger = logging.getLogger(__name__)


class KnowledgeEmbeddingService:
    """Service tạo vector embedding chuẩn 1536 chiều (mặc định OpenAI text-embedding-3-small)."""

    def __init__(self, embeddings: Embeddings | None = None):
        from src.config import get_settings
        from src.knowledge.index_readiness import embedding_identity

        self.provenance = embedding_identity(get_settings())
        if embeddings is not None:
            self.provenance = {
                "provider": "hash" if hasattr(embeddings, "dimension") else "custom",
                "model": get_settings().embedding_model_name
                if hasattr(embeddings, "dimension")
                else getattr(embeddings, "model", "unknown"),
            }
        self.embeddings = embeddings or get_embeddings()

    @property
    def model_name(self) -> str:
        """Tên và thông số mô hình embedding đang sử dụng."""
        from src.config import get_settings

        settings = get_settings()
        if settings.embedding_provider == "hash" or hasattr(self.embeddings, "dimension"):
            target = settings.embedding_model_name
            dim = getattr(self.embeddings, "dimension", 1536)
            return f"DeterministicHashEmbeddings (target: {target}, dim: {dim})"
        if settings.embedding_provider == "openrouter":
            model = getattr(self.embeddings, "model", settings.embedding_model_name)
            return f"OpenRouter ({model})"
        model = getattr(self.embeddings, "model", getattr(self.embeddings, "model_name", settings.embedding_model_name))
        return f"OpenAI ({model})"

    def embed_chunks(self, chunks: list[KnowledgeChunk]) -> list[list[float]]:
        """Mã hóa toàn bộ danh sách chunks thành vector embedding."""
        if not chunks:
            return []
        # Crawled tables may omit the model name inside a chunk; retain its identity in the vector.
        texts = [chunk_embedding_text(c) for c in chunks]
        return self.embeddings.embed_documents(texts)

    def embed_query(self, query: str) -> list[float]:
        """Mã hóa câu hỏi truy vấn của người dùng thành vector."""
        with span("embedding.query", provider=self.provenance.get("provider"), model=self.provenance.get("model")):
            return self.embeddings.embed_query(query)

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """Mã hóa danh sách chuỗi văn bản thành vector."""
        if not texts:
            return []
        return self.embeddings.embed_documents(texts)
