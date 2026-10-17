from datetime import date
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class DocumentType(StrEnum):
    """5 loại tài liệu nghiệp vụ VinFast."""

    PRODUCT_SPECS = "product_specs"
    BATTLECARD = "battlecard"
    PRICE_LIST = "price_list"
    POLICY = "policy"
    PROMOTION = "promotion"


class DocumentStatus(StrEnum):
    """Trạng thái hiệu lực của tài liệu."""

    ACTIVE = "active"
    EXPIRED = "expired"


class KnowledgeDocument(BaseModel):
    """Model validate dữ liệu nạp từ corpus.json (bỏ qua hoàn toàn sales_script)."""

    model_config = ConfigDict(extra="ignore")

    document_id: str = Field(..., description="Mã định danh duy nhất của tài liệu")
    title: str = Field(..., description="Tiêu đề tài liệu")
    document_type: DocumentType
    product_model: str = Field(..., description="Dòng xe: VF 3, VF 5, VF 6, VF 7 hoặc ALL")
    competitor_model: str | None = None
    policy_type: str | None = None
    effective_date: date
    expiry_date: date | None = None
    source: str
    version: str = "1.0"
    status: DocumentStatus = DocumentStatus.ACTIVE
    content: str = Field(..., description="Nội dung tri thức kỹ thuật / chính sách thuần túy")


class ChunkMetadata(BaseModel):
    """Metadata phẳng lưu trong Vector Database phục vụ lọc có điều kiện (where)."""

    chunk_id: str
    document_id: str
    title: str
    document_type: str
    product_model: str
    competitor_model: str | None = None
    policy_type: str | None = None
    effective_date: date | str
    expiry_date: date | str | None = None
    status: str = "active"
    source: str
    version: str = "1.0"
    chunk_index: int = 0
    section_id: str | None = None
    section_title: str | None = None
    start_char: int | None = Field(default=None, ge=0)
    end_char: int | None = Field(default=None, ge=0)
    context_prefix: str | None = None
    requires_context: bool = False


class KnowledgeChunk(BaseModel):
    """Đơn vị chunk tri thức hoàn chỉnh."""

    chunk_id: str
    document_id: str
    content: str
    metadata: ChunkMetadata
