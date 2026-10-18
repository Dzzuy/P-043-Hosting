import { useCallback, useEffect, useId, useRef, useState } from 'react';
import { Car, ChevronDown, FileText, Maximize2, Minimize2, MessageCircleQuestion, Receipt, Search, X } from 'lucide-react';
import { Modal } from '../common/Modal';
import { VEHICLES, MODEL_SVG_MAP } from '../../data/vehicleData';
import { POLICIES } from '../../data/policyData';
import { PRICING_TARIFFS } from '../../data/feeData';
import { FAQ_QUESTIONS } from '../../data/faqData';
import { copilotApi } from '../../api/copilotApi';
import { sourceHighlight, verifySourceReference } from './sourceReference';
import './knowledge.css';

const TABS = [
  { id: 'vehicles', title: 'Dòng xe', icon: Car, data: VEHICLES, unit: 'dòng xe' },
  { id: 'policies', title: 'Chính sách & hợp đồng', icon: FileText, data: POLICIES, unit: 'tài liệu' },
  { id: 'fees', title: 'Giá & phí', icon: Receipt, data: PRICING_TARIFFS, unit: 'tài liệu' },
  { id: 'faq', title: 'FAQ', icon: MessageCircleQuestion, data: FAQ_QUESTIONS, unit: 'câu hỏi' },
];
const FAQ_MODELS = ['Tất cả', 'VF 3', 'VF 5', 'VF 6', 'VF 7', 'VF 8', 'VF 9'];
const OFFICIAL_VEHICLE_IMAGES = {
  vf3: '/vehicles/official/vf-3.webp',
  vf5: '/vehicles/official/vf-5.webp',
  vf6: '/vehicles/official/vf-6.webp',
  vf7: '/vehicles/official/vf-7.webp',
  vf8: '/vehicles/official/vf-8.webp',
  vf9: '/vehicles/official/vf-9.webp',
  vfwild: '/vehicles/official/vf-wild.webp',
};
const CORE_SPECS = [['range', 'Quãng đường'], ['power', 'Công suất'], ['battery_capacity', 'Dung lượng pin'], ['charging_dc', 'Sạc nhanh DC']];
const DRIVE_SPECS = [...CORE_SPECS, ['torque', 'Mô-men xoắn'], ['drivetrain', 'Hệ dẫn động']];
const DIMENSION_SPECS = [['dimensions', 'Kích thước (D × R × C)'], ['wheelbase', 'Chiều dài cơ sở'], ['ground_clearance', 'Khoảng sáng gầm'], ['top_speed', 'Tốc độ tối đa']];
const normalize = (value) => String(value ?? '').normalize('NFD').replace(/\p{Diacritic}/gu, '').replace(/đ/g, 'd').replace(/Đ/g, 'D').toLocaleLowerCase('vi');
function matches(value, query) {
  if (value && typeof value === 'object') return Object.values(value).some((item) => matches(item, query));
  return normalize(value).includes(query);
}
function sortDocuments(documents) {
  return [...documents].sort((a, b) => {
    const rank = (date) => /^\d{4}-\d{2}(?:-\d{2})?$/.test(date ?? '') ? Date.parse(`${date.length === 7 ? `${date}-01` : date}T00:00:00Z`) : -Infinity;
    const first = rank(a.effective_date);
    const second = rank(b.effective_date);
    return first === second ? 0 : second - first;
  });
}
const UPDATES = sortDocuments([...POLICIES, ...PRICING_TARIFFS]);
const NEW_IDS = new Set(UPDATES.slice(0, 3).map((doc) => doc.id));
function dateParts(value) {
  const [year, month, day] = String(value ?? '').split('-');
  return { year: year || '', month: month || '', day: day || '' };
}
function formatDate(value) {
  const { year, month, day } = dateParts(value);
  if (!year) return 'Chưa rõ';
  return [day, month, year].filter(Boolean).join('.');
}
function vehicleSpec(vehicle, key) {
  return vehicle.specs?.[key] || vehicle[key] || (key === 'charging_dc' ? vehicle.charging_time : '') || 'Đang cập nhật';
}
function VehicleImage({ vehicle }) {
  return <img className="kb-vehicle-image" src={OFFICIAL_VEHICLE_IMAGES[vehicle.id] || vehicle.image} alt={vehicle.name} loading="lazy" onError={(event) => {
    const fallback = MODEL_SVG_MAP[vehicle.id];
    if (fallback && event.currentTarget.dataset.fallback !== 'true') {
      event.currentTarget.dataset.fallback = 'true';
      event.currentTarget.src = fallback;
    }
  }} />;
}
function Specs({ vehicle, fields }) {
  return <dl className="kb-specs">{fields.map(([key, label]) => <div key={key}><dt>{label}</dt><dd>{vehicleSpec(vehicle, key)}</dd></div>)}</dl>;
}
function Prices({ vehicle }) {
  return <div className="kb-prices"><p><strong>Kèm pin:</strong> {vehicle.price_battery_included || 'Đang cập nhật'}</p><p><strong>Thuê pin:</strong> {vehicle.price_battery_rental || 'Theo chính sách'}</p></div>;
}
function UpdateCard({ doc, onOpen }) {
  const { year, month, day } = dateParts(doc.effective_date);
  return <button type="button" className="kb-update" onClick={(event) => onOpen(doc, event.currentTarget)}>
    <span className="kb-date-tile">{month ? <><strong>{day || '01'}</strong><small>{month}</small></> : <strong>{year}</strong>}</span>
    <span className="kb-update-copy"><strong>{doc.title}</strong><span>{doc.summary}</span></span>
  </button>;
}
function DocumentCard({ doc, onOpen }) {
  const [expanded, setExpanded] = useState(false);
  const pointsId = useId();
  const points = doc.key_points ?? [];
  const shown = expanded ? points : points.slice(0, 3);
  return <article className="kb-doc">
    <div className="kb-tags"><span className="kb-pill">{doc.category}</span><span className="kb-muted">Hiệu lực {formatDate(doc.effective_date)}</span>{NEW_IDS.has(doc.id) && <span className="kb-pill kb-pill--new">Mới</span>}</div>
    <h3>{doc.title}</h3>
    <p className="kb-summary">{doc.summary}</p>
    {points.length > 0 && <ol id={pointsId} className="kb-points">{shown.map((point, index) => <li key={index}>{point}</li>)}</ol>}
    {points.length > 3 && <button type="button" className="kb-text-button" aria-expanded={expanded} aria-controls={pointsId} onClick={() => setExpanded(!expanded)}>{expanded ? 'Thu gọn' : `Xem thêm ${points.length - 3} điểm`}</button>}
    <div className="kb-card-foot">{doc.file_url ? <button type="button" className="kb-button kb-button--primary" onClick={(event) => onOpen(doc, event.currentTarget)}>Đọc PDF</button> : <span className="kb-muted">PDF đang cập nhật</span>}</div>
  </article>;
}
function VehicleCard({ vehicle, onSelect }) {
  return <article className="kb-vehicle">
    <div className="kb-vehicle-photo"><VehicleImage vehicle={vehicle} /></div>
    <div><h3>{vehicle.name}</h3><p className="kb-muted">{vehicle.segment}</p></div>
    <Specs vehicle={vehicle} fields={CORE_SPECS} />
    <Prices vehicle={vehicle} />
    <div className="kb-card-foot"><button type="button" className="kb-button kb-button--primary" onClick={() => onSelect(vehicle)} aria-label={`Chi tiết ${vehicle.name}`}>Chi tiết</button></div>
  </article>;
}
function FaqCard({ faq }) {
  const [expanded, setExpanded] = useState(false);
  const answerId = useId();
  return <article className="kb-faq"><span className="kb-muted">{faq.model || 'VinFast'}</span><h3><button className="kb-question" type="button" aria-expanded={expanded} aria-controls={answerId} onClick={() => setExpanded(!expanded)}><span>{faq.question}</span><ChevronDown size={18} aria-hidden="true" className={expanded ? 'kb-chevron kb-chevron--open' : 'kb-chevron'} /></button></h3>
    {expanded && <div id={answerId}><p className="kb-answer">{faq.answer || 'Câu trả lời đang cập nhật.'}</p></div>}
  </article>;
}
function PdfDrawer({ doc, onClose }) {
  const panelRef = useRef(null);
  const closeRef = useRef(null);
  const [headerBottom, setHeaderBottom] = useState(72);
  const titleId = useId();
  useEffect(() => {
    const header = document.querySelector('.top-header');
    const update = () => setHeaderBottom(Math.max(0, header?.getBoundingClientRect().bottom ?? 0));
    update();
    const observer = new ResizeObserver(update);
    if (header) observer.observe(header);
    window.addEventListener('resize', update);
    window.addEventListener('scroll', update, true);
    return () => { observer.disconnect(); window.removeEventListener('resize', update); window.removeEventListener('scroll', update, true); };
  }, []);
  const [fullUrl, setFullUrl] = useState(null);
  const isFull = Boolean(doc) && fullUrl === doc.file_url;
  useEffect(() => {
    if (!doc) return;
    closeRef.current?.focus();
    const handleKey = (event) => {
      if (event.key === 'Escape') { event.preventDefault(); onClose(); }
      if (event.key === 'Tab') {
        const focusable = panelRef.current?.querySelectorAll('a[href], button, iframe');
        const first = focusable?.[0];
        const last = focusable?.[focusable.length - 1];
        if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus(); }
        if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus(); }
      }
    };
    window.addEventListener('keydown', handleKey);
    return () => window.removeEventListener('keydown', handleKey);
  }, [doc, onClose]);
  return <div className={`kb-drawer-layer${doc ? ' kb-drawer-layer--open' : ''}`} style={{ '--kb-header-bottom': `${headerBottom}px` }} inert={!doc}>
    <div className="kb-drawer-shade" onClick={onClose} aria-hidden="true" />
    <section ref={panelRef} className={`kb-drawer${isFull ? ' kb-drawer--full' : ''}`} role="dialog" aria-modal="true" aria-labelledby={titleId} aria-hidden={!doc}>
      <header className="kb-drawer-head"><div><h2 id={titleId}>{doc?.title}</h2><p className="kb-muted">Hiệu lực: {doc?.effective_date}</p></div><div className="kb-drawer-tools"><a className="kb-drawer-link" href={doc?.file_url} target="_blank" rel="noopener noreferrer">Mở tab mới</a><button type="button" className="kb-icon-button" aria-label={isFull ? 'Thu nhỏ' : 'Toàn màn hình'} aria-pressed={isFull} title={isFull ? 'Thu nhỏ' : 'Toàn màn hình'} onClick={() => setFullUrl(isFull ? null : doc?.file_url)}>{isFull ? <Minimize2 size={18} aria-hidden="true" /> : <Maximize2 size={18} aria-hidden="true" />}</button><button ref={closeRef} type="button" className="kb-icon-button" aria-label="Đóng" onClick={onClose}><X size={20} aria-hidden="true" /></button></div></header>
      {doc && <iframe className="kb-pdf-frame" src={doc.file_url} title={`PDF: ${doc.title}`} />}
    </section>
  </div>;
}

