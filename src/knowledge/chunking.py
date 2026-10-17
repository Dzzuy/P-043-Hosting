"""Structure-aware, verbatim chunks with recursive splitting for oversized blocks."""

import json
import re
from dataclasses import dataclass
from pathlib import Path

from langchain_text_splitters import RecursiveCharacterTextSplitter

from src.knowledge.schemas import ChunkMetadata, KnowledgeChunk, KnowledgeDocument

CHUNK_SIZE = 750
CHUNK_OVERLAP = 100
CHUNKING_STRATEGY = "structure-recursive-v2"
EMBEDDING_TEXT_VERSION = "title-model-section-content-v2"

_PARAGRAPH_BREAK = re.compile(r"(?:\r?\n[ \t]*){2,}")
_LINE_HEADING_BREAK = re.compile(
    r"(?<=\n)(?=[ \t]*(?:#{1,6}\s+|(?:điều)\s+\d+[.\s:]|(?:\d+(?:\.\d+)*[.)]|[a-zA-Z]\.)\s+))",
    re.I,
)
_NUMBERED_HEADING = re.compile(r"^(\d+(?:\.\d+)*)(?:\.\s+(?:\|\s*)?|\s+\|\s*)(.+)")
_LETTER_HEADING = re.compile(r"^[a-zA-Z]\.\s+(?:\|\s*)?(.+)")
_ARTICLE = re.compile(r"^điều\s+\d+[.\s:]", re.I)
_MODEL_HEADING = re.compile(r"^VF[ -]*\d+\b", re.I)
_BULLET = re.compile(r"^(?:[-•]|o\s*\|)\s*(?:\|\s*)?")
_SPEC_LABEL = re.compile(
    r"^(?:dung lượng pin|công suất|mô[ -]?men|mô men|quãng đường|dài\s*x|chiều|"
    r"loại la.zăng|mức tiêu thụ|số (?:ghế|chỗ)|thời gian (?:nạp|sạc)|túi khí|"
    r"bảo hành|động cơ|tốc độ|khoảng sáng|trọng lượng)",
    re.I,
)
_VALUE = re.compile(r"^(?:[≈~]?\d|từ\s+\d|hợp kim\s+\d|\(tùy điều kiện)", re.I)
_UNIT = re.compile(r"^(?:kw(?:h|/hp)?|hp/?|Nm|km(?:/lần sạc)?\*?|VNĐ\*?|năm|mm|kg)$", re.I)
_TABLE_HEADER = re.compile(
    r"^(?:dòng xe|phiên bản|tiêu chuẩn|hạng (?:thẻ|thành viên)|khung giờ|"
    r"tài xế mua xe|mức chi tiêu|màu ngoại thất|trang bị|số\s*\||tt\s*\||lượng\s*\|)",
    re.I,
)
_HEADINGS = {
    "thông số kỹ thuật",
    "kích thước",
    "pin & sạc",
    "pin và sạc",
    "công nghệ trang bị",
    "an toàn",
    "nội thất",
    "ngoại thất",
    "vận hành",
    "nội dung chính sách:",
    "nội dung chính sách",
    "nội dung chính sách ưu đãi:",
    "lưu ý:",
}


@dataclass(frozen=True)
class _Span:
    start: int
    end: int


@dataclass(frozen=True)
class _Section:
    spans: tuple[_Span, ...]
    title: str | None
    inherited_headers: tuple[str, ...] = ()


