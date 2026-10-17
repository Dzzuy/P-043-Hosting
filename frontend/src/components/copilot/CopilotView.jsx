import { useState, useRef, useEffect, useCallback } from 'react';
import {
  RefreshIcon,
  CopyIcon,
  SendIcon,
  ChevronRight,
  BookIcon,
  CheckIcon,

  ChatIcon,
  TrashIcon,

  ArrowRight,

} from '../common/Icons';
import { CopilotLogo } from '../common/CopilotLogo';
import { Badge } from '../common/Badge';
import { Modal } from '../common/Modal';
import { copilotApi } from '../../api/copilotApi';
import { ProductContextPanel } from './ProductContextPanel';
import { createId, getCurrentTimeString } from '../../lib/id';
import { copilotReason } from '../../lib/copilotStatus';
import { SourceViewerModal } from './SourceViewerModal';
import { CustomerSalesCopilotView } from './CustomerSalesCopilotView';
import { CopilotWorkspace } from './agenda/CopilotWorkspace';

const STORAGE_KEY_PREFIX = 'vinfast_copilot_chat_';

export function CopilotView(props) {
  return import.meta.env.VITE_STANDALONE_COPILOT_ENABLED === 'true'
    ? <LegacyCopilotView {...props} />
    : <CopilotWorkspace key={props.currentUser?.user_id} currentUser={props.currentUser} />;
}

import { renderMarkdownWithCitations } from './markdownRenderer';