export function KnowledgeView({ sourceDocumentId, sourceReference }) {
  const [tab, setTab] = useState('vehicles');
  const [query, setQuery] = useState('');
  const [selectedVehicle, setSelectedVehicle] = useState(null);
  const [selectedDocument, setSelectedDocument] = useState(null);
  const [viewingPdf, setViewingPdf] = useState(null);
  const [sourceError, setSourceError] = useState('');
  const [sourceLoading, setSourceLoading] = useState(false);
  const [faqModel, setFaqModel] = useState('Tất cả');
  const triggerRef = useRef(null);
  const sourceRequestRef = useRef(0);
  const searchId = useId();

  useEffect(() => {
    if (!sourceDocumentId) return;
    let active = true;
    copilotApi.getSource(sourceDocumentId)
      .then((document) => {
        if (!active) return;
        verifySourceReference(document, sourceReference);
        setSourceError('');
        setSelectedDocument({ ...document, sourceHighlight: sourceHighlight(document, sourceReference) });
      })
      .catch((error) => { if (active) { setSelectedDocument(null); setSourceError(error.message || 'Không mở được tài liệu gốc. Vui lòng thử lại.'); } });
    return () => { active = false; };
  }, [sourceDocumentId, sourceReference]);

  async function openSource(id) {
    const request = ++sourceRequestRef.current;
    setSourceLoading(true);
    setSourceError('');
    try {
      const document = await copilotApi.getSource(id);
      if (request === sourceRequestRef.current) setSelectedDocument(document);
    } catch {
      if (request === sourceRequestRef.current) setSourceError('Không mở được tài liệu gốc. Vui lòng thử lại.');
    } finally {
      if (request === sourceRequestRef.current) setSourceLoading(false);
    }
  }
  function openPdf(doc, trigger) { triggerRef.current = trigger; setViewingPdf(doc); }
  // This callback is intentionally stable so the drawer only focuses when it opens.
  const closePdf = useCallback(() => { setViewingPdf(null); triggerRef.current?.focus(); }, []);
  const search = normalize(query.trim());
  const activeTab = TABS.find((item) => item.id === tab);
  let items = activeTab.data.filter((entry) => matches(entry, search));
  if (tab === 'faq') items = items.filter((faq) => faqModel === 'Tất cả' || faq.model === faqModel || faq.model?.startsWith(`${faqModel} `));
  if (tab === 'policies' || tab === 'fees') items = sortDocuments(items);
  const filtered = Boolean(search) || (tab === 'faq' && faqModel !== 'Tất cả');

  function renderItem(item) {
    if (tab === 'vehicles') return <VehicleCard key={item.id} vehicle={item} onSelect={setSelectedVehicle} />;
    if (tab === 'faq') return <FaqCard key={item.id} faq={item} />;
    return <DocumentCard key={item.id} doc={item} onOpen={openPdf} />;
  }
  return <div className="kb-page">
    <header className="kb-title">
      <div><h1>Kho kiến thức</h1><p>Tài liệu VinFast để đọc trước khi luyện tập. Mọi điểm đều dẫn về PDF gốc.</p></div>
      <div className="kb-search"><label htmlFor={searchId} className="kb-sr-only">Tìm trong tài liệu, dòng xe, câu hỏi</label><Search size={17} aria-hidden="true" /><input id={searchId} type="search" placeholder="Tìm trong mục đang xem…" value={query} onChange={(event) => setQuery(event.target.value)} /></div>
    </header>
    {sourceLoading && <p className="kb-notice" role="status">Đang mở tài liệu gốc…</p>}
    {sourceError && <div className="kb-notice" role="alert"><span>{sourceError}</span><button type="button" className="kb-icon-button" aria-label="Đóng thông báo" onClick={() => setSourceError('')}><X size={18} /></button></div>}
    <section className="kb-fresh" aria-labelledby="kb-fresh-title">
      <h2 id="kb-fresh-title" className="kb-label">Mới cập nhật</h2>
      <div className="kb-fresh-row">{UPDATES.slice(0, 3).map((doc) => <UpdateCard key={doc.id} doc={doc} onOpen={openPdf} />)}</div>
    </section>
    <nav className="kb-tabs" aria-label="Danh mục kiến thức">{TABS.map((item) => <button type="button" key={item.id} className="kb-tab" aria-pressed={tab === item.id} onClick={() => setTab(item.id)}><item.icon size={20} aria-hidden="true" />{item.title}<span className="kb-tab-count">{item.data.length}</span></button>)}</nav>
    {tab === 'faq' && <div className="kb-filters" role="group" aria-label="Lọc theo dòng xe">{FAQ_MODELS.map((model) => <button type="button" className="kb-filter" key={model} aria-pressed={faqModel === model} onClick={() => setFaqModel(model)}>{model}</button>)}</div>}
    {filtered && <p className="kb-muted" role="status">{items.length} kết quả</p>}
    {items.length ? <div className={`kb-grid${tab === 'vehicles' ? ' kb-grid--vehicles' : ''}`}>{items.map(renderItem)}</div> : <p className="kb-empty">{filtered ? 'Không tìm thấy kết quả. Hãy thử từ khóa hoặc bộ lọc khác.' : `Chưa có ${activeTab.unit} trong mục này.`}</p>}
    <PdfDrawer doc={viewingPdf} onClose={closePdf} />
    <Modal isOpen={Boolean(selectedVehicle)} onClose={() => setSelectedVehicle(null)} title={selectedVehicle?.name || ''} maxWidth={900}>
      {selectedVehicle && <div className="kb-modal-content"><VehicleImage vehicle={selectedVehicle} /><div><h3>{selectedVehicle.name}</h3><p className="kb-muted">{selectedVehicle.segment}</p>{selectedVehicle.tagline && <p>{selectedVehicle.tagline}</p>}</div><Prices vehicle={selectedVehicle} />
        <section><h4>Thông số vận hành & pin</h4><Specs vehicle={selectedVehicle} fields={DRIVE_SPECS} /></section><section><h4>Kích thước & khung gầm</h4><Specs vehicle={selectedVehicle} fields={DIMENSION_SPECS} /></section>
        {(selectedVehicle.adas_features?.length > 0 || selectedVehicle.specs?.adas) && <section><h4>Công nghệ an toàn & hỗ trợ lái (ADAS)</h4>{selectedVehicle.adas_features?.length ? <ul className="kb-detail-list">{selectedVehicle.adas_features.map((feature) => <li key={feature}>{feature}</li>)}</ul> : <p>{selectedVehicle.specs.adas}</p>}</section>}
        {selectedVehicle.highlights?.length > 0 && <section><h4>Điểm nhấn tư vấn nổi bật</h4><ul className="kb-detail-list">{selectedVehicle.highlights.map((highlight) => <li key={highlight}>{highlight}</li>)}</ul></section>}
        {selectedVehicle.document_id && <div className="kb-modal-footer"><span className="kb-muted">Mã văn bản: {selectedVehicle.document_id}</span><button type="button" className="kb-button" onClick={() => { const id = selectedVehicle.document_id; setSelectedVehicle(null); openSource(id); }}>Xem tài liệu gốc</button></div>}
      </div>}
    </Modal>
    <Modal isOpen={Boolean(selectedDocument)} onClose={() => setSelectedDocument(null)} title={selectedDocument?.title || ''} maxWidth={780}>
      {selectedDocument && <div className="kb-modal-content"><dl className="kb-document-meta"><div><dt>Mã văn bản</dt><dd>{selectedDocument.document_id}</dd></div><div><dt>Ngày hiệu lực</dt><dd>{selectedDocument.effective_date || 'Chưa xác định'}</dd></div><div><dt>Dòng xe</dt><dd>{selectedDocument.product_model || 'Tất cả'}</dd></div><div><dt>Trạng thái</dt><dd>{selectedDocument.status || 'Chưa xác định'}</dd></div></dl><div className="kb-document-text">{selectedDocument.sourceHighlight ? <>{selectedDocument.sourceHighlight.before}<mark ref={(node) => { if (node) requestAnimationFrame(() => { if (node.isConnected) node.scrollIntoView({ block: 'center' }); }); }}>{selectedDocument.sourceHighlight.text}</mark>{selectedDocument.sourceHighlight.after}</> : (selectedDocument.content || 'Nội dung tài liệu đang cập nhật.')}</div></div>}
    </Modal>
  </div>;
}
