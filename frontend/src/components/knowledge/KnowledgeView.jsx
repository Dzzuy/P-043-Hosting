import { useEffect, useState } from 'react';
import {
  SearchIcon,
  ChevronRight,
  SparkleIcon,
  FileTextIcon,
  CopyIcon,
  CheckIcon,
  AlertCircleIcon,
  UploadIcon,
  CheckCircleIcon,
  CloseIcon,
  PolicyIcon,
  FeeIcon,
  CarIcon,
  FaqIcon,
  ChecklistIcon,
  FolderIcon,
  BatteryIcon,
  SettingsIcon,
  RulerIcon,
  ShieldCheckIcon,
  ClockIcon,
  PinIcon,
} from '../common/Icons';
import { Badge } from '../common/Badge';
import { Modal } from '../common/Modal';
import { VEHICLES, REQUIRED_VEHICLE_PDFS } from '../../data/vehicleData';
import { POLICIES, REQUIRED_POLICY_PDFS } from '../../data/policyData';
import { PRICING_TARIFFS, REQUIRED_FEE_PDFS } from '../../data/feeData';
import { FAQ_QUESTIONS, REQUIRED_FAQ_PDFS } from '../../data/faqData';
import {
  REQUIRED_DOC_CATEGORIES,
  TOTAL_REQUIRED_PDFS,
  INGESTION_GUIDE,
} from '../../data/requiredDocsData';
import { copilotApi } from '../../api/copilotApi';

