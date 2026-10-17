import { useEffect, useState } from 'react';
import { copilotApi } from '../../api/copilotApi';
import { BookIcon, CloseIcon } from '../common/Icons';

export function SourceViewerModal({ isOpen, onClose, citation, onOpenDocument }) {
  const [docData, setDocData] = useState(null);
  const [loadedKey, setLoadedKey] = useState(null);
  const [error, setError] = useState(null);
  const [showFull, setShowFull] = useState(false);

  const docKey = isOpen && citation?.document_id ? `${citation.document_id}_${citation.chunk_id || ''}` : null;
  const loading = Boolean(docKey && loadedKey !== docKey && !error);

  useEffect(() => {
    setDocData(null);
    setLoadedKey(null);
    setError(null);
    setShowFull(false);

    if (!docKey || !citation?.document_id) {
      return;
    }

    let isMounted = true;

    copilotApi
      .getSource(citation.document_id, citation.chunk_id)
      .then((data) => {
        if (isMounted) {
          setDocData(data);
          setLoadedKey(docKey);
        }
      })
      .catch((err) => {
        if (isMounted) {
          setError(err.message || 'Không thể tải chi tiết tài liệu');
          setLoadedKey(docKey);
        }
      });

    return () => {
      isMounted = false;
    };
  }, [docKey, citation?.document_id, citation?.chunk_id]);

  useEffect(() => {
    function handleKeyDown(e) {
      if (e.key === 'Escape' && isOpen) {
        onClose();
      }
    }
    if (isOpen) {
      document.body.style.overflow = 'hidden';
      window.addEventListener('keydown', handleKeyDown);
    }
    return () => {
      document.body.style.overflow = 'unset';
      window.removeEventListener('keydown', handleKeyDown);
    };
  }, [isOpen, onClose]);

  if (!isOpen || !citation) return null;

  const isCurrentDocLoaded = loadedKey === docKey;
  const currentDoc = isCurrentDocLoaded ? docData : null;
  const displayTitle = currentDoc?.title || citation.title || citation.document_id;
  const displayExcerpt = citation.excerpt || currentDoc?.chunk?.content;
  const version = currentDoc?.version || citation.version;
  const effectiveDate = currentDoc?.effective_date || citation.effective_from;

  return (
    <div
      style={{
        position: 'fixed',
        inset: 0,
        zIndex: 110,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        backgroundColor: 'rgba(0, 0, 0, 0.6)',
        backdropFilter: 'blur(3px)',
        padding: 16,
      }}
      onClick={onClose}
    >
      <div
        style={{
          width: '100%',
          maxWidth: 780,
          maxHeight: '88vh',
          backgroundColor: '#FFFFFF',
          borderRadius: 14,
          boxShadow: '0 20px 50px rgba(0, 0, 0, 0.25)',
          display: 'flex',
          flexDirection: 'column',
          overflow: 'hidden',
          animation: 'fadeIn 0.2s ease',
        }}
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div
          style={{
            padding: '16px 20px',
            borderBottom: '1px solid #E5E5E5',
            display: 'flex',
            alignItems: 'flex-start',
            justifyContent: 'space-between',
            gap: 12,
            backgroundColor: '#FAFAFA',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'flex-start', gap: 10 }}>
            <div
              style={{
                width: 34,
                height: 34,
                borderRadius: 8,
                backgroundColor: '#EFF6FF',
                color: '#1D4ED8',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                flexShrink: 0,
                marginTop: 2,
              }}
            >
              <BookIcon style={{ width: 18, height: 18 }} />
            </div>
            <div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
                <span
                  style={{
                    backgroundColor: '#1E40AF',
                    color: '#FFFFFF',
                    fontSize: '0.72rem',
                    fontWeight: 700,
                    padding: '2px 7px',
                    borderRadius: 4,
                  }}
                >
                  {citation.citation_id || 'Nguồn trích dẫn'}
                </span>
                {version && (
                  <span
                    style={{
                      fontSize: '0.72rem',
                      color: '#4B5563',
                      backgroundColor: '#E5E7EB',
                      padding: '2px 6px',
                      borderRadius: 4,
                    }}
                  >
                    Phiên bản: {version}
                  </span>
                )}
                {effectiveDate && (
                  <span
                    style={{
                      fontSize: '0.72rem',
                      color: '#065F46',
                      backgroundColor: '#D1FAE5',
                      padding: '2px 6px',
                      borderRadius: 4,
                    }}
                  >
                    Hiệu lực: {effectiveDate}
                  </span>
                )}
              </div>
              <h2
                style={{
                  fontSize: '1.05rem',
                  fontWeight: 700,
                  color: '#111827',
                  marginTop: 4,
                  lineHeight: 1.4,
                }}
              >
                {displayTitle}
              </h2>
            </div>
          </div>
          <button
            onClick={onClose}
            style={{
              padding: 6,
              borderRadius: 6,
              color: '#6B7280',
              backgroundColor: 'transparent',
              border: 'none',
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
            }}
            aria-label="Đóng"
          >
            <CloseIcon style={{ width: 20, height: 20 }} />
          </button>
        </div>

        {/* Body */}
        <div style={{ padding: '20px', overflowY: 'auto', flex: 1, display: 'flex', flexDirection: 'column', gap: 16 }}>
          {/* Highlighted Chunk Excerpt */}
          <div
            style={{
              borderRadius: 10,
              backgroundColor: '#FEF9C3',
              border: '1px solid #FDE047',
              padding: '14px 16px',
            }}
          >
            <div
              style={{
                fontSize: '0.8rem',
                fontWeight: 700,
                color: '#854D0E',
                marginBottom: 8,
                display: 'flex',
                alignItems: 'center',
                gap: 6,
              }}
            >
              <span>📌 Đoạn trích dẫn thực tế được Copilot đối chiếu:</span>
            </div>
            <div
              style={{
                fontSize: '0.875rem',
                color: '#1F2937',
                lineHeight: 1.6,
                whiteSpace: 'pre-wrap',
                fontFamily: 'inherit',
              }}
            >
              {displayExcerpt || (loading ? 'Đang tải dữ liệu trích dẫn...' : 'Không có trích đoạn ngắn')}
            </div>
          </div>

          {/* Full Content Toggle */}
          <div>
            <button
              onClick={() => setShowFull(!showFull)}
              style={{
                fontSize: '0.82rem',
                fontWeight: 600,
                color: '#2563EB',
                backgroundColor: 'transparent',
                border: 'none',
                cursor: 'pointer',
                display: 'inline-flex',
                alignItems: 'center',
                gap: 6,
                padding: '4px 0',
              }}
            >
              <span>{showFull ? '▼ Thu gọn toàn văn tài liệu' : '▶ Xem toàn văn tài liệu trong kho lưu trữ'}</span>
            </button>

            {showFull && (
              <div
                style={{
                  marginTop: 10,
                  padding: '14px 16px',
                  borderRadius: 8,
                  backgroundColor: '#F9FAFB',
                  border: '1px solid #E5E7EB',
                  maxHeight: 280,
                  overflowY: 'auto',
                }}
              >
                {loading && <div style={{ fontSize: '0.82rem', color: '#6B7280' }}>Đang tải văn bản...</div>}
                {error && <div style={{ fontSize: '0.82rem', color: '#DC2626' }}>{error}</div>}
                {docData?.content && (
                  <pre
                    style={{
                      fontSize: '0.82rem',
                      color: '#374151',
                      lineHeight: 1.6,
                      whiteSpace: 'pre-wrap',
                      fontFamily: 'monospace',
                    }}
                  >
                    {docData.content}
                  </pre>
                )}
              </div>
            )}
          </div>
        </div>

        {/* Footer */}
        <div
          style={{
            padding: '12px 20px',
            borderTop: '1px solid #E5E5E5',
            backgroundColor: '#F9FAFB',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
          }}
        >
          <span style={{ fontSize: '0.75rem', color: '#6B7280' }}>
            ID: {citation.document_id} {citation.chunk_id ? `• ${citation.chunk_id}` : ''}
          </span>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            {onOpenDocument && citation.document_id && (
              <button
                type="button"
                onClick={() => {
                  onClose();
                  onOpenDocument(citation.document_id);
                }}
                style={{
                  padding: '6px 12px',
                  borderRadius: 6,
                  backgroundColor: '#FFFFFF',
                  color: '#374151',
                  fontSize: '0.82rem',
                  fontWeight: 500,
                  border: '1px solid #D1D5DB',
                  cursor: 'pointer',
                }}
              >
                Mở trong Kho tài liệu ↗
              </button>
            )}
            <button
              onClick={onClose}
              style={{
                padding: '6px 14px',
                borderRadius: 6,
                backgroundColor: '#111827',
                color: '#FFFFFF',
                fontSize: '0.82rem',
                fontWeight: 600,
                border: 'none',
                cursor: 'pointer',
              }}
            >
              Đóng
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
