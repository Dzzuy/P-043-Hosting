import { useState } from 'react';
import { ChevronRight, Info } from 'lucide-react';
import { formatMoney } from './workspaceData';

function FactEditor({ field, value, onSave, onCancel }) {
  const [text, setText] = useState(Array.isArray(value) ? value.join(', ') : value ?? '');
  const [error, setError] = useState(''); const [busy, setBusy] = useState(false);
  return <form className="sw-fact-editor" onSubmit={async (event) => {
    event.preventDefault(); setBusy(true); setError('');
    const result = field === 'interested_models' ? text.split(',').map((part) => part.trim()).filter(Boolean) : ['budget_vnd', 'down_payment_vnd'].includes(field) ? (text === '' ? null : Number(text)) : text.trim();
    try { await onSave(field, result); onCancel(); } catch (failure) { setError(failure.message); setBusy(false); }
  }}><label>Giá trị sales xác nhận<input autoFocus maxLength={2000} type={['budget_vnd', 'down_payment_vnd'].includes(field) ? 'number' : 'text'} min="0" value={text} onChange={(event) => setText(event.target.value)} /></label><div className="sw-inline-actions"><button type="button" className="sw-text-button" disabled={busy} onClick={onCancel}>Hủy</button><button type="submit" className="sw-secondary-button" disabled={busy}>{busy ? 'Đang lưu…' : 'Lưu xác nhận'}</button></div>{error && <p role="alert" className="sw-freshness">{error}</p>}</form>;
}

export function CustomerProfile({ customer, onSourceClick, onConfirmFact }) {
  const [editing, setEditing] = useState(null);
  const profile = customer.profile;
  const fields = [
    ['interested_models', 'Xe quan tâm', customer.model], ['budget_vnd', 'Ngân sách', customer.budget],
    ['usage_purpose', 'Nhu cầu sử dụng', customer.usage], ['payment_method', 'Hình thức thanh toán', customer.payment],
    ['down_payment_vnd', 'Trả trước', customer.deposit || 'Chưa xác định'],
    ['purchase_timeline', 'Thời điểm mua', profile.purchase_timeline || 'Chưa xác định'],
    ['charging_condition', 'Điều kiện sạc', profile.charging_condition || 'Chưa xác định'],
  ];
  const extraFields = [
    ['competitor_models', 'Xe đang so sánh', profile.competitor_models?.join(', ')],
    ['max_monthly_payment_vnd', 'Trả góp tối đa mỗi tháng', formatMoney(profile.max_monthly_payment_vnd)],
    ['loan_term_years', 'Thời hạn vay', profile.loan_term_years ? `${profile.loan_term_years} năm` : ''],
    ['passenger_count', 'Số người sử dụng', profile.passenger_count],
    ['daily_distance_km', 'Quãng đường hàng ngày', profile.daily_distance_km],
    ['living_area', 'Khu vực sinh sống', profile.living_area],
  ].filter(([, , value]) => value !== undefined && value !== null && value !== '');
  return <div className="sw-profile-content">
    <dl className="sw-profile-grid">{[...fields, ...extraFields].map(([field, label, value]) => {
      const fact = customer.facts.find((item) => item.field === field || (field === 'budget_vnd' && item.field === 'budget_notes'));
      return <div key={field}><dt>{label}</dt><dd>{value}</dd>
        {fact?.verification_status === 'inferred' && <small className="sw-fact-note">AI suy luận · Cần xác minh</small>}
        {fact?.verification_status === 'conflicted' && <small className="sw-freshness">Dữ kiện mâu thuẫn · Cần xác minh</small>}
        {fact?.verification_status === 'confirmed' && <small className="sw-confirmed">Đã xác nhận{fact.note === 'Sales xác nhận' ? ' bởi sales' : ''}</small>}
        {fact?.verification_status === 'reported' && <small className="sw-fact-note">Thông tin ghi nhận từ hội thoại</small>}
        {fact?.source_message_ids.map((id, index) => <button type="button" className="sw-text-button sw-fact-source" key={id} onClick={() => onSourceClick?.(id)}>Tin nguồn {index + 1}<ChevronRight size={11} /></button>)}
        {onConfirmFact && fields.some(([name]) => name === field) && (editing === field ? <FactEditor field={field} value={profile[field]} onSave={onConfirmFact} onCancel={() => setEditing(null)} /> : <button type="button" className="sw-text-button sw-edit-fact" onClick={() => setEditing(field)}>{['inferred', 'conflicted'].includes(fact?.verification_status) ? 'Xác nhận / Sửa' : 'Sửa dữ kiện'}</button>)}
      </div>;
    })}</dl>
    {!!customer.concerns.length && <div className="sw-intelligence-concerns"><h4>Mối quan tâm của khách</h4><ul>{customer.concerns.map((text, index) => <li key={index}>{text}</li>)}</ul></div>}
    <details className="sw-intelligence-contact"><summary>Thông tin liên hệ</summary><p className="sw-profile-contact">{customer.phone}<br />{customer.location}<br />{customer.source}</p></details>
    <p className="sw-info-note"><Info size={14} />Dữ kiện sales xác nhận được giữ khi AI phân tích lại.</p>
  </div>;
}