export function KnowledgeView({ onOpenCopilotQuery, sourceDocumentId }) {
  const [subTab, setSubTab] = useState('policies'); // 'policies' | 'fees' | 'vehicles' | 'faq' | 'checklist'
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedVehicle, setSelectedVehicle] = useState(null);
  const [selectedDocument, setSelectedDocument] = useState(null);
  const [viewingPdf, setViewingPdf] = useState(null); // { title, url, filename }
  const [sourceError, setSourceError] = useState('');
  const [copiedId, setCopiedId] = useState(null);
  const [faqModelFilter, setFaqModelFilter] = useState('all');
  const [expandedFaqId, setExpandedFaqId] = useState(null);

  useEffect(() => {
    if (!sourceDocumentId) return;
    let active = true;
    copilotApi.getSource(sourceDocumentId)
      .then((document) => { if (active) setSelectedDocument(document); })
      .catch(() => { if (active) setSourceError('Không mở được tài liệu gốc. Vui lòng thử lại.'); });
    return () => { active = false; };
  }, [sourceDocumentId]);

  const handleCopyText = (text, id) => {
    if (!text) return;
    navigator.clipboard.writeText(text);
    setCopiedId(id);
    setTimeout(() => setCopiedId(null), 2000);
  };

  const handleOpenDocument = async (docId, fallbackTitle = '') => {
    setSourceError('');
    try {
      const doc = await copilotApi.getSource(docId);
      setSelectedDocument(doc);
    } catch {
      setSourceError(`Chưa tìm thấy tệp dữ liệu text cho "${fallbackTitle || docId}". Hãy mở xem trực tiếp file PDF bên dưới.`);
    }
  };

  // Filter real data arrays (derived from real PDF files in frontend/src/data)
  const filteredPolicies = POLICIES.filter(
    (p) =>
      p.title?.toLowerCase().includes(searchQuery.toLowerCase()) ||
      p.filename?.toLowerCase().includes(searchQuery.toLowerCase()) ||
      p.category?.toLowerCase().includes(searchQuery.toLowerCase()) ||
      p.summary?.toLowerCase().includes(searchQuery.toLowerCase())
  );

  const filteredFees = PRICING_TARIFFS.filter(
    (f) =>
      f.title?.toLowerCase().includes(searchQuery.toLowerCase()) ||
      f.filename?.toLowerCase().includes(searchQuery.toLowerCase()) ||
      f.category?.toLowerCase().includes(searchQuery.toLowerCase()) ||
      f.summary?.toLowerCase().includes(searchQuery.toLowerCase())
  );

  const filteredVehicles = VEHICLES.filter((v) => {
    if (!searchQuery.trim()) return true;
    const q = searchQuery.toLowerCase();
    return (
      v.name?.toLowerCase().includes(q) ||
      v.model?.toLowerCase().includes(q) ||
      v.segment?.toLowerCase().includes(q) ||
      v.tagline?.toLowerCase().includes(q) ||
      v.highlights?.some((h) => h.toLowerCase().includes(q))
    );
  });

  const filteredFaqs = FAQ_QUESTIONS.filter((f) => {
    const matchesModel =
      faqModelFilter === 'all' ||
      f.model === faqModelFilter ||
      f.category?.toLowerCase().includes(faqModelFilter.toLowerCase());
    if (!matchesModel) return false;
    if (!searchQuery.trim()) return true;
    const q = searchQuery.toLowerCase();
    return (
      f.question?.toLowerCase().includes(q) ||
      f.category?.toLowerCase().includes(q) ||
      f.answer?.toLowerCase().includes(q) ||
      f.model?.toLowerCase().includes(q)
    );
  });

  // Filter required PDF checklist arrays
  const filterPdfList = (list) => {
    if (!searchQuery.trim()) return list;
    const q = searchQuery.toLowerCase();
    return list.filter(
      (item) =>
        item.title?.toLowerCase().includes(q) ||
        item.filename?.toLowerCase().includes(q) ||
        item.document_id?.toLowerCase().includes(q) ||
        item.category?.toLowerCase().includes(q) ||
        item.model?.toLowerCase().includes(q) ||
        item.required_contents?.some((c) => c.toLowerCase().includes(q))
    );
  };

  const filteredVehiclePdfs = filterPdfList(REQUIRED_VEHICLE_PDFS);
  const filteredPolicyPdfs = filterPdfList(REQUIRED_POLICY_PDFS);
  const filteredFeePdfs = filterPdfList(REQUIRED_FEE_PDFS);
  const filteredFaqPdfs = filterPdfList(REQUIRED_FAQ_PDFS);

  // Render a source PDF with its summary and direct preview.
  const renderRealDocCard = (doc) => (
    <article key={doc.id} className="card-white knowledge-document-card">
      <div className="knowledge-document-meta">
        <div className="knowledge-document-meta-left">
          <Badge variant="highlight">{doc.category}</Badge>
          <span>Hiệu lực: {doc.effective_date}</span>
        </div>
        <span className="knowledge-document-status">
          <CheckCircleIcon style={{ width: 13, height: 13 }} />
          {doc.status}
        </span>
      </div>

      <div className="knowledge-document-body">
        <div className="knowledge-document-copy">
          <h3>{doc.title}</h3>
          <p>{doc.summary}</p>
          {doc.key_points?.length > 0 && (
            <div className="knowledge-document-points">
              <strong>ĐIỀU KHOẢN CỐT LÕI TƯ VẤN VIÊN CẦN NẮM:</strong>
              <ul>
                {doc.key_points.map((point, index) => (
                  <li key={index}>
                    <CheckIcon style={{ width: 13, height: 13, flexShrink: 0 }} />
                    <span>{point}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
        <div className="knowledge-document-side">
          <button
            type="button"
            className="knowledge-pdf-preview"
            onClick={() => setViewingPdf({ title: doc.title, url: doc.file_url, filename: doc.filename })}
            aria-label={`Mở PDF: ${doc.title}`}
          >
            <span className="knowledge-pdf-preview-icon"><FileTextIcon style={{ width: 40, height: 40 }} /></span>
            <span className="knowledge-pdf-preview-label">Mở PDF</span>
          </button>
          <button
            type="button"
            className="btn-outline knowledge-document-copilot"
            onClick={() => onOpenCopilotQuery && onOpenCopilotQuery(`Tra cứu tóm tắt điều khoản trong tài liệu "${doc.title}"`)}
          >
            Hỏi Copilot <SparkleIcon style={{ width: 13, height: 13 }} />
          </button>
        </div>
      </div>
    </article>
  );

  // Component rendering a Required PDF Card
  const renderPdfItemCard = (pdf) => {
    const isCopied = copiedId === pdf.id || copiedId === pdf.filename;
    return (
      <div
        key={pdf.id}
        className="card-white knowledge-document-card knowledge-required-card"
        style={{
          padding: '20px 24px',
          display: 'flex',
          flexDirection: 'column',
          gap: 14,
          border: '1px solid #ECECE8',
          borderLeft: '4px solid #71717A',
          borderRadius: 10,
        }}
      >
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: 10 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
            {pdf.model && <Badge variant="highlight">{pdf.model}</Badge>}
            {pdf.category && <Badge variant="default">{pdf.category}</Badge>}
            <span
              style={{
                fontSize: '0.72rem',
                fontWeight: 700,
                color: pdf.status?.includes('Đã nạp') ? '#18181B' : '#52525B',
                backgroundColor: '#F4F4F5',
                padding: '3px 8px',
                borderRadius: 4,
                display: 'inline-flex',
                alignItems: 'center',
                gap: 4,
              }}
            >
              {pdf.status?.includes('Đã nạp') ? <CheckCircleIcon style={{ width: 12, height: 12 }} /> : <ClockIcon style={{ width: 12, height: 12 }} />}
              {pdf.status}
            </span>
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <span style={{ fontSize: '0.75rem', color: '#737373' }}>
              Mã tài liệu: <code style={{ backgroundColor: '#F3F4F6', padding: '2px 6px', borderRadius: 4, fontWeight: 700, color: '#111827' }}>{pdf.document_id}</code>
            </span>
          </div>
        </div>

        <div>
          <h3 style={{ fontSize: '1.05rem', fontWeight: 700, color: '#111111' }}>
            {pdf.title}
          </h3>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 6, flexWrap: 'wrap' }}>
            <FileTextIcon style={{ width: 14, height: 14, color: '#52525B' }} />
            <span style={{ fontSize: '0.85rem', fontWeight: 600, color: '#1F2937' }}>
              Tên file chuẩn: <code>{pdf.filename}</code>
            </span>
            <button
              onClick={() => handleCopyText(pdf.filename, pdf.filename)}
              title="Sao chép tên file PDF"
              style={{
                background: 'none',
                border: 'none',
                cursor: 'pointer',
                display: 'inline-flex',
                alignItems: 'center',
                gap: 3,
                fontSize: '0.75rem',
                color: isCopied ? '#111111' : '#6B7280',
                padding: '2px 6px',
                borderRadius: 4,
                backgroundColor: '#F3F4F6',
              }}
            >
              {isCopied ? <CheckIcon style={{ width: 12, height: 12 }} /> : <CopyIcon style={{ width: 12, height: 12 }} />}
              <span>{isCopied ? 'Đã sao chép tên file' : 'Sao chép'}</span>
            </button>
          </div>
        </div>

        {/* Required Contents Box */}
        <div style={{ backgroundColor: '#F9FAFB', padding: '12px 16px', borderRadius: 8, border: '1px solid #E5E7EB' }}>
          <div style={{ fontSize: '0.76rem', fontWeight: 700, color: '#374151', textTransform: 'uppercase', letterSpacing: '0.04em', marginBottom: 6 }}>
            <span style={{ display: "inline-flex", alignItems: "center", gap: 4 }}><PinIcon style={{ width: 12, height: 12 }} /> NỘI DUNG CẦN CÓ TRONG TÀI LIỆU:</span>
          </div>
          <ul style={{ listStyle: 'none', paddingLeft: 0, margin: 0, display: 'flex', flexDirection: 'column', gap: 5 }}>
            {pdf.required_contents?.map((item, idx) => (
              <li key={idx} style={{ fontSize: '0.82rem', color: '#4B5563', display: 'flex', alignItems: 'flex-start', gap: 6 }}>
                <span style={{ color: '#71717A', fontWeight: 700 }}>•</span>
                <span>{item}</span>
              </li>
            ))}
          </ul>
        </div>

        {/* Footer specs & actions */}
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 10, paddingTop: 10, borderTop: '1px solid #F3F4F6', fontSize: '0.75rem', color: '#6B7280' }}>
          <div>
            <span>Định dạng: <strong>{pdf.target_format || 'PDF (.pdf)'}</strong></span>
            {pdf.recommended_pages && <span> • Khuyến nghị: <strong>{pdf.recommended_pages}</strong></span>}
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <button
              className="btn-outline"
              onClick={() => handleOpenDocument(pdf.document_id, pdf.title)}
              style={{ fontSize: '0.78rem', padding: '6px 12px' }}
            >
              <span>Kiểm tra tệp mẫu</span>
              <ChevronRight style={{ width: 12, height: 12 }} />
            </button>
            <button
              className="btn-primary"
              onClick={() => onOpenCopilotQuery && onOpenCopilotQuery(`Tra cứu thông tin về ${pdf.title} theo mã ${pdf.document_id}`)}
              style={{ fontSize: '0.78rem', padding: '6px 12px' }}
            >
              <span>Hỏi Copilot</span>
              <SparkleIcon style={{ width: 12, height: 12 }} />
            </button>
          </div>
        </div>
      </div>
    );
  };

  // Component for section header when data is empty
  const renderEmptySectionNotice = (title, count, docType) => (
    <div
      style={{
        padding: '24px 28px',
        borderRadius: 12,
        backgroundColor: '#FFFFFF',
        border: '1px solid #E5E7EB',
        display: 'flex',
        flexDirection: 'column',
        gap: 12,
        boxShadow: '0 1px 3px rgba(0,0,0,0.03)',
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
        <div style={{ width: 36, height: 36, borderRadius: 8, backgroundColor: '#F4F4F5', color: '#18181B', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
          <AlertCircleIcon style={{ width: 20, height: 20 }} />
        </div>
        <div>
          <h2 style={{ fontSize: '1.15rem', fontWeight: 800, color: '#111827' }}>
            {title} — Dữ liệu đang để trống
          </h2>
          <p style={{ fontSize: '0.85rem', color: '#6B7280', marginTop: 2 }}>
            Hệ thống không sử dụng dữ liệu tự tạo. Danh sách hiện đang để trống theo yêu cầu và sẵn sàng tiếp nhận {count} tệp PDF tài liệu chính thức từ quản trị viên.
          </p>
        </div>
      </div>

      <div style={{ display: 'flex', alignItems: 'center', gap: 14, flexWrap: 'wrap', backgroundColor: '#F9FAFB', padding: '10px 16px', borderRadius: 8, fontSize: '0.8rem', color: '#4B5563' }}>
        <span>Thư mục tiếp nhận: <code style={{ fontWeight: 700, color: '#111827' }}>data/knowledge/</code></span>
        <span>•</span>
        <span>Số lượng tệp cần nạp: <strong style={{ color: '#18181B' }}>{count} tệp PDF</strong></span>
        <span>•</span>
        <span>Định dạng: <code>{docType}</code></span>
      </div>
    </div>
  );

  return (
    <div className="knowledge-page" style={{ display: 'flex', flexDirection: 'column', gap: 24 }}>
      {sourceError && (
        <div
          role="alert"
          style={{
            padding: '12px 16px',
            borderRadius: 8,
            backgroundColor: '#FEF2F2',
            border: '1px solid #FCA5A5',
            color: '#991B1B',
            fontSize: '0.85rem',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            gap: 10,
          }}
        >
          <span>{sourceError}</span>
          <button
            onClick={() => setSourceError('')}
            style={{ background: 'none', border: 'none', color: '#991B1B', cursor: 'pointer', display: 'flex', alignItems: 'center', padding: 2 }}
            aria-label="Đóng"
          >
            <CloseIcon style={{ width: 14, height: 14 }} />
          </button>
        </div>
      )}

      {/* TOP HEADER & SEARCH */}
      <div className="knowledge-page-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: 16 }}>
        <div>
          <h1 className="knowledge-page-title" style={{ fontSize: '1.75rem', fontWeight: 800, color: '#111111', letterSpacing: '-0.02em' }}>
            Cẩm nang Sản phẩm, Chính sách & Biểu phí Bán hàng
          </h1>
          <p style={{ fontSize: '0.88rem', color: '#737373', marginTop: 4 }}>
            Tra cứu các tệp văn bản PDF hợp đồng mua bán, chính sách pin, biểu phí bán xe và hạ tầng trạm sạc VinFast.
          </p>
        </div>

        {/* SEARCH BAR */}
        <div className="knowledge-search" style={{ position: 'relative', width: 280 }}>
          <SearchIcon style={{ position: 'absolute', left: 12, top: 12, width: 16, height: 16, color: '#888888' }} />
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Tìm theo tên file, dòng xe, mã số..."
            style={{
              width: '100%',
              padding: '9px 12px 9px 36px',
              borderRadius: 9999,
              border: '1px solid #E5E5E5',
              backgroundColor: '#FFFFFF',
              outline: 'none',
              fontSize: '0.85rem',
            }}
          />
        </div>
      </div>

      {/* STATUS OVERVIEW BANNER */}
      <div
        className="card-white knowledge-overview"
        style={{
          padding: '14px 18px',
          borderLeft: '4px solid #0F172A',
          display: 'flex',
          flexDirection: 'column',
          gap: 12,
          backgroundColor: '#F8FAFC',
        }}
      >
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 10 }}>
          <button
            className={`btn-outline knowledge-checklist-button${subTab === 'checklist' ? ' active' : ''}`}
            onClick={() => setSubTab('checklist')}
            aria-pressed={subTab === 'checklist'}
            style={{ fontSize: '0.78rem', padding: '5px 12px', backgroundColor: '#FFFFFF', display: 'inline-flex', alignItems: 'center', gap: 6 }}
          >
            <ChecklistIcon style={{ width: 13, height: 13 }} />
            <span>Danh mục {TOTAL_REQUIRED_PDFS} tài liệu</span>
            <ChevronRight style={{ width: 12, height: 12 }} />
          </button>
        </div>

        <div className="knowledge-stats" style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: 10 }}>
          <button type="button" className={`knowledge-stat-button${subTab === 'policies' ? ' active' : ''}`} onClick={() => setSubTab('policies')} aria-pressed={subTab === 'policies'}>
            <div style={{ width: 32, height: 32, borderRadius: 6, backgroundColor: '#F1F5F9', display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#0F172A', flexShrink: 0 }}>
              <PolicyIcon style={{ width: 16, height: 16 }} />
            </div>
            <div>
              <span style={{ fontSize: '0.72rem', color: '#64748B', display: 'block' }}>Chính sách & Hợp đồng</span>
              <strong style={{ fontSize: '0.98rem', color: '#0F172A' }}>{POLICIES.length} tệp</strong>
            </div>
          </button>
          <button type="button" className={`knowledge-stat-button${subTab === 'fees' ? ' active' : ''}`} onClick={() => setSubTab('fees')} aria-pressed={subTab === 'fees'}>
            <div style={{ width: 32, height: 32, borderRadius: 6, backgroundColor: '#F1F5F9', display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#0F172A', flexShrink: 0 }}>
              <FeeIcon style={{ width: 16, height: 16 }} />
            </div>
            <div>
              <span style={{ fontSize: '0.72rem', color: '#64748B', display: 'block' }}>Biểu phí & Bảng giá</span>
              <strong style={{ fontSize: '0.98rem', color: '#0F172A' }}>{PRICING_TARIFFS.length} tệp</strong>
            </div>
          </button>
          <button type="button" className={`knowledge-stat-button${subTab === 'vehicles' ? ' active' : ''}`} onClick={() => setSubTab('vehicles')} aria-pressed={subTab === 'vehicles'}>
            <div style={{ width: 32, height: 32, borderRadius: 6, backgroundColor: '#F1F5F9', display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#0F172A', flexShrink: 0 }}>
              <CarIcon style={{ width: 16, height: 16 }} />
            </div>
            <div>
              <span style={{ fontSize: '0.72rem', color: '#64748B', display: 'block' }}>Thông số xe</span>
              <strong style={{ fontSize: '0.98rem', color: '#0F172A' }}>{VEHICLES.length} dòng xe</strong>
            </div>
          </button>
          <button type="button" className={`knowledge-stat-button${subTab === 'faq' ? ' active' : ''}`} onClick={() => setSubTab('faq')} aria-pressed={subTab === 'faq'}>
            <div style={{ width: 32, height: 32, borderRadius: 6, backgroundColor: '#F1F5F9', display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#0F172A', flexShrink: 0 }}>
              <FaqIcon style={{ width: 16, height: 16 }} />
            </div>
            <div>
              <span style={{ fontSize: '0.72rem', color: '#64748B', display: 'block' }}>Hỏi đáp FAQ</span>
              <strong style={{ fontSize: '0.98rem', color: '#0F172A' }}>{FAQ_QUESTIONS.length} câu hỏi</strong>
            </div>
          </button>
        </div>
      </div>

      {/* 1. POLICIES TAB: HIỂN THỊ CÁC TỆP PDF CHÍNH SÁCH THỰC TẾ */}
      {subTab === 'policies' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          <div
            className="knowledge-section-heading"
            style={{
              padding: '16px 20px',
              borderRadius: 10,
              backgroundColor: '#FAFAFA',
              border: '1px solid #E4E4E7',
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
              flexWrap: 'wrap',
              gap: 10,
            }}
          >
            <div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <CheckCircleIcon style={{ width: 18, height: 18, color: '#18181B' }} />
                <h3 style={{ fontSize: '1rem', fontWeight: 800, color: '#18181B' }}>
                  Chính sách & Hợp đồng
                </h3>
              </div>
              <p style={{ fontSize: '0.82rem', color: '#52525B', marginTop: 2 }}>
                Dữ liệu lấy trực tiếp từ các file PDF văn bản pháp lý chính thức.
              </p>
            </div>
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
            {filteredPolicies.map((p) => renderRealDocCard(p))}
          </div>

          {/* CHECKLIST ĐỐI CHIẾU NẾU CẦN BỔ SUNG */}
          {REQUIRED_POLICY_PDFS.length > 0 && (
            <div style={{ marginTop: 20, paddingTop: 16, borderTop: '1px dashed #E2E8F0' }}>
              <details style={{ cursor: 'pointer' }}>
                <summary style={{ fontSize: '0.85rem', fontWeight: 700, color: '#475569' }}>
                  <span style={{ display: "inline-flex", alignItems: "center", gap: 6 }}><FolderIcon style={{ width: 14, height: 14 }} /> Danh mục tài liệu bổ sung ({REQUIRED_POLICY_PDFS.length})</span>
                </summary>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 12, marginTop: 12 }}>
                  {filteredPolicyPdfs.map((pdf) => renderPdfItemCard(pdf))}
                </div>
              </details>
            </div>
          )}
        </div>
      )}

      {/* 2. FEES TAB: HIỂN THỊ CÁC TỆP PDF BIỂU PHÍ & BẢNG GIÁ THỰC TẾ */}
      {subTab === 'fees' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          <div
            className="knowledge-section-heading"
            style={{
              padding: '16px 20px',
              borderRadius: 10,
              backgroundColor: '#FAFAFA',
              border: '1px solid #E4E4E7',
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
              flexWrap: 'wrap',
              gap: 10,
            }}
          >
            <div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <CheckCircleIcon style={{ width: 18, height: 18, color: '#18181B' }} />
                <h3 style={{ fontSize: '1rem', fontWeight: 800, color: '#18181B' }}>
                  Biểu phí & Bảng giá
                </h3>
              </div>
              <p style={{ fontSize: '0.82rem', color: '#52525B', marginTop: 2 }}>
                Dữ liệu lấy từ các văn bản bảng giá xe niêm yết, tùy chọn trang bị và biểu phí dịch vụ sạc V-GREEN.
              </p>
            </div>
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
            {filteredFees.map((f) => renderRealDocCard(f))}
          </div>

          {/* CHECKLIST ĐỐI CHIẾU */}
          {REQUIRED_FEE_PDFS.length > 0 && (
            <div style={{ marginTop: 20, paddingTop: 16, borderTop: '1px dashed #E2E8F0' }}>
              <details style={{ cursor: 'pointer' }}>
                <summary style={{ fontSize: '0.85rem', fontWeight: 700, color: '#475569' }}>
                  <span style={{ display: "inline-flex", alignItems: "center", gap: 6 }}><FolderIcon style={{ width: 14, height: 14 }} /> Danh mục biểu phí bổ sung ({REQUIRED_FEE_PDFS.length})</span>
                </summary>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 12, marginTop: 12 }}>
                  {filteredFeePdfs.map((pdf) => renderPdfItemCard(pdf))}
                </div>
              </details>
            </div>
          )}
        </div>
      )}

      {/* 3. VEHICLES TAB: DẢI XE VINFAST CHÍNH THỨC */}
      {subTab === 'vehicles' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          {VEHICLES.length === 0 && renderEmptySectionNotice('Thông số xe & Trang bị kỹ thuật', REQUIRED_VEHICLE_PDFS.length, 'product_specs')}
          <div
            className="knowledge-section-heading"
            style={{
              padding: '16px 20px',
              borderRadius: 10,
              backgroundColor: '#FAFAFA',
              border: '1px solid #E4E4E7',
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
              flexWrap: 'wrap',
              gap: 10,
            }}
          >
            <div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <CheckCircleIcon style={{ width: 18, height: 18, color: '#18181B' }} />
                <h3 style={{ fontSize: '1rem', fontWeight: 800, color: '#18181B' }}>
                  Dải ô tô điện VinFast 2026
                </h3>
              </div>
              <p style={{ fontSize: '0.82rem', color: '#52525B', marginTop: 2 }}>
                Thông số kỹ thuật chuẩn hóa, giá niêm yết, pin và trang bị ADAS phục vụ tư vấn khách hàng.
              </p>
            </div>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(360px, 1fr))', gap: 20 }}>
            {filteredVehicles.map((v) => (
              <div
                key={v.id}
                className="card-white knowledge-vehicle-card"
                style={{
                  display: 'flex',
                  flexDirection: 'column',
                  justifyContent: 'space-between',
                  borderRadius: 12,
                  overflow: 'hidden',
                  border: '1px solid #E2E8F0',
                  boxShadow: '0 1px 3px rgba(0,0,0,0.04)',
                  backgroundColor: '#FFFFFF',
                }}
              >
                {/* Image Banner */}
                {v.image && (
                  <div style={{ width: '100%', height: 190, backgroundColor: '#0F172A', overflow: 'hidden', position: 'relative' }}>
                    <img
                      src={v.image}
                      alt={v.name}
                      style={{ width: '100%', height: '100%', objectFit: 'cover' }}
                      onError={(e) => {
                        if (v.id) e.target.src = `/vehicles/${v.id}.svg`;
                      }}
                    />
                    <div style={{ position: 'absolute', top: 12, left: 12 }}>
                      <span style={{ backgroundColor: 'rgba(0,0,0,0.75)', color: '#FFFFFF', padding: '4px 10px', borderRadius: 6, fontSize: '0.75rem', fontWeight: 700 }}>
                        {v.model}
                      </span>
                    </div>
                  </div>
                )}

                <div style={{ padding: 20, display: 'flex', flexDirection: 'column', gap: 14, flex: 1 }}>
                  <div>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', flexWrap: 'wrap', gap: 8 }}>
                      <h3 style={{ fontSize: '1.2rem', fontWeight: 700, color: '#0F172A' }}>{v.name}</h3>
                      <span style={{ fontSize: '0.78rem', color: '#64748B', fontWeight: 500 }}>{v.segment}</span>
                    </div>
                    {v.tagline && (
                      <p style={{ fontSize: '0.82rem', color: '#475569', fontStyle: 'italic', marginTop: 4 }}>
                        "{v.tagline}"
                      </p>
                    )}
                  </div>

                  {/* Specs Highlights */}
                  <div
                    style={{
                      display: 'grid',
                      gridTemplateColumns: '1fr 1fr',
                      gap: 10,
                      padding: '12px 14px',
                      backgroundColor: '#F8FAFC',
                      borderRadius: 10,
                      border: '1px solid #E2E8F0',
                    }}
                  >
                    <div>
                      <span style={{ fontSize: '0.7rem', color: '#64748B', display: 'block' }}>Quãng đường:</span>
                      <strong style={{ fontSize: '0.85rem', color: '#0F172A' }}>{v.range}</strong>
                    </div>
                    <div>
                      <span style={{ fontSize: '0.7rem', color: '#64748B', display: 'block' }}>Công suất:</span>
                      <strong style={{ fontSize: '0.85rem', color: '#0F172A' }}>{v.power}</strong>
                    </div>
                    <div>
                      <span style={{ fontSize: '0.7rem', color: '#64748B', display: 'block' }}>Dung lượng Pin:</span>
                      <strong style={{ fontSize: '0.85rem', color: '#0F172A' }}>{v.battery_capacity}</strong>
                    </div>
                    <div>
                      <span style={{ fontSize: '0.7rem', color: '#64748B', display: 'block' }}>Sạc nhanh (DC):</span>
                      <strong style={{ fontSize: '0.85rem', color: '#0F172A' }}>{v.charging_time}</strong>
                    </div>
                  </div>

                  {/* Pricing info */}
                  {(v.price_battery_included || v.price_battery_rental) && (
                    <div style={{ padding: '10px 12px', backgroundColor: '#F1F5F9', borderRadius: 8, fontSize: '0.8rem', color: '#334155' }}>
                      {v.price_battery_included && (
                        <div><FeeIcon style={{ width: 13, height: 13, display: "inline", verticalAlign: "-2px", marginRight: 4 }} /> <strong>Kèm pin:</strong> {v.price_battery_included}</div>
                      )}
                      {v.price_battery_rental && (
                        <div style={{ marginTop: 2 }}><BatteryIcon style={{ width: 13, height: 13, display: "inline", verticalAlign: "-2px", marginRight: 4 }} /> <strong>Thuê pin:</strong> {v.price_battery_rental}</div>
                      )}
                    </div>
                  )}

                  {/* Action buttons */}
                  <div style={{ display: 'flex', gap: 8, marginTop: 'auto', paddingTop: 8, borderTop: '1px solid #F1F5F9', flexWrap: 'wrap' }}>
                    <button
                      className="btn-primary"
                      onClick={() => setSelectedVehicle(v)}
                      style={{ flex: 1, fontSize: '0.8rem', padding: '8px 12px', justifyContent: 'center' }}
                    >
                      <span>Chi tiết kỹ thuật</span>
                      <ChevronRight style={{ width: 13, height: 13 }} />
                    </button>
                    {v.document_id && (
                      <button
                        className="btn-outline"
                        onClick={() => handleOpenDocument(v.document_id, v.name)}
                        style={{ fontSize: '0.8rem', padding: '8px 12px' }}
                        title="Xem văn bản gốc trong Corpus"
                      >
                        <span>Văn bản gốc</span>
                      </button>
                    )}
                    <button
                      className="btn-outline"
                      onClick={() => onOpenCopilotQuery && onOpenCopilotQuery(`Tư vấn thông số kỹ thuật xe ${v.name}`)}
                      style={{ fontSize: '0.8rem', padding: '8px 10px' }}
                      title="Hỏi Copilot về xe này"
                    >
                      <SparkleIcon style={{ width: 14, height: 14 }} />
                    </button>
                  </div>
                </div>
              </div>
            ))}
          </div>

          {/* Collapsible reference PDF documents */}
          <div style={{ marginTop: 8 }}>
            <details style={{ cursor: 'pointer' }}>
              <summary style={{ fontSize: '0.85rem', fontWeight: 700, color: '#475569' }}>
                <span style={{ display: "inline-flex", alignItems: "center", gap: 6 }}><FolderIcon style={{ width: 14, height: 14 }} /> Danh mục tài liệu kỹ thuật ({REQUIRED_VEHICLE_PDFS.length})</span>
              </summary>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 12, marginTop: 12 }}>
                {filteredVehiclePdfs.map((pdf) => renderPdfItemCard(pdf))}
              </div>
            </details>
          </div>
        </div>
      )}

      {/* 4. FAQ TAB: NGÂN HÀNG CÂU HỎI THƯỜNG GẶP FAQ */}
      {subTab === 'faq' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          {FAQ_QUESTIONS.length === 0 && renderEmptySectionNotice('Câu hỏi thường gặp FAQ', REQUIRED_FAQ_PDFS.length, 'faq')}
          <div
            className="knowledge-section-heading"
            style={{
              padding: '16px 20px',
              borderRadius: 10,
              backgroundColor: '#FAFAFA',
              border: '1px solid #E4E4E7',
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
              flexWrap: 'wrap',
              gap: 10,
            }}
          >
            <div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <CheckCircleIcon style={{ width: 18, height: 18, color: '#18181B' }} />
                <h3 style={{ fontSize: '1rem', fontWeight: 800, color: '#18181B' }}>
                  Ngân hàng Câu hỏi thường gặp FAQ VinFast 2026
                </h3>
              </div>
              <p style={{ fontSize: '0.82rem', color: '#52525B', marginTop: 2 }}>
                Giải đáp chi tiết thắc mắc khách hàng theo từng dòng xe, pin & trạm sạc V-GREEN, bảo hành và tiện ích thông minh.
              </p>
            </div>
          </div>

          {/* Model filter chips */}
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
            {[
              { id: 'all', label: `Tất cả (${FAQ_QUESTIONS.length})` },
              { id: 'VF 3', label: 'VF 3' },
              { id: 'VF 5', label: 'VF 5 Plus' },
              { id: 'VF 6', label: 'VF 6' },
              { id: 'VF 7', label: 'VF 7' },
              { id: 'VF 8', label: 'VF 8' },
              { id: 'VF 9', label: 'VF 9' },
            ].map((m) => (
              <button
                key={m.id}
                className={`chip ${faqModelFilter === m.id ? 'active' : ''}`}
                onClick={() => setFaqModelFilter(m.id)}
                style={{ fontSize: '0.78rem' }}
              >
                {m.label}
              </button>
            ))}
          </div>

          {/* FAQ list */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
            {filteredFaqs.map((f) => {
              const isExpanded = expandedFaqId === f.id;
              return (
                <div
                  key={f.id}
                  className="card-white knowledge-faq-card"
                  style={{
                    padding: '18px 22px',
                    display: 'flex',
                    flexDirection: 'column',
                    gap: 12,
                    border: '1px solid #E2E8F0',
                    borderRadius: 10,
                  }}
                >
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: 10 }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
                      <Badge variant="highlight">{f.model || f.category}</Badge>
                      <span style={{ fontSize: '0.75rem', color: '#64748B' }}>
                        Tài liệu: <code>{f.document_id}</code>
                      </span>
                    </div>

                    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                      <button
                        className="btn-outline"
                        onClick={() => handleOpenDocument(f.document_id, f.category)}
                        style={{ fontSize: '0.75rem', padding: '4px 10px' }}
                        title="Xem toàn bộ tài liệu FAQ gốc"
                      >
                        <span>Văn bản gốc FAQ</span>
                      </button>
                      <button
                        className="btn-primary"
                        onClick={() => onOpenCopilotQuery && onOpenCopilotQuery(f.query || f.question)}
                        style={{ fontSize: '0.75rem', padding: '4px 12px' }}
                      >
                        <span>Hỏi Copilot</span>
                        <SparkleIcon style={{ width: 12, height: 12 }} />
                      </button>
                    </div>
                  </div>

                  <div>
                    <h3
                      onClick={() => setExpandedFaqId(isExpanded ? null : f.id)}
                      style={{ fontSize: '1.02rem', fontWeight: 700, color: '#0F172A', cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 10 }}
                    >
                      <span>{f.question}</span>
                      <span style={{ fontSize: '0.75rem', color: '#64748B', fontWeight: 400 }}>
                        {isExpanded ? 'Thu gọn ▲' : 'Xem chi tiết ▼'}
                      </span>
                    </h3>

                    {/* Answer content */}
                    <div style={{ marginTop: 8, fontSize: '0.86rem', color: '#334155', lineHeight: 1.6, backgroundColor: '#F8FAFC', padding: '12px 16px', borderRadius: 8, border: '1px solid #F1F5F9', whiteSpace: 'pre-line' }}>
                      {isExpanded ? f.answer : f.preview}
                    </div>
                  </div>
                </div>
              );
            })}
          </div>

          {/* Collapsible reference FAQ documents */}
          <div style={{ marginTop: 8 }}>
            <details style={{ cursor: 'pointer' }}>
              <summary style={{ fontSize: '0.85rem', fontWeight: 700, color: '#475569' }}>
                <span style={{ display: "inline-flex", alignItems: "center", gap: 6 }}><FolderIcon style={{ width: 14, height: 14 }} /> Danh mục tài liệu FAQ ({REQUIRED_FAQ_PDFS.length})</span>
              </summary>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 12, marginTop: 12 }}>
                {filteredFaqPdfs.map((pdf) => renderPdfItemCard(pdf))}
              </div>
            </details>
          </div>
        </div>
      )}

      {/* 5. CHECKLIST TAB: TỔNG HỢP TOÀN BỘ CÁC TỆP PDF */}
      {subTab === 'checklist' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
          {/* TECHNICAL INGESTION GUIDE BOX */}
          <div
            className="card-white"
            style={{
              padding: '24px 28px',
              backgroundColor: '#0F172A',
              color: '#FFFFFF',
              borderRadius: 12,
              display: 'flex',
              flexDirection: 'column',
              gap: 16,
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
              <div style={{ width: 36, height: 36, borderRadius: 8, backgroundColor: '#1E293B', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                <UploadIcon style={{ width: 20, height: 20, color: '#E4E4E7' }} />
              </div>
              <div>
                <h2 style={{ fontSize: '1.2rem', fontWeight: 800, color: '#FFFFFF' }}>
                  Thư mục Nạp Tệp PDF Dữ liệu Thực tế
                </h2>
                <p style={{ fontSize: '0.85rem', color: '#94A3B8', marginTop: 2 }}>
                  Tất cả các tệp PDF đặt trong <code>frontend/src/data/</code> tự động đồng bộ sang <code>frontend/public/docs/</code> để xem trực tiếp.
                </p>
              </div>
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))', gap: 14, paddingTop: 14, borderTop: '1px solid #1E293B' }}>
              <div>
                <span style={{ fontSize: '0.75rem', color: '#94A3B8', display: 'block' }}>1. Thư mục data PDF hiện tại:</span>
                <code style={{ fontSize: '0.85rem', color: '#E4E4E7', backgroundColor: '#1E293B', padding: '3px 8px', borderRadius: 4, display: 'inline-block', marginTop: 4 }}>
                  frontend/src/data/
                </code>
              </div>
              <div>
                <span style={{ fontSize: '0.75rem', color: '#94A3B8', display: 'block' }}>2. Thư mục web docs:</span>
                <code style={{ fontSize: '0.85rem', color: '#E4E4E7', backgroundColor: '#1E293B', padding: '3px 8px', borderRadius: 4, display: 'inline-block', marginTop: 4 }}>
                  frontend/public/docs/
                </code>
              </div>
              <div>
                <span style={{ fontSize: '0.75rem', color: '#94A3B8', display: 'block' }}>3. Thư mục RAG Knowledge:</span>
                <code style={{ fontSize: '0.85rem', color: '#FFFFFF', backgroundColor: '#1E293B', padding: '3px 8px', borderRadius: 4, display: 'inline-block', marginTop: 4 }}>
                  {INGESTION_GUIDE.storage_directory}
                </code>
              </div>
              <div>
                <span style={{ fontSize: '0.75rem', color: '#94A3B8', display: 'block' }}>4. File corpus xuất ra:</span>
                <code style={{ fontSize: '0.85rem', color: '#CBD5E1', backgroundColor: '#1E293B', padding: '3px 8px', borderRadius: 4, display: 'inline-block', marginTop: 4 }}>
                  {INGESTION_GUIDE.corpus_file}
                </code>
              </div>
            </div>
          </div>

          {/* CATEGORIES BREAKDOWN */}
          {REQUIRED_DOC_CATEGORIES.map((cat) => {
            const filteredItems = filterPdfList(cat.items);
            return (
              <div key={cat.key} style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', borderBottom: '2px solid #E5E7EB', paddingBottom: 8 }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <span style={{ display: 'inline-flex', alignItems: 'center', color: '#0F172A' }}>
                    {cat.key === 'vehicles' ? <CarIcon style={{ width: 20, height: 20 }} /> :
                     cat.key === 'policies' ? <PolicyIcon style={{ width: 20, height: 20 }} /> :
                     cat.key === 'fees' ? <FeeIcon style={{ width: 20, height: 20 }} /> :
                     <FaqIcon style={{ width: 20, height: 20 }} />}
                  </span>
                    <h3 style={{ fontSize: '1.1rem', fontWeight: 800, color: '#111827' }}>
                      {cat.name} ({cat.count} tệp PDF)
                    </h3>
                  </div>
                  <span style={{ fontSize: '0.78rem', color: '#6B7280' }}>
                    {cat.description}
                  </span>
                </div>

                <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
                  {filteredItems.map((pdf) => renderPdfItemCard(pdf))}
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* MODAL: XEM TRỰC TIẾP TỆP PDF */}
      <Modal
        isOpen={Boolean(viewingPdf)}
        onClose={() => setViewingPdf(null)}
        title={viewingPdf ? viewingPdf.title : ''}
        maxWidth={960}
      >
        {viewingPdf && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 10, paddingBottom: 10, borderBottom: '1px solid #E2E8F0', fontSize: '0.82rem' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <FileTextIcon style={{ width: 16, height: 16, color: '#52525B' }} />
                <span>Tên file: <strong>{viewingPdf.filename}</strong></span>
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <a
                  href={viewingPdf.url}
                  target="_blank"
                  rel="noreferrer"
                  className="btn-outline"
                  style={{ fontSize: '0.75rem', padding: '4px 10px', textDecoration: 'none' }}
                >
                  <span>Mở tab mới</span>
                  <ChevronRight style={{ width: 12, height: 12 }} />
                </a>
                <a
                  href={viewingPdf.url}
                  download={viewingPdf.filename}
                  className="btn-primary"
                  style={{ fontSize: '0.75rem', padding: '4px 12px', textDecoration: 'none' }}
                >
                  <span>Tải tệp PDF</span>
                </a>
              </div>
            </div>

            <div style={{ height: '70vh', width: '100%', borderRadius: 8, overflow: 'hidden', border: '1px solid #CBD5E1', backgroundColor: '#525659' }}>
              <iframe
                src={viewingPdf.url}
                title={viewingPdf.title}
                style={{ width: '100%', height: '100%', border: 'none' }}
              />
            </div>
          </div>
        )}
      </Modal>

      {/* VEHICLE DETAIL MODAL */}
      <Modal
        isOpen={Boolean(selectedVehicle)}
        onClose={() => setSelectedVehicle(null)}
        title={selectedVehicle ? `${selectedVehicle.name} — Thông số chi tiết` : ''}
        maxWidth={760}
      >
        {selectedVehicle && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
            {selectedVehicle.image && (
              <div style={{ position: 'relative', borderRadius: 12, overflow: 'hidden', backgroundColor: '#0F1117' }}>
                <img
                  src={selectedVehicle.image}
                  alt={selectedVehicle.name}
                  style={{ width: '100%', maxHeight: 280, objectFit: 'cover', display: 'block' }}
                  onError={(e) => {
                    if (selectedVehicle.id) e.target.src = `/vehicles/${selectedVehicle.id}.svg`;
                  }}
                />
              </div>
            )}
            <div>
              <div style={{ display: 'flex', alignItems: 'baseline', gap: 10, flexWrap: 'wrap' }}>
                <h3 style={{ fontSize: '1.25rem', fontWeight: 700, color: '#0F172A' }}>{selectedVehicle.name}</h3>
                <span style={{ fontSize: '0.85rem', color: '#64748B' }}>{selectedVehicle.segment}</span>
              </div>
              {selectedVehicle.tagline && (
                <p style={{ fontSize: '0.88rem', color: '#475569', fontStyle: 'italic', marginTop: 4 }}>
                  "{selectedVehicle.tagline}"
                </p>
              )}
            </div>

            {/* Price section */}
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, padding: 14, backgroundColor: '#F8FAFC', borderRadius: 8, border: '1px solid #E2E8F0' }}>
              <div>
                <span style={{ fontSize: '0.72rem', color: '#64748B', display: 'block' }}>Giá bán kèm Pin:</span>
                <strong style={{ fontSize: '1rem', color: '#0F172A' }}>{selectedVehicle.price_battery_included || 'Đang cập nhật'}</strong>
              </div>
              <div>
                <span style={{ fontSize: '0.72rem', color: '#64748B', display: 'block' }}>Giá thuê Pin (nếu có):</span>
                <strong style={{ fontSize: '1rem', color: '#0F172A' }}>{selectedVehicle.price_battery_rental || 'Theo chính sách'}</strong>
              </div>
            </div>

            {/* Specifications Grid */}
            <div>
              <h4 style={{ fontSize: '0.92rem', fontWeight: 700, color: '#0F172A', marginBottom: 10 }}>
                <span style={{ display: "inline-flex", alignItems: "center", gap: 6 }}><SettingsIcon style={{ width: 14, height: 14 }} /> Thông số Vận hành & Pin:</span>
              </h4>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: 10 }}>
                <div style={{ padding: 12, backgroundColor: '#F8FAFC', borderRadius: 8, border: '1px solid #E2E8F0' }}>
                  <span style={{ fontSize: '0.72rem', color: '#64748B' }}>Quãng đường di chuyển:</span>
                  <div style={{ fontWeight: 600, fontSize: '0.88rem', color: '#0F172A' }}>{selectedVehicle.range}</div>
                </div>
                <div style={{ padding: 12, backgroundColor: '#F8FAFC', borderRadius: 8, border: '1px solid #E2E8F0' }}>
                  <span style={{ fontSize: '0.72rem', color: '#64748B' }}>Công suất tối đa:</span>
                  <div style={{ fontWeight: 600, fontSize: '0.88rem', color: '#0F172A' }}>{selectedVehicle.power}</div>
                </div>
                <div style={{ padding: 12, backgroundColor: '#F8FAFC', borderRadius: 8, border: '1px solid #E2E8F0' }}>
                  <span style={{ fontSize: '0.72rem', color: '#64748B' }}>Mô-men xoắn cực đại:</span>
                  <div style={{ fontWeight: 600, fontSize: '0.88rem', color: '#0F172A' }}>{selectedVehicle.torque}</div>
                </div>
                <div style={{ padding: 12, backgroundColor: '#F8FAFC', borderRadius: 8, border: '1px solid #E2E8F0' }}>
                  <span style={{ fontSize: '0.72rem', color: '#64748B' }}>Dung lượng pin:</span>
                  <div style={{ fontWeight: 600, fontSize: '0.88rem', color: '#0F172A' }}>{selectedVehicle.battery_capacity}</div>
                </div>
                <div style={{ padding: 12, backgroundColor: '#F8FAFC', borderRadius: 8, border: '1px solid #E2E8F0' }}>
                  <span style={{ fontSize: '0.72rem', color: '#64748B' }}>Thời gian sạc nhanh:</span>
                  <div style={{ fontWeight: 600, fontSize: '0.88rem', color: '#0F172A' }}>{selectedVehicle.charging_time}</div>
                </div>
                <div style={{ padding: 12, backgroundColor: '#F8FAFC', borderRadius: 8, border: '1px solid #E2E8F0' }}>
                  <span style={{ fontSize: '0.72rem', color: '#64748B' }}>Hệ dẫn động:</span>
                  <div style={{ fontWeight: 600, fontSize: '0.88rem', color: '#0F172A' }}>{selectedVehicle.drivetrain}</div>
                </div>
              </div>
            </div>

            {/* Dimensions & Chassis */}
            <div>
              <h4 style={{ fontSize: '0.92rem', fontWeight: 700, color: '#0F172A', marginBottom: 10 }}>
                <span style={{ display: "inline-flex", alignItems: "center", gap: 6 }}><RulerIcon style={{ width: 14, height: 14 }} /> Kích thước & Khung gầm:</span>
              </h4>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: 10 }}>
                <div style={{ padding: 12, backgroundColor: '#F8FAFC', borderRadius: 8, border: '1px solid #E2E8F0' }}>
                  <span style={{ fontSize: '0.72rem', color: '#64748B' }}>Kích thước (D x R x C):</span>
                  <div style={{ fontWeight: 600, fontSize: '0.88rem', color: '#0F172A' }}>{selectedVehicle.dimensions}</div>
                </div>
                <div style={{ padding: 12, backgroundColor: '#F8FAFC', borderRadius: 8, border: '1px solid #E2E8F0' }}>
                  <span style={{ fontSize: '0.72rem', color: '#64748B' }}>Chiều dài cơ sở:</span>
                  <div style={{ fontWeight: 600, fontSize: '0.88rem', color: '#0F172A' }}>{selectedVehicle.wheelbase}</div>
                </div>
                <div style={{ padding: 12, backgroundColor: '#F8FAFC', borderRadius: 8, border: '1px solid #E2E8F0' }}>
                  <span style={{ fontSize: '0.72rem', color: '#64748B' }}>Khoảng sáng gầm:</span>
                  <div style={{ fontWeight: 600, fontSize: '0.88rem', color: '#0F172A' }}>{selectedVehicle.ground_clearance}</div>
                </div>
                <div style={{ padding: 12, backgroundColor: '#F8FAFC', borderRadius: 8, border: '1px solid #E2E8F0' }}>
                  <span style={{ fontSize: '0.72rem', color: '#64748B' }}>Tốc độ tối đa:</span>
                  <div style={{ fontWeight: 600, fontSize: '0.88rem', color: '#0F172A' }}>{selectedVehicle.top_speed}</div>
                </div>
              </div>
            </div>

            {/* ADAS features */}
            {selectedVehicle.adas_features && selectedVehicle.adas_features.length > 0 && (
              <div>
                <h4 style={{ fontSize: '0.92rem', fontWeight: 700, color: '#0F172A', marginBottom: 10 }}>
                  <span style={{ display: "inline-flex", alignItems: "center", gap: 6 }}><ShieldCheckIcon style={{ width: 14, height: 14 }} /> Công nghệ An toàn & Hỗ trợ Lái (ADAS):</span>
                </h4>
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
                  {selectedVehicle.adas_features.map((item, idx) => (
                    <span
                      key={idx}
                      style={{
                        padding: '4px 10px',
                        borderRadius: 6,
                        backgroundColor: '#F1F5F9',
                        fontSize: '0.8rem',
                        color: '#1E293B',
                        border: '1px solid #E2E8F0',
                      }}
                    >
                      <CheckIcon style={{ width: 11, height: 11, display: "inline", verticalAlign: "-1px", marginRight: 4 }} />{item}
                    </span>
                  ))}
                </div>
              </div>
            )}

            {/* Highlights */}
            {selectedVehicle.highlights && selectedVehicle.highlights.length > 0 && (
              <div>
                <h4 style={{ fontSize: '0.92rem', fontWeight: 700, color: '#0F172A', marginBottom: 10 }}>
                  <span style={{ display: "inline-flex", alignItems: "center", gap: 6 }}><SparkleIcon style={{ width: 14, height: 14 }} /> Điểm nhấn tư vấn nổi bật:</span>
                </h4>
                <ul style={{ listStyle: 'none', paddingLeft: 0, display: 'flex', flexDirection: 'column', gap: 6 }}>
                  {selectedVehicle.highlights.map((h, idx) => (
                    <li key={idx} style={{ fontSize: '0.84rem', color: '#334155', display: 'flex', alignItems: 'flex-start', gap: 8 }}>
                      <span style={{ color: '#0284C7', fontWeight: 700 }}>•</span>
                      <span>{h}</span>
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {/* Actions footer */}
            <div style={{ borderTop: '1px solid #E2E8F0', paddingTop: 16, display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 10 }}>
              <span style={{ fontSize: '0.8rem', color: '#64748B' }}>
                Mã văn bản Corpus: <code>{selectedVehicle.document_id}</code>
              </span>
              <div style={{ display: 'flex', gap: 8 }}>
                {selectedVehicle.document_id && (
                  <button
                    className="btn-outline"
                    onClick={() => {
                      const docId = selectedVehicle.document_id;
                      const vName = selectedVehicle.name;
                      setSelectedVehicle(null);
                      handleOpenDocument(docId, vName);
                    }}
                    style={{ fontSize: '0.82rem', padding: '8px 14px' }}
                  >
                    <span>Xem tài liệu gốc Corpus</span>
                  </button>
                )}
                <button
                  className="btn-primary"
                  onClick={() => {
                    const vName = selectedVehicle.name;
                    setSelectedVehicle(null);
                    onOpenCopilotQuery && onOpenCopilotQuery(`Tư vấn thông số kỹ thuật và so sánh xe ${vName}`);
                  }}
                  style={{ fontSize: '0.82rem', padding: '8px 16px' }}
                >
                  <span>Hỏi kịch bản tư vấn với Copilot</span>
                  <SparkleIcon style={{ width: 14, height: 14 }} />
                </button>
              </div>
            </div>
          </div>
        )}
      </Modal>

      {/* DOCUMENT VIEWER MODAL (TEXT/JSON) */}
      <Modal
        isOpen={Boolean(selectedDocument)}
        onClose={() => setSelectedDocument(null)}
        title={selectedDocument ? selectedDocument.title : ''}
        maxWidth={780}
      >
        {selectedDocument && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 10, fontSize: '0.78rem', color: '#737373', borderBottom: '1px solid #F0F0EE', paddingBottom: 10, flexWrap: 'wrap' }}>
              <span>Mã văn bản: <strong>{selectedDocument.document_id}</strong></span>
              <span>•</span>
              <span>Ngày hiệu lực: <strong>{selectedDocument.effective_date}</strong></span>
              <span>•</span>
              <span>Dòng xe: <strong>{selectedDocument.product_model || 'ALL'}</strong></span>
              <span>•</span>
              <span>Trạng thái: <strong>{selectedDocument.status || 'Chưa xác định'}</strong></span>
            </div>

            <div
              style={{
                fontSize: '0.88rem',
                lineHeight: 1.6,
                color: '#222222',
                whiteSpace: 'pre-wrap',
                maxHeight: '60vh',
                overflowY: 'auto',
                backgroundColor: '#FAFAFA',
                padding: '16px 20px',
                borderRadius: 8,
                border: '1px solid #ECECE8',
              }}
            >
              {selectedDocument.content}
            </div>

            <div style={{ display: 'flex', justifyContent: 'flex-end', paddingTop: 10, borderTop: '1px solid #F0F0EE' }}>
              <button
                className="btn-primary"
                onClick={() => {
                  const docTitle = selectedDocument.title;
                  const docId = selectedDocument.document_id;
                  setSelectedDocument(null);
                  onOpenCopilotQuery && onOpenCopilotQuery(`Tư vấn và giải thích chi tiết nội dung tài liệu ${docTitle} (${docId})`);
                }}
                style={{ fontSize: '0.82rem', padding: '8px 16px' }}
              >
                <span>Hỏi Copilot về tài liệu này</span>
                <SparkleIcon style={{ width: 14, height: 14 }} />
              </button>
            </div>
          </div>
        )}
      </Modal>
    </div>
  );
}
