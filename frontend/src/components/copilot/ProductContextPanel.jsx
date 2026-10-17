import { useState } from 'react';
import { BookIcon, CopyIcon, CheckIcon, ChevronRight } from '../common/Icons';

export function ProductContextPanel({
  browseModel = null,
  resolvedModel = null,
  resolvedDate = '',
  originMessageId = null,
  insights = [],
  loading = false,
  error = null,
  onSelectBrowseModel,
  onFillDraft,
  onSwitchModel,
  onCitationClick,
  onCopy,
  copiedId,
  onComposeMessage,
  onRetryInsights,
}) {
  const [selectedBrowse, setSelectedBrowse] = useState(browseModel || 'VF 5');

  const vehicleCatalog = [
    { model: 'VF 3', segment: 'Mini e-SUV', highlight: 'Đô thị nhỏ gọn, giá dễ tiếp cận' },
    { model: 'VF 5', segment: 'A-SUV đô thị', highlight: 'Tiết kiệm, thực dụng, sạc nhanh' },
    { model: 'VF 6', segment: 'B-SUV gia đình', highlight: 'Không gian rộng rãi, công nghệ ADAS' },
    { model: 'VF 7', segment: 'C-SUV thể thao', highlight: 'Thiết kế phi thuyền, vận hành mạnh mẽ' },
    { model: 'VF 8', segment: 'D-SUV thông minh', highlight: 'Chuẩn an toàn cao cấp, 2 cầu AWD' },
    { model: 'VF 9', segment: 'E-SUV hạng sang', highlight: '7 chỗ/6 chỗ chủ tịch, tiện nghi đỉnh cao' },
  ];

  const currentActiveModel = resolvedModel || (insights.length > 0 ? insights[0]?.product_model : null);
  const isConsultationMode = Boolean(currentActiveModel);

  const handleSelectModel = (m) => {
    setSelectedBrowse(m);
    if (onSelectBrowseModel) {
      onSelectBrowseModel(m);
    }
  };

  const getTopics = (model) => [
    {
      id: 'price',
      label: '🏷️ Giá & phiên bản',
      query: `Bảng giá niêm yết và các phiên bản của ${model} hiện tại là bao nhiêu?`,
    },
    {
      id: 'highlights',
      label: '⭐ Điểm nổi bật',
      query: `Những điểm nổi bật và ưu thế cạnh tranh của ${model} để tư vấn cho khách hàng?`,
    },
    {
      id: 'policy',
      label: '📜 Chính sách & ưu đãi',
      query: `Chính sách ưu đãi, gói thuê/mua pin và trạm sạc mới nhất áp dụng cho ${model}?`,
    },
    {
      id: 'compare',
      label: '⚖️ So sánh xe',
      query: `So sánh ${model} với các đối thủ cùng phân khúc về thông số, trang bị và chi phí vận hành.`,
    },
    {
      id: 'pitch',
      label: '💬 Soạn tin cho khách',
      query: `Soạn tin nhắn tư vấn giới thiệu ${model} cho khách hàng quan tâm đến xe tiết kiệm chi phí.`,
    },
  ];

  return (
    <div
      className="card-white copilot-insights-card"
      style={{
        display: 'flex',
        flexDirection: 'column',
        height: '100%',
        minHeight: 0,
        padding: 0,
        overflow: 'hidden',
        backgroundColor: '#FFFFFF',
        borderRadius: 12,
        border: '1px solid #E5E7EB',
      }}
    >
      {/* HEADER */}
      <div
        style={{
          padding: '14px 18px',
          borderBottom: '1px solid #E5E5E5',
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          backgroundColor: '#FAFAFA',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <span style={{ fontSize: '1.05rem' }}>{isConsultationMode ? '✨' : '🚗'}</span>
          <div>
            <h3
              style={{
                fontSize: '0.88rem',
                fontWeight: 800,
                color: '#111827',
                margin: 0,
                letterSpacing: '-0.01em',
              }}
            >
              {isConsultationMode ? 'Bổ sung để tư vấn khách' : 'Bạn muốn tư vấn xe nào?'}
            </h3>
            <span style={{ fontSize: '0.7rem', color: '#6B7280' }}>
              {isConsultationMode
                ? 'Thông tin sản phẩm và chính sách theo ngày đối chiếu'
                : 'Chọn xe và chủ đề để bắt đầu chuẩn bị tư vấn'}
            </span>
          </div>
        </div>

        {isConsultationMode ? (
          <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            <span
              style={{
                padding: '3px 8px',
                borderRadius: 6,
                backgroundColor: '#111827',
                color: '#FFFFFF',
                fontSize: '0.74rem',
                fontWeight: 700,
              }}
            >
              {currentActiveModel}
            </span>
            {onSwitchModel && (
              <button
                type="button"
                onClick={onSwitchModel}
                style={{
                  padding: '3px 8px',
                  borderRadius: 6,
                  border: '1px solid #D1D5DB',
                  backgroundColor: '#FFFFFF',
                  color: '#4B5563',
                  fontSize: '0.7rem',
                  fontWeight: 600,
                  cursor: 'pointer',
                }}
                title="Chọn xe khác để tư vấn"
              >
                Đổi xe
              </button>
            )}
          </div>
        ) : (
          <span
            style={{
              padding: '3px 7px',
              borderRadius: 6,
              backgroundColor: '#EFF6FF',
              color: '#1D4ED8',
              fontSize: '0.7rem',
              fontWeight: 700,
            }}
          >
            Danh mục xe
          </span>
        )}
      </div>

      {/* BODY CONTENT */}
      <div
        style={{
          flex: 1,
          overflowY: 'auto',
          padding: '14px 16px',
          display: 'flex',
          flexDirection: 'column',
          gap: 14,
        }}
      >
        {isConsultationMode ? (
          /* ================= MODE 2: CONSULTATION COMPLEMENTARY INSIGHTS ================= */
          <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
            {/* Meta info bar */}
            <div
              style={{
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
                padding: '8px 10px',
                backgroundColor: '#F9FAFB',
                border: '1px solid #E5E7EB',
                borderRadius: 8,
                fontSize: '0.72rem',
                color: '#4B5563',
              }}
            >
              <span style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                <span>🎯</span>
                <strong>Ngữ cảnh:</strong> {currentActiveModel}
              </span>
              <span>
                {resolvedDate ? `Đối chiếu: ${resolvedDate}` : 'Theo tài liệu của phiên tư vấn'}
              </span>
            </div>

            {loading && (
              <div
                style={{
                  padding: '24px 16px',
                  textAlign: 'center',
                  color: '#6B7280',
                  fontSize: '0.8rem',
                }}
              >
                <div style={{ marginBottom: 8 }}>⚡ Đang đối chiếu tài liệu bổ sung...</div>
              </div>
            )}

            {error && (
              <div
                style={{
                  padding: '12px 14px',
                  backgroundColor: '#FEF2F2',
                  border: '1px solid #FECACA',
                  borderRadius: 8,
                  fontSize: '0.78rem',
                  color: '#991B1B',
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'center',
                }}
              >
                <span>Chưa tải được thông tin bổ sung.</span>
                {onRetryInsights && (
                  <button
                    type="button"
                    onClick={onRetryInsights}
                    style={{
                      background: 'none',
                      border: 'none',
                      color: '#DC2626',
                      fontWeight: 700,
                      cursor: 'pointer',
                    }}
                  >
                    Thử lại
                  </button>
                )}
              </div>
            )}

            {!loading && insights.length === 0 && (
              <div
                style={{
                  padding: '28px 16px',
                  textAlign: 'center',
                  backgroundColor: '#F9FAFB',
                  border: '1px dashed #D1D5DB',
                  borderRadius: 8,
                }}
              >
                <span style={{ fontSize: '1.4rem', display: 'block', marginBottom: 6 }}>✅</span>
                <p style={{ fontSize: '0.82rem', fontWeight: 700, color: '#374151', margin: '0 0 4px 0' }}>
                  Chưa có thông tin nổi bật bổ sung
                </p>
                <p style={{ fontSize: '0.75rem', color: '#6B7280', margin: 0 }}>
                  Bạn có thể hỏi thêm về thông số, trang bị hoặc chính sách của xe để đối chiếu tài liệu.
                </p>
              </div>
            )}

            {(loading ? [] : insights).map((insight, idx) => {
              const isPolicy = insight.category === 'policy';
              const copyKey = `card-${originMessageId || 'curr'}-${idx}`;
              const sourceTag = insight.citation?.title ? ` [Nguồn: ${insight.citation.title}]` : '';
              const fullCopyText = `${insight.title}: ${insight.summary}${
                insight.essential_conditions && !insight.summary.includes(insight.essential_conditions)
                  ? ` (Điều kiện: ${insight.essential_conditions})`
                  : ''
              }${sourceTag}`;

              return (
                <div
                  key={insight.insight_id || idx}
                  style={{
                    padding: '12px 14px',
                    backgroundColor: isPolicy ? '#F0FDF4' : '#FFFFFF',
                    border: `1px solid ${isPolicy ? '#86EFAC' : '#E2E8F0'}`,
                    borderLeft: `4px solid ${isPolicy ? '#166534' : '#2563EB'}`,
                    borderRadius: 8,
                    display: 'flex',
                    flexDirection: 'column',
                    gap: 8,
                    boxShadow: '0 1px 2px rgba(0, 0, 0, 0.03)',
                  }}
                >
                  {/* Category & Model Tags */}
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap' }}>
                      <span
                        style={{
                          padding: '2px 6px',
                          borderRadius: 4,
                          fontSize: '0.66rem',
                          fontWeight: 700,
                          backgroundColor: isPolicy ? '#DCFCE7' : '#EFF6FF',
                          color: isPolicy ? '#166534' : '#1D4ED8',
                        }}
                      >
                        {isPolicy ? '📜 Chính sách áp dụng' : '💡 Điểm nổi bật'}
                      </span>
                      <span
                        style={{
                          padding: '2px 6px',
                          borderRadius: 4,
                          fontSize: '0.66rem',
                          fontWeight: 600,
                          backgroundColor: '#111827',
                          color: '#FFFFFF',
                        }}
                      >
                        {insight.product_model === 'ALL' ? 'Tất cả xe' : insight.product_model}
                      </span>
                    </div>

                    {insight.applicability === 'conditional' && (
                      <span
                        style={{
                          fontSize: '0.66rem',
                          color: '#D97706',
                          backgroundColor: '#FEF3C7',
                          padding: '2px 6px',
                          borderRadius: 4,
                          fontWeight: 600,
                        }}
                      >
                        Cần đối chiếu điều kiện
                      </span>
                    )}
                  </div>

                  {/* Title & Concise Summary (1-3 sentences) */}
                  <div>
                    <h4
                      style={{
                        fontSize: '0.84rem',
                        fontWeight: 800,
                        color: '#111827',
                        margin: '0 0 4px 0',
                        lineHeight: 1.35,
                      }}
                    >
                      {insight.title}
                    </h4>
                    <p
                      style={{
                        fontSize: '0.78rem',
                        color: '#374151',
                        lineHeight: 1.5,
                        margin: 0,
                      }}
                    >
                      {insight.summary}
                    </p>
                  </div>

                  {isPolicy && insight.citation?.effective_from && (
                    <p style={{ margin: 0, fontSize: '0.7rem', color: '#4B5563' }}>
                      Hiệu lực từ {insight.citation.effective_from}
                      {insight.citation.effective_to ? ` đến ${insight.citation.effective_to}` : ''}
                    </p>
                  )}

                  {/* Clickable Source Provenance Pill */}
                  {insight.citation && onCitationClick && (
                    <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap', marginTop: 2 }}>
                      <button
                        type="button"
                        onClick={() => onCitationClick(insight.citation)}
                        style={{
                          display: 'inline-flex',
                          alignItems: 'center',
                          gap: 5,
                          padding: '3px 8px',
                          backgroundColor: '#F8FAFC',
                          border: '1px solid #CBD5E1',
                          borderRadius: 6,
                          fontSize: '0.68rem',
                          color: '#334155',
                          fontWeight: 600,
                          cursor: 'pointer',
                          maxWidth: '100%',
                          textAlign: 'left',
                          transition: 'background-color 0.15s ease, border-color 0.15s ease',
                        }}
                        onMouseEnter={(e) => {
                          e.currentTarget.style.backgroundColor = '#EFF6FF';
                          e.currentTarget.style.borderColor = '#93C5FD';
                        }}
                        onMouseLeave={(e) => {
                          e.currentTarget.style.backgroundColor = '#F8FAFC';
                          e.currentTarget.style.borderColor = '#CBD5E1';
                        }}
                        title={`Bấm để tra cứu trích đoạn gốc: ${insight.citation.title || insight.citation.document_id}`}
                      >
                        <BookIcon style={{ width: 11, height: 11, color: '#2563EB', flexShrink: 0 }} />
                        <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                          Nguồn: {insight.citation.title || insight.citation.document_id}
                        </span>
                        <span style={{ fontSize: '0.65rem', color: '#64748B' }}>↗</span>
                      </button>
                    </div>
                  )}

                  {/* Essential conditions (if present and not already in summary) */}
                  {insight.essential_conditions && !insight.summary.includes(insight.essential_conditions) && (
                    <div
                      style={{
                        padding: '5px 8px',
                        backgroundColor: '#FFFBEB',
                        borderRadius: 6,
                        border: '1px solid #FDE68A',
                        fontSize: '0.71rem',
                        color: '#92400E',
                        lineHeight: 1.35,
                      }}
                    >
                      <strong>Điều kiện áp dụng:</strong> {insight.essential_conditions}
                    </div>
                  )}

                  {/* Action buttons */}
                  <div
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'space-between',
                      paddingTop: 6,
                      borderTop: '1px solid #F3F4F6',
                    }}
                  >
                    <div style={{ display: 'flex', gap: 6 }}>
                      {/* 1. Copy button */}
                      <button
                        type="button"
                        onClick={() => onCopy && onCopy(copyKey, fullCopyText)}
                        style={{
                          padding: '4px 8px',
                          borderRadius: 5,
                          border: '1px solid #CBD5E1',
                          backgroundColor: '#FFFFFF',
                          fontSize: '0.72rem',
                          color: copiedId === copyKey ? '#166534' : '#334155',
                          fontWeight: 600,
                          cursor: 'pointer',
                          display: 'inline-flex',
                          alignItems: 'center',
                          gap: 3,
                        }}
                        title="Chép thông tin và điều kiện áp dụng"
                      >
                        {copiedId === copyKey ? (
                          <>
                            <CheckIcon style={{ width: 12, height: 12, color: '#166534' }} />
                            <span>Đã chép</span>
                          </>
                        ) : (
                          <>
                            <CopyIcon style={{ width: 12, height: 12 }} />
                            <span>Chép thông tin</span>
                          </>
                        )}
                      </button>

                      {/* 2. Compose draft query for customer */}
                      <button
                        type="button"
                        onClick={() => {
                          const draftPrompt = `Soạn tin nhắn gửi khách hàng về ${insight.title}: ${insight.summary}`;
                          if (onComposeMessage) {
                            onComposeMessage(draftPrompt);
                          } else if (onFillDraft) {
                            onFillDraft(draftPrompt);
                          }
                        }}
                        style={{
                          padding: '4px 8px',
                          borderRadius: 5,
                          border: '1px solid #CBD5E1',
                          backgroundColor: '#FFFFFF',
                          fontSize: '0.72rem',
                          color: '#1D4ED8',
                          fontWeight: 600,
                          cursor: 'pointer',
                        }}
                        title="Tạo yêu cầu soạn tin nhắn cho khách"
                      >
                        💬 Soạn tin cho khách
                      </button>
                    </div>

                    {/* 3. View Source modal */}
                    {insight.citation && onCitationClick && (
                      <button
                        type="button"
                        onClick={() => onCitationClick(insight.citation)}
                        style={{
                          padding: '4px 8px',
                          borderRadius: 5,
                          border: 'none',
                          backgroundColor: 'transparent',
                          fontSize: '0.72rem',
                          color: '#2563EB',
                          fontWeight: 600,
                          cursor: 'pointer',
                          display: 'inline-flex',
                          alignItems: 'center',
                          gap: 3,
                        }}
                        title="Xem trích đoạn tài liệu gốc"
                      >
                        <BookIcon style={{ width: 11, height: 11 }} />
                        <span>Xem nguồn gốc</span>
                      </button>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        ) : (
          /* ================= MODE 1: BEFORE PRODUCT QUESTION (BROWSER / PICKER) ================= */
          <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
            <div>
              <span
                style={{
                  fontSize: '0.72rem',
                  fontWeight: 700,
                  color: '#4B5563',
                  textTransform: 'uppercase',
                  letterSpacing: '0.04em',
                  display: 'block',
                  marginBottom: 8,
                }}
              >
                1. Chọn xe đang quan tâm
              </span>
              <div
                style={{
                  display: 'grid',
                  gridTemplateColumns: 'repeat(3, 1fr)',
                  gap: 8,
                }}
              >
                {vehicleCatalog.map((v) => {
                  const isSelected = selectedBrowse === v.model;
                  return (
                    <button
                      key={v.model}
                      type="button"
                      onClick={() => handleSelectModel(v.model)}
                      style={{
                        padding: '10px 8px',
                        borderRadius: 8,
                        border: isSelected ? '2px solid #1D4ED8' : '1px solid #E5E7EB',
                        backgroundColor: isSelected ? '#EFF6FF' : '#F9FAFB',
                        display: 'flex',
                        flexDirection: 'column',
                        alignItems: 'center',
                        gap: 2,
                        cursor: 'pointer',
                        transition: 'all 0.15s ease',
                      }}
                    >
                      <span
                        style={{
                          fontSize: '0.88rem',
                          fontWeight: 800,
                          color: isSelected ? '#1D4ED8' : '#111827',
                        }}
                      >
                        {v.model}
                      </span>
                      <span style={{ fontSize: '0.66rem', color: '#6B7280' }}>
                        {v.segment}
                      </span>
                    </button>
                  );
                })}
              </div>
            </div>

            {/* Selected model details & topics */}
            {selectedBrowse && (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
                <div
                  style={{
                    padding: '10px 12px',
                    borderRadius: 8,
                    backgroundColor: '#F0F9FF',
                    border: '1px solid #BAE6FD',
                  }}
                >
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <span style={{ fontSize: '0.86rem', fontWeight: 800, color: '#0369A1' }}>
                      {selectedBrowse}
                    </span>
                    <span style={{ fontSize: '0.72rem', color: '#0284C7', fontWeight: 600 }}>
                      Ngữ cảnh chuẩn bị tư vấn
                    </span>
                  </div>
                  <p style={{ fontSize: '0.74rem', color: '#334155', margin: '4px 0 0 0' }}>
                    {vehicleCatalog.find((v) => v.model === selectedBrowse)?.highlight}
                  </p>
                </div>

                <div>
                  <span
                    style={{
                      fontSize: '0.72rem',
                      fontWeight: 700,
                      color: '#4B5563',
                      textTransform: 'uppercase',
                      letterSpacing: '0.04em',
                      display: 'block',
                      marginBottom: 8,
                    }}
                  >
                    2. Chọn chủ đề câu hỏi
                  </span>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                    {getTopics(selectedBrowse).map((topic) => (
                      <button
                        key={topic.id}
                        type="button"
                        onClick={() => onFillDraft && onFillDraft(topic.query)}
                        style={{
                          width: '100%',
                          textAlign: 'left',
                          padding: '9px 12px',
                          borderRadius: 6,
                          border: '1px solid #E5E7EB',
                          backgroundColor: '#FFFFFF',
                          fontSize: '0.78rem',
                          color: '#1F2937',
                          fontWeight: 600,
                          cursor: 'pointer',
                          display: 'flex',
                          alignItems: 'center',
                          justifyContent: 'space-between',
                          transition: 'all 0.15s ease',
                        }}
                        onMouseEnter={(e) => {
                          e.currentTarget.style.backgroundColor = '#EFF6FF';
                          e.currentTarget.style.borderColor = '#93C5FD';
                        }}
                        onMouseLeave={(e) => {
                          e.currentTarget.style.backgroundColor = '#FFFFFF';
                          e.currentTarget.style.borderColor = '#E5E7EB';
                        }}
                        title="Điền câu hỏi mẫu vào ô nhập liệu"
                      >
                        <span>{topic.label}</span>
                        <ChevronRight style={{ width: 12, height: 12, color: '#9CA3AF' }} />
                      </button>
                    ))}
                  </div>
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