function LegacyCopilotView({ onOpenDocument, initialQuery = '', currentUser = null }) {
  const [filterDomain, setFilterDomain] = useState('all');
  const [inputDraft, setInputDraft] = useState({ initialQuery, value: initialQuery || '' });
  const inputMessage = inputDraft.initialQuery === initialQuery ? inputDraft.value : initialQuery || '';
  const setInputMessage = (value) => setInputDraft({ initialQuery, value });

  const storageKey = `${STORAGE_KEY_PREFIX}${currentUser?.username || 'advisor'}`;

  // Top Tabs Mode: 'customer_sales' (Tab 2 - Chức năng mới) vs 'product_knowledge' (Tab 1 - Tra cứu hiện tại)
  const [copilotMode, setCopilotMode] = useState('customer_sales');

  const [loading, setLoading] = useState(false);
  const [streamStatus, setStreamStatus] = useState('');
  const [error, setError] = useState('');
  const [copiedId, setCopiedId] = useState(null);

  const [customerContext, setCustomerContext] = useState('');
  const [targetDate, setTargetDate] = useState('');
  const [activeCitation, setActiveCitation] = useState(null);

  // Model browsing vs Resolved consultation context
  const [browseModel, setBrowseModel] = useState(null);
  const [resolvedContext, setResolvedContext] = useState({
    model: null,
    date: null,
    originMessageId: null,
    insights: [],
  });

  const sessionIdRef = useRef(localStorage.getItem('copilot_active_session_id') || null);
  const [currentSessionId, setCurrentSessionId] = useState(() => localStorage.getItem('copilot_active_session_id') || null);
  const [sessions, setSessions] = useState([]);
  const [showSidebar, setShowSidebar] = useState(true);

  const [messages, setMessages] = useState(() => {
    try {
      const saved = JSON.parse(localStorage.getItem(storageKey) || 'null');
      if (Array.isArray(saved) && saved.length > 0) return saved;
    } catch {
      // Ignore invalid cached messages and start a new conversation.
    }
    return [
    {
      id: 'msg-welcome',
      role: 'assistant',
      time: getCurrentTimeString(),
      content:
        'Chào bạn! Tôi có thể giúp chuẩn bị cuộc gọi, so sánh xe và xử lý những băn khoăn của khách dựa trên tài liệu. Bạn có thể thêm ghi chú về nhu cầu khách hoặc chọn dòng xe bên phải để tôi đề xuất nội dung tư vấn phù hợp.',
      talking_points: [],
      citations: [],
    },
    ];
  });

  const [selectedCitationDoc, setSelectedCitationDoc] = useState(null);
  const [citationLoading, setCitationLoading] = useState(false);

  const handleOpenCitation = async (documentId) => {
    setCitationLoading(true);
    try {
      const doc = await copilotApi.getSource(documentId);
      setSelectedCitationDoc(doc);
    } catch {
      setSelectedCitationDoc({
        document_id: documentId,
        title: `Tài liệu: ${documentId}`,
        content: 'Không thể tải nội dung chi tiết của tài liệu này từ máy chủ.',
      });
    } finally {
      setCitationLoading(false);
    }
  };



  useEffect(() => {
    try {
      localStorage.setItem(storageKey, JSON.stringify(messages));
    } catch {
      // ignore
    }
  }, [messages, storageKey]);


  const chatScrollContainerRef = useRef(null);
  const isNearBottomRef = useRef(true);
  const textareaRef = useRef(null);


  const filterChips = [
    { id: 'all', label: 'Tất cả lĩnh vực' },
    { id: 'specs', label: 'Thông số & Công nghệ' },
    { id: 'policy', label: 'Chính sách & Ưu đãi' },
    { id: 'charging', label: 'Pin & Trạm sạc V-GREEN' },
    { id: 'competitor', label: 'So sánh đối thủ' },
  ];

  const handleScroll = useCallback(() => {
    const el = chatScrollContainerRef.current;
    if (!el) return;
    const distanceToBottom = el.scrollHeight - el.scrollTop - el.clientHeight;
    isNearBottomRef.current = distanceToBottom < 140;
  }, []);

  const scrollToBottomIfNeeded = useCallback(() => {
    if (isNearBottomRef.current) {
      const container = chatScrollContainerRef.current;
      if (container) container.scrollTop = container.scrollHeight;
    }
  }, []);



  useEffect(() => {
    scrollToBottomIfNeeded();
  }, [messages, loading, scrollToBottomIfNeeded]);

  const fetchSessions = async () => {
    try {
      const data = await copilotApi.getSessions();
      setSessions(Array.isArray(data) ? data : []);
    } catch (e) {
      console.warn('Failed to fetch sessions', e);
    }
  };

  const loadSession = async (sessionId) => {
    if (!sessionId || loading) return;
    setLoading(true);
    setError('');
    try {
      const data = await copilotApi.getSessionDetail(sessionId);
      if (data && data.messages && data.messages.length > 0) {
        setMessages(data.messages);
        setCustomerContext(data.customer_context || '');
        sessionIdRef.current = sessionId;
        setCurrentSessionId(sessionId);
        localStorage.setItem('copilot_active_session_id', sessionId);

        const lastAnswer = [...data.messages].reverse().find((message) => message.role === 'assistant');
        const savedInsights = lastAnswer?.product_insights || [];
        const models = [...new Set(savedInsights.map((item) => item.product_model).filter((model) => model && model !== 'ALL'))];
        setResolvedContext({ model: models.join(' / ') || (savedInsights.length ? 'VinFast' : null),
          date: lastAnswer?.insight_date || '', originMessageId: lastAnswer?.id, insights: savedInsights });
      }
    } catch (err) {
      console.warn('Failed to load session', err);
      if (err.status === 404) {
        localStorage.removeItem('copilot_active_session_id');
        sessionIdRef.current = null;
        setCurrentSessionId(null);
        setResolvedContext({ model: null, date: null, originMessageId: null, insights: [] });
      }
    } finally {
      setLoading(false);
    }
  };

  // New Chat: Resets active conversation in UI without deleting historical session on server
  const handleNewChat = () => {
    sessionIdRef.current = null;
    setCurrentSessionId(null);
    localStorage.removeItem('copilot_active_session_id');
    setCustomerContext('');
    setTargetDate('');
    setInputMessage('');
    setError('');
    setBrowseModel(null);
    setResolvedContext({ model: null, date: null, originMessageId: null, insights: [] });
    setMessages([
      {
        id: createId('msg-welcome'),
        role: 'assistant',
        time: getCurrentTimeString(),
        content:
          'Chào bạn! Tôi có thể giúp chuẩn bị cuộc gọi, so sánh xe và xử lý những băn khoăn của khách dựa trên tài liệu. Bạn có thể thêm ghi chú về nhu cầu khách hoặc chọn dòng xe bên phải để tôi đề xuất nội dung tư vấn phù hợp.',
        talking_points: [],
        citations: [],
      },
    ]);
  };

  // Explicit session deletion on server via trash icon
  const handleDeleteSession = async (sessionId, e) => {
    e.stopPropagation();
    try {
      await copilotApi.deleteSession(sessionId);
      if (currentSessionId === sessionId) {
        handleNewChat();
      }
      fetchSessions();
    } catch (err) {
      console.warn('Failed to delete session', err);
    }
  };

  useEffect(() => {
    let isMounted = true;
    const initSessions = async () => {
      try {
        const data = await copilotApi.getSessions();
        if (isMounted) {
          setSessions(Array.isArray(data) ? data : []);
        }
      } catch (e) {
        console.warn('Failed to fetch sessions', e);
      }
      const savedSessionId = localStorage.getItem('copilot_active_session_id');
      if (savedSessionId) {
        try {
          const detail = await copilotApi.getSessionDetail(savedSessionId);
          if (isMounted && detail && detail.messages && detail.messages.length > 0) {
            setMessages(detail.messages);
            const lastAnswer = [...detail.messages].reverse().find((message) => message.role === 'assistant');
            const savedInsights = lastAnswer?.product_insights || [];
            const savedModels = [...new Set(savedInsights.map((item) => item.product_model).filter((model) => model && model !== 'ALL'))];
            setResolvedContext({ model: savedModels.join(' / ') || (savedInsights.length ? 'VinFast' : null),
              date: lastAnswer?.insight_date || '', originMessageId: lastAnswer?.id, insights: savedInsights });
            setCustomerContext(detail.customer_context || '');
            sessionIdRef.current = savedSessionId;
            setCurrentSessionId(savedSessionId);
          }
        } catch (err) {
          if (err.status === 404) {
            localStorage.removeItem('copilot_active_session_id');
          }
        }
      }
    };
    initSessions();
    return () => {
      isMounted = false;
    };
  }, []);

  const handleCopy = async (id, text) => {
    try {
      await navigator.clipboard?.writeText(text);
      setCopiedId(id);
      setTimeout(() => setCopiedId(null), 2000);
    } catch (err) {
      console.warn('Clipboard write failed', err);
    }
  };

  const handleFillDraft = (text) => {
    setInputMessage(text);
    if (textareaRef.current) {
      textareaRef.current.focus({ preventScroll: true });
    }
  };

  const handleSend = async (textToSend) => {
    const queryText = (textToSend || inputMessage).trim();
    if (!queryText || loading) return;

    const draftBackup = queryText;
    const userMsg = {
      id: createId('usr'),
      role: 'user',
      time: getCurrentTimeString(),
      content: queryText,
    };

    const tempAiId = createId('ai');
    let accumulatedText = '';

    setMessages((prev) => [...prev, userMsg]);
    setInputMessage('');
    setLoading(true);
    setStreamStatus('Đang phân tích câu hỏi & đối chiếu ngữ cảnh...');
    setError('');
    isNearBottomRef.current = true;

    try {
      await copilotApi.queryStream(
        {
          query: queryText,
          session_id: sessionIdRef.current,
          customer_context: customerContext,
          domain: filterDomain,
          target_date: targetDate || undefined,
        },
        {
          onStatus: (data) => {
            if (data?.text) setStreamStatus(data.text);
          },
          onDelta: (data) => {
            if (data?.text) {
              accumulatedText += data.text;
              setMessages((prev) => {
                const existing = prev.find((m) => m.id === tempAiId);
                if (existing) {
                  return prev.map((m) => (m.id === tempAiId ? { ...m, content: accumulatedText } : m));
                }
                return [
                  ...prev,
                  {
                    id: tempAiId,
                    role: 'assistant',
                    time: getCurrentTimeString(),
                    content: accumulatedText,
                    citations: [],
                    product_insights: [],
                    talking_points: [],
                    status: 'streaming',
                  },
                ];
              });
            }
          },
          onFinal: (response) => {
            if (!response.answer && !accumulatedText) {
              throw new Error('Copilot chưa trả lời được câu hỏi này.');
            }
            if (response.session_id) {
              sessionIdRef.current = response.session_id;
              setCurrentSessionId(response.session_id);
              localStorage.setItem('copilot_active_session_id', response.session_id);
              fetchSessions();
            }

            const responseInsights = response.product_insights || [];
            const models = [...new Set(responseInsights.map((item) => item.product_model).filter((model) => model && model !== 'ALL'))];
            setResolvedContext({
              model: models.join(' / ') || (responseInsights.length ? 'VinFast' : null),
              date: targetDate || new Date().toLocaleDateString('en-CA', { timeZone: 'Asia/Ho_Chi_Minh' }),
              originMessageId: tempAiId,
              insights: responseInsights,
            });

            const finalAiMsg = {
              id: tempAiId,
              role: 'assistant',
              time: getCurrentTimeString(),
              content: response.answer || accumulatedText,
              citations: response.citations || [],
              product_insights: response.product_insights || [],
              insight_date: targetDate || new Date().toLocaleDateString('en-CA', { timeZone: 'Asia/Ho_Chi_Minh' }),
              talking_points: response.talking_points || [],
              status: response.status || 'answered',
              reason_code: response.reason_code,
              missing_information: response.missing_information || [],
              sales_actions: response.sales_actions || [],
              suggested_next_question: response.suggested_next_question,
            };

            setMessages((prev) => {
              const hasPlaceholder = prev.some((m) => m.id === tempAiId);
              if (hasPlaceholder) {
                return prev.map((m) => (m.id === tempAiId ? finalAiMsg : m));
              }
              return [...prev, finalAiMsg];
            });
          },
          onError: (streamErr) => {
            console.warn('Stream error occurred:', streamErr);
          },
        }
      );
    } catch (requestError) {
      console.warn('Copilot query error:', requestError);
      const errText = requestError.message || 'Dịch vụ tra cứu tạm thời không khả dụng. Vui lòng thử lại sau.';
      setError(errText);
      setInputMessage(draftBackup); // Retain user's draft on failure so they can retry without losing input!

      setMessages((prev) => {
        const hasPlaceholder = prev.some((m) => m.id === tempAiId);
        const errMsg = {
          id: tempAiId,
          role: 'assistant',
          time: getCurrentTimeString(),
          content: `⚠️ **Không thể hoàn tất câu trả lời:**\n\n${errText}`,
          status: 'refused',
          citations: [],
          talking_points: [],
        };
        if (hasPlaceholder) {
          return prev.map((m) => (m.id === tempAiId ? errMsg : m));
        }
        return [...prev, errMsg];
      });
    } finally {
      setLoading(false);
      setStreamStatus('');
    }
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 10, height: '100%', minHeight: 0, flex: 1 }}>
      {/* 2 TOP TABS NAVIGATION */}
      <div
        style={{
          display: 'flex',
          gap: 8,
          padding: '5px',
          backgroundColor: '#E2E8F0',
          borderRadius: 10,
          width: 'fit-content',
          flexShrink: 0,
        }}
      >
        <button
          type="button"
          onClick={() => setCopilotMode('customer_sales')}
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 8,
            padding: '7px 16px',
            borderRadius: 8,
            border: 'none',
            fontSize: '0.86rem',
            fontWeight: copilotMode === 'customer_sales' ? 700 : 500,
            backgroundColor: copilotMode === 'customer_sales' ? '#FFFFFF' : 'transparent',
            color: copilotMode === 'customer_sales' ? '#1D4ED8' : '#475569',
            boxShadow: copilotMode === 'customer_sales' ? '0 1px 3px rgba(0,0,0,0.1)' : 'none',
            cursor: 'pointer',
            transition: 'all 0.15s ease',
          }}
        >
          <span>🤝 Trợ lý bán hàng theo khách hàng</span>
          <span style={{ fontSize: '0.7rem', backgroundColor: '#FEF3C7', color: '#92400E', padding: '1px 6px', borderRadius: 4, fontWeight: 700 }}>
            Mới
          </span>
        </button>

        <button
          type="button"
          onClick={() => setCopilotMode('product_knowledge')}
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 8,
            padding: '7px 16px',
            borderRadius: 8,
            border: 'none',
            fontSize: '0.86rem',
            fontWeight: copilotMode === 'product_knowledge' ? 700 : 500,
            backgroundColor: copilotMode === 'product_knowledge' ? '#FFFFFF' : 'transparent',
            color: copilotMode === 'product_knowledge' ? '#1D4ED8' : '#475569',
            boxShadow: copilotMode === 'product_knowledge' ? '0 1px 3px rgba(0,0,0,0.1)' : 'none',
            cursor: 'pointer',
            transition: 'all 0.15s ease',
          }}
        >
          <span>📚 Tra cứu & Hỏi đáp xe</span>
          <Badge variant="default" style={{ fontSize: '0.7rem', padding: '1px 6px' }}>RAG</Badge>
        </button>
      </div>

      {/* TAB 2: CUSTOMER SALES COPILOT */}
      {copilotMode === 'customer_sales' && (
        <div style={{ flex: 1, minHeight: 0, height: '100%', display: 'flex', flexDirection: 'column' }}>
          <CustomerSalesCopilotView
            currentUser={currentUser}
            onOpenKnowledgeQuery={(q) => {
              setFilterDomain('all');
              setCustomerContext('');
              setCopilotMode('product_knowledge');
              handleSend(q);
            }}
            onOpenDocument={onOpenDocument}
          />
        </div>
      )}

      {/* TAB 1: PRODUCT KNOWLEDGE COPILOT (EXISTING) */}
      <div style={{ display: copilotMode === 'product_knowledge' ? 'block' : 'none', flex: 1, minHeight: 0, height: '100%' }}>
        <div className={`copilot-grid-layout${showSidebar ? ' copilot-with-history' : ''}`}>
      {/* SESSIONS SIDEBAR */}
      {showSidebar && (
        <div
          className="card-white"
          style={{
            display: 'flex',
            flexDirection: 'column',
            height: '100%',
            minHeight: 0,
            padding: 0,
            overflow: 'hidden',
          }}
        >
          <div
            style={{
              padding: '16px 18px',
              borderBottom: '1px solid #E5E5E5',
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
              backgroundColor: '#FFFFFF',
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, fontWeight: 700, fontSize: '0.92rem', color: '#111827' }}>
              <ChatIcon style={{ width: 16, height: 16, color: '#2563EB' }} />
              <span>Lịch sử tư vấn</span>
            </div>
            <span
              style={{
                fontSize: '0.72rem',
                color: '#6B7280',
                backgroundColor: '#F3F4F6',
                padding: '2px 7px',
                borderRadius: 10,
                fontWeight: 600,
              }}
            >
              {sessions.length}
            </span>
          </div>

          <div style={{ padding: '12px 14px', borderBottom: '1px solid #F3F4F6' }}>
            <button
              type="button"
              onClick={handleNewChat}
              disabled={loading}
              style={{
                width: '100%',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                gap: 6,
                padding: '9px 12px',
                backgroundColor: '#1D4ED8',
                color: '#FFFFFF',
                border: 'none',
                borderRadius: 8,
                fontSize: '0.82rem',
                fontWeight: 600,
                cursor: 'pointer',
                transition: 'background-color 0.15s ease',
              }}
            >
              <span>＋ Cuộc trò chuyện mới</span>
            </button>
          </div>

          <div
            style={{
              flex: 1,
              overflowY: 'auto',
              padding: '8px 10px',
              display: 'flex',
              flexDirection: 'column',
              gap: 6,
            }}
          >
            {sessions.length === 0 ? (
              <div style={{ padding: '32px 12px', textAlign: 'center', color: '#9CA3AF', fontSize: '0.8rem' }}>
                Chưa có cuộc trò chuyện nào được lưu.
              </div>
            ) : (
              sessions.map((sess) => {
                const isActive = sess.session_id === currentSessionId;
                return (
                  <div
                    key={sess.session_id}
                    onClick={() => loadSession(sess.session_id)}
                    style={{
                      padding: '10px 12px',
                      borderRadius: 8,
                      cursor: 'pointer',
                      border: isActive ? '1px solid #3B82F6' : '1px solid #E5E7EB',
                      backgroundColor: isActive ? '#EFF6FF' : '#FAFAFA',
                      display: 'flex',
                      flexDirection: 'column',
                      gap: 4,
                      transition: 'all 0.15s ease',
                    }}
                  >
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 6 }}>
                      <span
                        style={{
                          fontSize: '0.82rem',
                          fontWeight: isActive ? 700 : 500,
                          color: isActive ? '#1D4ED8' : '#1F2937',
                          overflow: 'hidden',
                          textOverflow: 'ellipsis',
                          whiteSpace: 'nowrap',
                          flex: 1,
                        }}
                        title={sess.title}
                      >
                        {sess.title || 'Cuộc trò chuyện'}
                      </span>
                      <button
                        type="button"
                        onClick={(e) => handleDeleteSession(sess.session_id, e)}
                        style={{
                          background: 'none',
                          border: 'none',
                          color: '#9CA3AF',
                          cursor: 'pointer',
                          padding: 2,
                          display: 'flex',
                          alignItems: 'center',
                        }}
                        title="Xóa phiên này"
                      >
                        <TrashIcon style={{ width: 13, height: 13 }} />
                      </button>
                    </div>
                    <div
                      style={{
                        display: 'flex',
                        justifyContent: 'space-between',
                        alignItems: 'center',
                        fontSize: '0.72rem',
                        color: '#9CA3AF',
                      }}
                    >
                      <span>{sess.message_count ? `${sess.message_count} tin nhắn` : ''}</span>
                      <span>{sess.updated_at ? new Date(sess.updated_at).toLocaleDateString('vi-VN') : ''}</span>
                    </div>
                  </div>
                );
              })
            )}
          </div>
        </div>
      )}

      {/* LEFT MAIN CHAT CARD */}
      <div
        className="card-white copilot-chat-card"
        style={{
          display: 'flex',
          flexDirection: 'column',
          height: '100%',
          minHeight: 0,
          padding: 0,
          overflow: 'hidden',
        }}
      >
        {/* HEADER */}
        <div
          style={{
            padding: '18px 24px',
            borderBottom: '1px solid #E5E5E5',
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            backgroundColor: '#FFFFFF',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
            <button
              type="button"
              onClick={() => setShowSidebar((prev) => !prev)}
              className="btn-ghost"
              style={{
                padding: '6px 8px',
                fontSize: '0.78rem',
                color: '#4B5563',
                display: 'flex',
                alignItems: 'center',
                gap: 4,
                borderRadius: 6,
              }}
              title={showSidebar ? 'Thu gọn lịch sử' : 'Hiện lịch sử'}
            >
              <ChatIcon style={{ width: 15, height: 15 }} />
              <span>{showSidebar ? 'Ẩn lịch sử' : 'Lịch sử'}</span>
            </button>
            <div className="copilot-chat-mark">
              <CopilotLogo style={{ width: 23, height: 23 }} />
            </div>

            <div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <h2 className="copilot-chat-title">
                  VinFast AI Copilot
                </h2>
                <Badge variant="default" className="copilot-grounded-badge">
                  <span className="copilot-grounded-dot" />
                  RAG Grounded
                </Badge>
                <Badge variant="default" style={{ backgroundColor: '#F4F4F2', border: '1px solid #E0E0DD' }}>
                  <span
                    style={{
                      display: 'inline-block',
                      width: 6,
                      height: 6,
                      borderRadius: '50%',
                      backgroundColor: '#166534',
                      marginRight: 4,
                    }}
                  />
                  Trợ lý sales
                </Badge>
              </div>
              <p className="copilot-chat-subtitle">
                Chuẩn bị tư vấn, đối chiếu thông số kỹ thuật &amp; chính sách bán hàng 2026
              </p>
            </div>
          </div>

          <button
            onClick={handleNewChat}
            disabled={loading}
            className="copilot-reset-button"
            title="Bắt đầu cuộc trò chuyện mới"
          >
            <RefreshIcon style={{ width: 14, height: 14 }} />
            <span>Làm mới phiên chat</span>
          </button>
        </div>


        {/* DOMAIN FILTER CHIPS */}
        <div
          style={{
            padding: '10px 24px',
            borderBottom: '1px solid #F0F0EE',
            display: 'flex',
            gap: 8,
            overflowX: 'auto',
            backgroundColor: '#FAFAFA',
          }}
        >
          {filterChips.map((chip) => (
            <button
              key={chip.id}
              className={`chip ${filterDomain === chip.id ? 'active' : ''}`}
              onClick={() => setFilterDomain(chip.id)}
            >
              {chip.label}
            </button>
          ))}
        </div>

        <details style={{ padding: '10px 24px', borderBottom: '1px solid #F0F0EE' }}>
          <summary style={{ cursor: 'pointer', fontSize: '0.82rem', fontWeight: 600, color: '#374151' }}>
            Nhu cầu khách và ngày đối chiếu
          </summary>
          <textarea
            aria-label="Ghi chú nhu cầu khách"
            value={customerContext}
            onChange={(event) => setCustomerContext(event.target.value)}
            maxLength={6000}
            disabled={loading}
            placeholder="Ví dụ: Khách cân nhắc VF 5 và VF 6, có chỗ đỗ riêng, còn lo chi phí sử dụng pin."
            style={{
              width: '100%',
              minHeight: 70,
              marginTop: 8,
              padding: 10,
              border: '1px solid #E5E5E5',
              borderRadius: 8,
              fontSize: '0.85rem',
            }}
          />
          <label style={{ display: 'block', marginTop: 8, fontSize: '0.8rem', color: '#4B5563' }}>
            Ngày đối chiếu tài liệu (để trống để dùng ngày hiện tại):
            <input
              type="date"
              value={targetDate}
              onChange={(event) => setTargetDate(event.target.value)}
              disabled={loading}
              style={{ display: 'block', marginTop: 6, padding: '4px 8px', borderRadius: 6, border: '1px solid #D1D5DB' }}
            />
          </label>
        </details>

        {/* CHAT MESSAGES AREA */}
        <div
          ref={chatScrollContainerRef}
          onScroll={handleScroll}
          className="copilot-messages"
          style={{
            flex: 1,
            overflowY: 'auto',
            padding: '24px',
            display: 'flex',
            flexDirection: 'column',
            gap: 20,
          }}
        >


          {messages.map((msg) => (
            <div
              key={msg.id}
              style={{
                display: 'flex',
                flexDirection: 'column',
                alignItems: msg.role === 'user' ? 'flex-end' : 'flex-start',
                width: '100%',
              }}
            >
              {msg.role === 'user' ? (
                <div className="chat-bubble-user">
                  <div style={{ fontSize: '0.92rem', lineHeight: 1.5 }}>{msg.content}</div>
                  <div style={{ fontSize: '0.7rem', color: '#A3A3A3', marginTop: 4, textAlign: 'right' }}>
                    {msg.time}
                  </div>
                </div>
              ) : (
                <div className="chat-bubble-ai copilot-assistant-message" style={{ width: '100%' }}>
                  {/* AI header */}
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 12 }}>
                    <div className="copilot-message-mark">
                      <CopilotLogo style={{ width: 16, height: 16 }} />
                    </div>
                    <span style={{ fontSize: '0.82rem', fontWeight: 700, color: '#111111' }}>
                      VinFast Sales Copilot
                    </span>
                  </div>


                  {msg.status === 'needs_clarification' && (
                    <p style={{ marginBottom: 8, fontSize: '0.8rem', color: '#92400E', fontWeight: 600 }}>
                      ⚠️ Cần bạn bổ sung thông tin
                    </p>
                  )}
                  {msg.status === 'partial' && (
                    <p style={{ marginBottom: 8, fontSize: '0.8rem', color: '#92400E', fontWeight: 600 }}>
                      ℹ️ Đã xác minh được một phần
                    </p>
                  )}
                  {copilotReason(msg.reason_code) && (
                    <p role="status" style={{ fontSize: '0.8rem', color: '#92400E', marginBottom: 8 }}>
                      {copilotReason(msg.reason_code)}
                    </p>
                  )}

                  {/* Formatted body with Markdown & citations */}
                  <div style={{ fontSize: '0.92rem', color: '#222222', lineHeight: 1.6 }}>
                    {renderMarkdownWithCitations(msg.content, msg.citations, setActiveCitation)}

                  </div>

                  {msg.missing_information?.length > 0 && (
                    <div style={{ marginTop: 10, fontSize: '0.82rem', color: '#737373' }}>
                      <strong>Thông tin còn thiếu:</strong>
                      <ul style={{ paddingLeft: 20 }}>
                        {msg.missing_information.map((item, index) => (
                          <li key={index}>{item}</li>
                        ))}
                      </ul>
                    </div>
                  )}

                  {/* Talking points recommendation box */}
                  {/* Citations / Evidence Sources */}
                  {msg.citations && msg.citations.length > 0 && (
                    <div style={{ marginTop: 14, paddingTop: 12, borderTop: '1px solid #F0F0EE' }}>
                      <div
                        style={{
                          fontSize: '0.78rem',
                          fontWeight: 600,
                          color: '#737373',
                          marginBottom: 6,
                          display: 'flex',
                          alignItems: 'center',
                          gap: 6,
                        }}
                      >
                        <BookIcon style={{ width: 12, height: 12 }} />
                        <span>Nguồn đối chiếu tài liệu chính thức:</span>
                      </div>
                      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
                        {msg.citations
                          .filter(
                            (cite, idx, self) =>
                              idx ===
                              self.findIndex(
                                (c) =>
                                  (c.document_id && c.document_id === cite.document_id) ||
                                  (c.title && c.title === cite.title)
                              )
                          )
                          .map((cite, cIdx) => (
                            <button
                              key={cIdx}
                              type="button"
                              onClick={() => {
                                if (cite.content) {
                                  setActiveCitation(cite);
                                } else if (cite.document_id) {
                                  handleOpenCitation(cite.document_id);
                                } else {
                                  setActiveCitation(cite);
                                }
                              }}
                              disabled={citationLoading}
                              style={{
                                padding: '4px 10px',
                                borderRadius: 6,
                                backgroundColor: '#F4F4F2',
                                border: '1px solid #E0E0DD',
                                fontSize: '0.75rem',
                                color: '#111111',
                                fontWeight: 500,
                                display: 'inline-flex',
                                alignItems: 'center',
                                gap: 6,
                                cursor: 'pointer',
                              }}
                            >
                              <span>{cite.title || cite.document_id}</span>
                              <ChevronRight style={{ width: 10, height: 10 }} />
                            </button>
                          ))}
                      </div>
                    </div>
                  )}

                  {/* Next question prompt */}
                  {msg.sales_actions?.length > 0 && (
                    <div style={{ marginTop: 12, fontSize: '0.82rem' }}>
                      <strong>Bước trao đổi tiếp theo:</strong>
                      <ol style={{ paddingLeft: 20 }}>
                        {msg.sales_actions.map((action, index) => (
                          <li key={index}>{action}</li>
                        ))}
                      </ol>
                    </div>
                  )}

                  {msg.suggested_next_question && (
                    <div style={{ marginTop: 12 }}>
                      <button
                        onClick={() => handleSend(msg.suggested_next_question)}
                        style={{
                          padding: '6px 12px',
                          borderRadius: 9999,
                          border: '1px dashed #B0B0AC',
                          backgroundColor: '#FFFFFF',
                          fontSize: '0.78rem',
                          color: '#444444',
                          cursor: 'pointer',
                        }}
                      >
                        <ArrowRight style={{ width: 13, height: 13, color: '#0F172A', display: 'inline', verticalAlign: '-2px', marginRight: 4 }} /> Gợi ý hỏi tiếp: <strong>{msg.suggested_next_question}</strong>
                      </button>
                    </div>
                  )}

                  {/* Footer actions */}
                  <div
                    style={{
                      display: 'flex',
                      justifyContent: 'space-between',
                      alignItems: 'center',
                      marginTop: 14,
                      paddingTop: 10,
                      borderTop: '1px solid #F4F4F2',
                      fontSize: '0.75rem',
                      color: '#888888',
                    }}
                  >
                    <span>{msg.time}</span>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                      <button
                        onClick={() => handleCopy(msg.id, msg.content)}
                        style={{
                          display: 'inline-flex',
                          alignItems: 'center',
                          gap: 4,
                          color: '#666666',
                          fontSize: '0.75rem',
                          background: 'none',
                          border: 'none',
                          cursor: 'pointer',
                        }}
                      >
                        {copiedId === msg.id ? (
                          <>
                            <CheckIcon style={{ width: 13, height: 13, color: '#111111' }} />
                            <span style={{ color: '#111111' }}>Đã sao chép</span>
                          </>
                        ) : (
                          <>
                            <CopyIcon style={{ width: 13, height: 13 }} />
                            <span>Sao chép</span>
                          </>
                        )}
                      </button>
                    </div>
                  </div>
                </div>
              )}
            </div>
          ))}

          {loading && (
            <div className="chat-bubble-ai copilot-assistant-message" style={{ width: '80%' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
                <div className="copilot-message-mark">
                  <CopilotLogo style={{ width: 15, height: 15 }} />
                </div>
                <span style={{ fontSize: '0.8rem', fontWeight: 600, color: '#111111' }}>
                  {streamStatus || 'Copilot đang chuẩn bị nội dung tư vấn...'}
                </span>
              </div>
              <div style={{ display: 'flex', gap: 6 }}>
                <span style={{ width: 8, height: 8, borderRadius: '50%', backgroundColor: '#111111', animation: 'bounce 1s infinite 0.1s' }} />
                <span style={{ width: 8, height: 8, borderRadius: '50%', backgroundColor: '#111111', animation: 'bounce 1s infinite 0.2s' }} />
                <span style={{ width: 8, height: 8, borderRadius: '50%', backgroundColor: '#111111', animation: 'bounce 1s infinite 0.3s' }} />
              </div>
            </div>
          )}

        </div>


        {/* BOTTOM INPUT BAR */}
        <div className="copilot-composer">
          {error && <p role="alert" style={{ color: '#991B1B', fontSize: '0.82rem', marginBottom: 8 }}>{error}</p>}
          <form
            className="copilot-composer-form"
            onSubmit={(e) => {
              e.preventDefault();
              handleSend();

            }}
          >
            <textarea
              ref={textareaRef}
              rows={1}
              value={inputMessage}
              onChange={(e) => setInputMessage(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) {
                  e.preventDefault();
                  handleSend();
                }
              }}
              placeholder="Nhập câu hỏi tư vấn... (Enter để gửi, Shift+Enter xuống dòng)"
              style={{
                flex: 1,
                border: 'none',
                background: 'transparent',
                outline: 'none',
                fontSize: '0.9rem',
                color: '#111111',
                resize: 'none',
                maxHeight: 140,
                minHeight: 24,
                lineHeight: 1.4,
                fontFamily: 'inherit',
              }}
              disabled={loading}
            />

            <button
              className="copilot-send-button"
              type="submit"
              disabled={!inputMessage.trim() || loading}
              title="Gửi câu hỏi"
            >
              <SendIcon style={{ width: 16, height: 16 }} />
            </button>
          </form>
        </div>
      </div>

      {/* RIGHT SIDEBAR: CONTEXT PANEL + FAQ + CHEAT SHEET */}
      <div className="copilot-sidebar-column">
        <ProductContextPanel
          browseModel={browseModel}
          resolvedModel={resolvedContext.model}
          resolvedDate={resolvedContext.date}
          originMessageId={resolvedContext.originMessageId}
          insights={resolvedContext.insights}
          loading={loading}
          onSelectBrowseModel={(model) => setBrowseModel(model)}
          onFillDraft={handleFillDraft}
          onSwitchModel={() => {
            setResolvedContext({ model: null, date: null, originMessageId: null, insights: [] });
          }}
          onCitationClick={(citation) => setActiveCitation(citation)}
          onCopy={handleCopy}
          copiedId={copiedId}
          onComposeMessage={(draft) => handleFillDraft(draft)}
        />


      </div>
      {/* SOURCE CITATION DOCUMENT MODAL */}
      <Modal
        isOpen={Boolean(selectedCitationDoc)}
        onClose={() => setSelectedCitationDoc(null)}
        title={selectedCitationDoc ? selectedCitationDoc.title : "Tài liệu nguồn trích dẫn"}
        maxWidth={780}
      >
        {selectedCitationDoc && (
          <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 10, fontSize: "0.78rem", color: "#737373", borderBottom: "1px solid #F0F0EE", paddingBottom: 10, flexWrap: "wrap" }}>
              <span>Mã văn bản: <strong>{selectedCitationDoc.document_id}</strong></span>
              {selectedCitationDoc.effective_date && (
                <>
                  <span>•</span>
                  <span>Ngày hiệu lực: <strong>{selectedCitationDoc.effective_date}</strong></span>
                </>
              )}
              {selectedCitationDoc.product_model && (
                <>
                  <span>•</span>
                  <span>Dòng xe: <strong>{selectedCitationDoc.product_model}</strong></span>
                </>
              )}
              {selectedCitationDoc.status && (
                <>
                  <span>•</span>
                  <span>Trạng thái: <strong>{selectedCitationDoc.status}</strong></span>
                </>
              )}
            </div>

            <div
              style={{
                fontSize: "0.88rem",
                lineHeight: 1.6,
                color: "#222222",
                whiteSpace: "pre-wrap",
                maxHeight: "60vh",
                overflowY: "auto",
                backgroundColor: "#FAFAFA",
                padding: "16px 20px",
                borderRadius: 8,
                border: "1px solid #ECECE8",
              }}
            >
              {selectedCitationDoc.content}
            </div>

            {onOpenDocument && (
              <div style={{ display: "flex", justifyContent: "flex-end", paddingTop: 10, borderTop: "1px solid #F0F0EE" }}>
                <button
                  type="button"
                  className="btn-outline"
                  onClick={() => {
                    const docId = selectedCitationDoc.document_id;
                    setSelectedCitationDoc(null);
                    onOpenDocument(docId);
                  }}
                  style={{ fontSize: "0.82rem", padding: "8px 14px" }}
                >
                  Xem toàn văn trong mục Knowledge →
                </button>
              </div>
            )}
          </div>
        )}
      </Modal>

      <SourceViewerModal
        isOpen={!!activeCitation}
        onClose={() => setActiveCitation(null)}
        citation={activeCitation}
        onOpenDocument={onOpenDocument}
      />
        </div>
      </div>
    </div>
  );
}