def chunking_identity(size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> dict:
    return {
        "size": size,
        "overlap": overlap,
        "unit": "characters",
        "strategy": CHUNKING_STRATEGY,
        "embedding_text": EMBEDDING_TEXT_VERSION,
    }


def _trim_span(content: str, start: int, end: int) -> _Span | None:
    while start < end and content[start].isspace():
        start += 1
    while end > start and content[end - 1].isspace():
        end -= 1
    return _Span(start, end) if start < end else None


def _paragraphs(content: str, product_specs: bool = False) -> list[_Span]:
    result, start = [], 0
    breaks = list(_PARAGRAPH_BREAK.finditer(content)) + list(_LINE_HEADING_BREAK.finditer(content))
    if product_specs:
        breaks += list(re.finditer(r"\r?\n", content))
    for match in sorted(breaks, key=lambda match: (match.start(), -match.end())):
        if match.start() < start:
            continue
        if span := _trim_span(content, start, match.start()):
            result.append(span)
        start = match.end()
    if span := _trim_span(content, start, len(content)):
        result.append(span)
    return result


def _heading(text: str, product_specs: bool) -> tuple[int, str] | None:
    first = text.splitlines()[0].strip()
    if first.startswith("#") and (match := re.match(r"^(#{1,6})\s+(.+)", first)):
        return len(match[1]), match[2]
    if _ARTICLE.match(first):
        return 1, first[:200]
    # Price rows can start with a number; they must not become section headings.
    if text.count("|") < 2 and (match := _NUMBERED_HEADING.match(first)):
        return match[1].count(".") + 1, first[:200]
    if _LETTER_HEADING.match(first):
        return (1 if first[0].isupper() else 2), first[:200]
    if product_specs and "|" not in text and len(text) <= 140 and _MODEL_HEADING.match(text):
        return 3, text
    if text.casefold().startswith("nội dung chính sách") and text.casefold() in _HEADINGS:
        return 0, text
    if len(text) <= 160 and (text.casefold() in _HEADINGS or text.casefold().startswith("giá bán bán lẻ đề xuất")):
        return 2, text
    if product_specs and text.casefold() in {"công nghệ", "thiết kế"}:
        return 2, text
    return None


def _sections(content: str, product_specs: bool) -> list[_Section]:
    result, current, headings = [], [], {}
    title, headers, inherited = None, [], ()
    for span in _paragraphs(content, product_specs):
        text = content[span.start : span.end]
        if heading := _heading(text, product_specs):
            # Attach standalone ancestor headings to their first subsection.
            level, label = heading
            parent = headings.get(1, "")
            if _NUMBERED_HEADING.match(text.splitlines()[0]) and (
                _ARTICLE.match(parent) or (parent[:1].isupper() and _LETTER_HEADING.match(parent))
            ):
                level += 1
            standalone_ancestors = level > max(headings, default=0) and all(
                len(content[s.start : s.end].splitlines()) == 1
                and len(content[s.start : s.end]) <= 200
                and _heading(content[s.start : s.end], product_specs)
                for s in current
            )
            if current and not standalone_ancestors:
                result.append(_Section(tuple(current), title, inherited))
                current = []
            if level <= 2:
                headers = []
            inherited = tuple(headers)
            headings = {depth: value for depth, value in headings.items() if depth < level}
            headings[level] = label
            title = " > ".join(headings[depth] for depth in sorted(headings))
        current.append(span)
        if _is_table_header(text):
            headers.append(text)
    if current:
        result.append(_Section(tuple(current), title, inherited))
    return result


def _is_value(text: str) -> bool:
    return bool(_VALUE.match(text) or _UNIT.fullmatch(text))


def _atoms(content: str, section: _Section, product_specs: bool) -> list[_Span]:
    """Keep labels/values, individual table rows and wrapped bullet clauses together."""
    spans, result, index = section.spans, [], 0
    while index < len(spans):
        start, end = spans[index].start, spans[index].end
        text = content[start:end]
        index += 1
        # A PDF-extracted price row may wrap its colour or currency cell.
        if "|" in text and not _is_table_header(text) and not _BULLET.match(text):
            if index < len(spans):
                following = content[spans[index].start : spans[index].end]
                if re.fullmatch(r"(?:VNĐ|VND)", following, re.I) or (
                    re.search(r"\d[\d.,]*\s*$", text)
                    and "|" in following
                    and re.search(r"\|\s*(?:VNĐ|VND)\s*$", following, re.I)
                ):
                    end = spans[index].end
                    index += 1
        elif product_specs and "|" not in text and (_SPEC_LABEL.match(text) or _is_value(text)):
            label_first = bool(_SPEC_LABEL.match(text))
            while index < len(spans):
                following = content[spans[index].start : spans[index].end]
                if "|" in following:
                    break
                if _is_value(following):
                    end = spans[index].end
                    index += 1
                elif not label_first and _SPEC_LABEL.match(following):
                    end = spans[index].end
                    index += 1
                    break
                else:
                    break
        elif _BULLET.match(text):
            while index < len(spans):
                following = content[spans[index].start : spans[index].end]
                if _BULLET.match(following) or "|" in following or _heading(following, product_specs):
                    break
                # PDF extraction may put a blank line inside one sentence.
                if content[start:end].rstrip().endswith((".", "!", "?", ";", ":")):
                    break
                end = spans[index].end
                index += 1
        result.append(_Span(start, end))
    return result


def _split_atoms(content: str, atoms: list[_Span], size: int, overlap: int) -> list[tuple[_Span, bool]]:
    result, buffer = [], []
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=size,
        chunk_overlap=overlap,
        separators=["\n\n", "\n", ". ", "; ", " ", ""],
        add_start_index=True,
    )
    for atom in atoms:
        if atom.end - atom.start > size:
            if buffer:
                result.append((_Span(buffer[0].start, buffer[-1].end), False))
                buffer = []
            for part in splitter.create_documents([content[atom.start : atom.end]]):
                start = atom.start + part.metadata["start_index"]
                if (
                    part.metadata["start_index"] < 0
                    or content[start : start + len(part.page_content)] != part.page_content
                ):
                    raise ValueError("Recursive split lost its source offsets")
                result.append((_Span(start, start + len(part.page_content)), True))
            continue
        if buffer and atom.end - buffer[0].start > size:
            result.append((_Span(buffer[0].start, buffer[-1].end), False))
            # Overlap whole atoms only: never repeat an orphan value or half a row.
            tail = []
            for previous in reversed(buffer):
                if buffer[-1].end - previous.start > overlap or atom.end - previous.start > size:
                    break
                tail.insert(0, previous)
            buffer = tail
        buffer.append(atom)
    if buffer:
        result.append((_Span(buffer[0].start, buffer[-1].end), False))
    return result


def _is_table_header(text: str) -> bool:
    return "|" in text and bool(_TABLE_HEADER.match(text)) and not re.search(r"\d[\d.,]*\s*(?:VNĐ|VND|%)", text, re.I)


def _context_prefix(content: str, section: _Section, span: _Span) -> str | None:
    headers = list(section.inherited_headers)
    for paragraph in section.spans:
        if paragraph.start >= span.end:
            break
        text = content[paragraph.start : paragraph.end]
        if _is_table_header(text):
            headers.append(text)
    return "\n".join(dict.fromkeys(headers)) or None


def chunk_embedding_text(chunk: KnowledgeChunk) -> str:
    """Context enriches search inputs; citation content remains verbatim."""
    meta = chunk.metadata
    return "\n".join(
        value
        for value in (meta.title, meta.product_model, meta.section_title, meta.context_prefix, chunk.content)
        if value
    )


def chunk_document(
    doc: KnowledgeDocument,
    chunk_size: int = CHUNK_SIZE,
    chunk_overlap: int = CHUNK_OVERLAP,
) -> list[KnowledgeChunk]:
    """Pack source structure under a character cap; recursively split oversized atoms."""
    if chunk_size <= 0 or not 0 <= chunk_overlap < chunk_size:
        raise ValueError("Require chunk_size > 0 and 0 <= chunk_overlap < chunk_size")
    content = doc.content
    if not content.strip():
        return []
    chunks = []
    product_specs = doc.document_type.value == "product_specs"
    for section_index, section in enumerate(_sections(content, product_specs)):
        for span, requires_context in _split_atoms(
            content, _atoms(content, section, product_specs), chunk_size, chunk_overlap
        ):
            index = len(chunks)
            chunk_id = f"{doc.document_id}_{index}"
            metadata = ChunkMetadata(
                chunk_id=chunk_id,
                document_id=doc.document_id,
                title=doc.title,
                document_type=doc.document_type.value,
                product_model=doc.product_model,
                competitor_model=doc.competitor_model,
                policy_type=doc.policy_type,
                effective_date=doc.effective_date,
                expiry_date=doc.expiry_date,
                status=doc.status.value,
                source=doc.source,
                version=doc.version,
                chunk_index=index,
                section_id=f"{doc.document_id}:section:{section_index}",
                section_title=section.title,
                start_char=span.start,
                end_char=span.end,
                context_prefix=_context_prefix(content, section, span),
                requires_context=requires_context,
            )
            chunks.append(
                KnowledgeChunk(
                    chunk_id=chunk_id,
                    document_id=doc.document_id,
                    content=content[span.start : span.end],
                    metadata=metadata,
                )
            )
    return chunks


def load_and_chunk_corpus(
    corpus_path: str | Path = "data/knowledge/corpus.json",
    chunk_size: int = CHUNK_SIZE,
    chunk_overlap: int = CHUNK_OVERLAP,
) -> list[KnowledgeChunk]:
    """Load the normalized corpus using the same chunker as dense ingestion."""
    records = json.loads(Path(corpus_path).read_text(encoding="utf-8"))
    return [
        chunk
        for item in records
        for chunk in chunk_document(KnowledgeDocument.model_validate(item), chunk_size, chunk_overlap)
    ]
