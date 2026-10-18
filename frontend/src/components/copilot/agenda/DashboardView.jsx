import { useState } from 'react';
import {
  ArrowRight,
  CalendarDays,
  Check,
  ChevronLeft,
  ChevronRight,
  Clock3,
  Plus,
  RefreshCw,
  X,
} from 'lucide-react';
import { salesCopilotApi } from '../../../api/salesCopilotApi';
import { leadStages } from '../customerWorkspace/workspaceData';
import { useAgendaResource } from './agendaResource';
import { filters, formatDateTime, itemLabel, taskState, waitingDuration } from './agendaData';
import { useWorkspaceClock } from '../customerWorkspace/useCustomerWorkspace';

const STAGE_LABELS = {
  new: 'Mới liên hệ',
  discovery: 'Tìm hiểu nhu cầu',
  qualified: 'Đang tư vấn',
  considering: 'Đang cân nhắc',
  negotiating: 'Đang đàm phán',
  deposit_process: 'Chuẩn bị đặt cọc',
  won: 'Đã ký hợp đồng',
  lost: 'Ngừng chăm sóc',
  needs_confirmation: 'Cần xác nhận',
};

const STAGE_TONES = {
  new: 'slate',
  discovery: 'blue',
  qualified: 'blue',
  considering: 'indigo',
  negotiating: 'teal',
  deposit_process: 'emerald',
  won: 'emerald',
  lost: 'slate',
  needs_confirmation: 'amber',
};

function getStageLabel(stageId) {
  if (STAGE_LABELS[stageId]) return STAGE_LABELS[stageId];
  const found = leadStages.find((s) => s.id === stageId);
  return found?.label || stageId || 'Chưa phân loại';
}

function getStageTone(stageId) {
  return STAGE_TONES[stageId] || 'blue';
}

function formatCompactMoney(vnd) {
  if (!vnd || !Number.isFinite(Number(vnd)) || Number(vnd) <= 0) return null;
  const num = Number(vnd);
  if (num >= 1_000_000_000) {
    const billions = (num / 1_000_000_000).toFixed(2).replace(/\.?0+$/, '');
    return `${billions.replace('.', ',')} tỷ ₫`;
  }
  const millions = Math.round(num / 1_000_000);
  return `${millions.toLocaleString('vi-VN')} tr ₫`;
}

function cleanDemoLabel(text) {
  if (!text) return '';
  return String(text).replace(/^\[Mẫu\]\s*/i, '').trim();
}

function Empty({ children = 'Chưa có dữ liệu.' }) {
  return <p className="agenda-empty">{children}</p>;
}

function Panel({ title, subtitle, children, action, className = '', id }) {
  return (
    <section id={id} className={`agenda-panel ${className}`}>
      <div className="agenda-panel-title">
        <div>
          <h2>{title}</h2>
          {subtitle && <p className="agenda-panel-subtitle">{subtitle}</p>}
        </div>
        {action && <div className="agenda-panel-action">{action}</div>}
      </div>
      {children}
    </section>
  );
}

function TaskRow({ item, now, onEdit, onCustomer, onStatus, busy }) {
  const stateLabel = taskState(item, now);
  const isOverdue = stateLabel === 'Cần cập nhật trạng thái';
  const isHigh = ['high', 'urgent'].includes(item.priority);
  const timeText = item.starts_at
    ? `${formatDateTime(item.starts_at)} - ${formatDateTime(item.ends_at)}`
    : 'Chưa xếp giờ';

  const metaParts = [
    timeText,
    itemLabel(item),
    item.location,
    isHigh ? 'Ưu tiên cao' : null,
    isOverdue ? 'Quá giờ' : null,
  ].filter(Boolean);

  return (
    <div className="agenda-task-row">
      <div className="agenda-task-copy">
        <strong className="agenda-task-title">{item.title}</strong>
        <div className="agenda-task-details">
          {item.customer_name && (
            <>
              <button
                type="button"
                className="agenda-inline-link"
                onClick={() => onCustomer(item)}
              >
                {item.customer_name}
              </button>
              <span className="agenda-dot-sep">·</span>
            </>
          )}
          <span>{metaParts.join(' · ')}</span>
        </div>
      </div>

      <div className="agenda-task-actions">
        {!['completed', 'needs_review'].includes(item.status) && (
          <button
            type="button"
            className="agenda-btn-minimal"
            disabled={busy}
            onClick={() => onStatus(item, 'completed')}
          >
            <Check size={12} strokeWidth={2} />
            Xong
          </button>
        )}
        <button
          type="button"
          className="agenda-btn-minimal"
          disabled={busy}
          onClick={() => onEdit(item)}
        >
          {item.status === 'needs_review' ? 'Duyệt' : 'Xếp giờ'}
        </button>
        {item.status === 'completed' && (
          <button
            type="button"
            className="agenda-btn-minimal"
            disabled={busy}
            onClick={() => onStatus(item, 'pending')}
          >
            Mở lại
          </button>
        )}
        <button
          type="button"
          className="agenda-btn-minimal is-muted"
          disabled={busy}
          onClick={() => onStatus(item, 'cancelled')}
        >
          Hủy
        </button>
      </div>
    </div>
  );
}

function Bars({ rows, label, totalCount, selectedKey, onSelect }) {
  const max = Math.max(1, ...rows.map((row) => row.count));
  const sum = totalCount || rows.reduce((acc, r) => acc + r.count, 0) || 1;
  return rows.length ? (
    <div className="agenda-bars">
      {rows.map((row) => {
        const pct = Math.round((row.count / sum) * 100);
        const isSelected = selectedKey === row.key;
        const InteractiveTag = onSelect ? 'button' : 'div';
        return (
          <InteractiveTag
            key={row.key}
            type={onSelect ? 'button' : undefined}
            className={`agenda-bar-row ${onSelect ? 'is-clickable' : ''} ${isSelected ? 'is-selected' : ''}`}
            onClick={onSelect ? () => onSelect(row.key) : undefined}
          >
            <div className="agenda-bar-header">
              <span className="agenda-bar-label">{label(row)}</span>
              <span className="agenda-bar-value">
                <strong>{row.count}</strong>
                <small>{pct}%</small>
              </span>
            </div>
            <div className="agenda-bar-track">
              <span style={{ width: `${Math.max(3, (row.count / max) * 100)}%` }} />
            </div>
          </InteractiveTag>
        );
      })}
    </div>
  ) : (
    <Empty />
  );
}

export function DashboardView({
  currentUser,
  active,
  onCreate,
  onEdit,
  onCustomer,
  onCalendar,
  focusedTask,
  onClearFocus,
}) {
  const [filter, setFilter] = useState('today');
  const [page, setPage] = useState(1);
  const [days, setDays] = useState(7);
  const [busy, setBusy] = useState(null);
  const [actionError, setActionError] = useState('');
  const [showAllCustomers, setShowAllCustomers] = useState(false);
  const [customerQueueTab, setCustomerQueueTab] = useState('waiting');
  const [selectedStage, setSelectedStage] = useState(null);
  const now = useWorkspaceClock();

  const resource = useAgendaResource(
    currentUser.user_id,
    `dashboard:${days}:${filter}:${page}`,
    () => salesCopilotApi.getDashboard({ activity_days: days, work_filter: filter, work_page: page }),
    active
  );
  const data = resource.data;

  function changeFilter(value) {
    setFilter(value);
    setPage(1);
  }

  async function status(item, value) {
    if (busy) return;
    setBusy(item.id);
    setActionError('');
    try {
      await salesCopilotApi.updateTaskStatus(item.id, value);
      if (focusedTask?.id === item.id) onClearFocus();
    } catch (error) {
      setActionError(error.message);
    } finally {
      setBusy(null);
    }
  }

  const row = (item) => (
    <TaskRow
      key={item.id}
      item={item}
      now={now}
      busy={busy === item.id}
      onEdit={onEdit}
      onCustomer={onCustomer}
      onStatus={status}
    />
  );

  const activityMax = Math.max(1, ...(data?.message_activity || []).map((day) => day.customer + day.sales));
  const totalCustomerMsgs = (data?.message_activity || []).reduce((acc, d) => acc + d.customer, 0);
  const totalSalesMsgs = (data?.message_activity || []).reduce((acc, d) => acc + d.sales, 0);
  const workCounts = data?.portfolio_insights?.work_counts || {};
  const pendingActionTasks =
    (data?.kpis?.stale_tasks || 0) + (data?.unscheduled?.total || 0) + (data?.kpis?.review_tasks || 0);

  const rawQueueList =
    customerQueueTab === 'waiting'
      ? data?.waiting_customers || []
      : customerQueueTab === 'priority'
        ? data?.priority_customers || []
        : data?.customer_intelligence || [];

  const filteredCustomers = selectedStage
    ? (data?.customers || []).filter((c) => c.stage === selectedStage)
    : rawQueueList;

  const visibleCustomers = showAllCustomers ? filteredCustomers : filteredCustomers.slice(0, 6);

  return (
    <div className="agenda-page dashboard-page" aria-label="Bảng điều khiển bán hàng">
      {/* MINIMALIST HEADER */}
      <header className="agenda-topbar">
        <div className="agenda-topbar-left">
          <h1>Bảng điều khiển</h1>
          <span className="agenda-topbar-meta">
            {currentUser?.display_name || 'Tư vấn viên'}
            {data ? ` · ${formatDateTime(data.generated_at)}` : ''}
          </span>
        </div>

        <div className="agenda-heading-actions">
          <button
            type="button"
            className="agenda-btn-minimal"
            aria-label="Làm mới bảng điều khiển"
            disabled={resource.loading}
            onClick={resource.reload}
          >
            <RefreshCw size={13} strokeWidth={1.75} />
            <span>Làm mới</span>
          </button>
          <button type="button" className="agenda-btn-minimal" onClick={() => onCalendar()}>
            <CalendarDays size={13} strokeWidth={1.75} />
            <span>Lịch tuần</span>
          </button>
          <button
            type="button"
            className="agenda-btn-solid"
            disabled={!data}
            onClick={() => onCreate(data.customers)}
          >
            <Plus size={14} strokeWidth={2} />
            <span>Tạo việc</span>
          </button>
        </div>
      </header>

      {(resource.error || actionError) && (
        <div className="sw-error-banner" role="alert">
          {resource.error || actionError}
          <button type="button" className="sw-text-button" onClick={resource.reload}>
            Thử lại
          </button>
        </div>
      )}

      {!data && (
        <p className="agenda-empty" role="status">
          {resource.loading ? 'Đang tải dữ liệu...' : 'Chưa tải được dữ liệu.'}
        </p>
      )}

      {data && (
        <>
          {/* ROW 1: FLAT METRIC STRIP WITH SUBTLE ACCENT DOTS */}
          <section className="agenda-metric-strip" aria-label="Chỉ số vận hành">
            <button
              type="button"
              className="agenda-metric-cell"
              onClick={() => {
                setSelectedStage(null);
                setCustomerQueueTab('waiting');
              }}
            >
              <span className="agenda-metric-label">
                <i className="agenda-dot is-amber" />
                Khách chờ phản hồi
              </span>
              <div className="agenda-metric-main">
                <strong>{data.kpis.waiting_customers}</strong>
                <small className="is-amber">
                  {data.waiting_customers[0]?.waiting_since
                    ? waitingDuration(data.waiting_customers[0].waiting_since, now)
                    : 'Đã trả lời hết'}
                </small>
              </div>
            </button>

            <button
              type="button"
              className="agenda-metric-cell"
              onClick={() => {
                setSelectedStage(null);
                setCustomerQueueTab('priority');
              }}
            >
              <span className="agenda-metric-label">
                <i className="agenda-dot is-emerald" />
                Cơ hội nóng / Khách mở
              </span>
              <div className="agenda-metric-main">
                <strong>
                  {data.kpis.hot_leads}
                  <span className="agenda-metric-denom">/{data.kpis.active_customers}</span>
                </strong>
                <small className="is-emerald">{data.kpis.closing_leads || 0} sát chốt</small>
              </div>
            </button>

            <button
              type="button"
              className="agenda-metric-cell"
              onClick={() => changeFilter(data.kpis.today_events > 0 ? 'today' : 'upcoming')}
            >
              <span className="agenda-metric-label">
                <i className="agenda-dot is-blue" />
                Lịch hôm nay
              </span>
              <div className="agenda-metric-main">
                <strong>{data.kpis.today_events}</strong>
                <small className="is-blue">{data.kpis.upcoming_events} sắp đến</small>
              </div>
            </button>

            <button
              type="button"
              className="agenda-metric-cell"
              onClick={() =>
                changeFilter(
                  data.kpis.stale_tasks > 0
                    ? 'stale'
                    : data.unscheduled.total > 0
                      ? 'unscheduled'
                      : 'review'
                )
              }
            >
              <span className="agenda-metric-label">
                <i className="agenda-dot is-indigo" />
                Việc cần xếp giờ
              </span>
              <div className="agenda-metric-main">
                <strong>{pendingActionTasks}</strong>
                <small>{data.unscheduled.total} chưa xếp lịch</small>
              </div>
            </button>

            <button
              type="button"
              className="agenda-metric-cell"
              onClick={() => {
                setSelectedStage(null);
                setCustomerQueueTab('priority');
              }}
            >
              <span className="agenda-metric-label">
                <i className="agenda-dot is-teal" />
                Ngân sách dự kiến
              </span>
              <div className="agenda-metric-main">
                <strong className="is-money">
                  {data.kpis.pipeline_budget_vnd > 0 ? formatCompactMoney(data.kpis.pipeline_budget_vnd) : '0 ₫'}
                </strong>
                <small>{data.kpis.completed_tasks}/{data.kpis.total_tasks} việc xong</small>
              </div>
            </button>
          </section>

          {/* ROW 2 (TOP OF PAGE): CUSTOMER STAGE FUNNEL */}
          <Panel
            id="agenda-stages"
            className="agenda-funnel-top-panel"
            title="Phễu giai đoạn khách hàng"
            subtitle="Phân bổ trạng thái chuyển đổi trong danh sách phụ trách"
            action={
              selectedStage ? (
                <button
                  type="button"
                  className="agenda-btn-minimal"
                  onClick={() => setSelectedStage(null)}
                >
                  <X size={12} /> Bỏ lọc: {getStageLabel(selectedStage)}
                </button>
              ) : (
                <span className="agenda-muted-caption">Tổng {data.customers.length} khách hàng</span>
              )
            }
          >
            <div className="agenda-stage-funnel-grid">
              {data.stage_distribution.map((item) => {
                const total = Math.max(1, data.customers.length);
                const pct = Math.round((item.count / total) * 100);
                const isSelected = selectedStage === item.stage;
                const tone = getStageTone(item.stage);
                return (
                  <button
                    type="button"
                    key={item.stage}
                    className={`agenda-funnel-step ${isSelected ? 'is-selected' : ''}`}
                    onClick={() => setSelectedStage(isSelected ? null : item.stage)}
                  >
                    <div className="agenda-funnel-step-top">
                      <span className="agenda-funnel-label">
                        <i className={`agenda-dot is-${tone}`} />
                        {getStageLabel(item.stage)}
                      </span>
                      <span className="agenda-funnel-pct">{pct}%</span>
                    </div>
                    <strong className="agenda-funnel-count">{item.count}</strong>
                    <div className="agenda-bar-track">
                      <span className={`tone-${tone}`} style={{ width: `${Math.max(4, pct)}%` }} />
                    </div>
                  </button>
                );
              })}
            </div>
          </Panel>

          {focusedTask && (
            <Panel
              title="Công việc đang chọn"
              action={
                <button type="button" className="agenda-btn-minimal" onClick={onClearFocus}>
                  Đóng
                </button>
              }
            >
              {row(focusedTask)}
            </Panel>
          )}

          {/* ROW 3: PRIMARY 2-COLUMN WORKSPACE (CUSTOMERS + TASKS) */}
          <div className="agenda-main-grid">
            {/* LEFT: MINIMALIST 2-LINE CUSTOMER LIST */}
            <div className="agenda-column" id="agenda-primary-queue">
              <section className="agenda-panel">
                <div className="agenda-queue-header">
                  <div className="agenda-queue-tabs" role="tablist" aria-label="Danh sách khách hàng">
                    <button
                      type="button"
                      role="tab"
                      aria-selected={!selectedStage && customerQueueTab === 'waiting'}
                      className={!selectedStage && customerQueueTab === 'waiting' ? 'is-active' : ''}
                      onClick={() => {
                        setSelectedStage(null);
                        setCustomerQueueTab('waiting');
                      }}
                    >
                      <span>Chờ phản hồi</span>
                      <em>{data.waiting_customers.length}</em>
                    </button>
                    <button
                      type="button"
                      role="tab"
                      aria-selected={!selectedStage && customerQueueTab === 'priority'}
                      className={!selectedStage && customerQueueTab === 'priority' ? 'is-active' : ''}
                      onClick={() => {
                        setSelectedStage(null);
                        setCustomerQueueTab('priority');
                      }}
                    >
                      <span>Cơ hội trọng điểm</span>
                      <em>{(data.priority_customers || []).length}</em>
                    </button>
                    <button
                      type="button"
                      role="tab"
                      aria-selected={!selectedStage && customerQueueTab === 'intelligence'}
                      className={!selectedStage && customerQueueTab === 'intelligence' ? 'is-active' : ''}
                      onClick={() => {
                        setSelectedStage(null);
                        setCustomerQueueTab('intelligence');
                      }}
                    >
                      <span>Băn khoăn & Cam kết</span>
                      <em>{(data.customer_intelligence || []).length}</em>
                    </button>
                  </div>
                </div>

                {visibleCustomers.length ? (
                  <div className="agenda-minimal-list">
                    {visibleCustomers.map((customer) => {
                      const stageLabel = getStageLabel(customer.stage);
                      const modelText = customer.models?.length ? customer.models.join(', ') : null;
                      const budgetText = formatCompactMoney(customer.budget_vnd);
                      const competitorText = customer.competitor_models?.length
                        ? `So sánh ${customer.competitor_models[0]}`
                        : null;
                      const waitText = customer.waiting_since
                        ? waitingDuration(customer.waiting_since, now)
                        : null;

                      const facts = [stageLabel, budgetText, competitorText].filter(Boolean);

                      const singleNote = cleanDemoLabel(
                        customerQueueTab === 'waiting' && !selectedStage
                          ? customer.last_message || customer.issues?.[0] || customer.buying_signals?.[0]
                          : customerQueueTab === 'intelligence' && !selectedStage
                            ? customer.issues?.[0] || customer.promises?.[0] || customer.quick_summary
                            : customer.buying_signals?.[0] ||
                                customer.issues?.[0] ||
                                customer.quick_summary ||
                                customer.last_message
                      );

                      return (
                        <div className="agenda-minimal-row" key={customer.customer_id}>
                          <div className="agenda-minimal-row-main">
                            <div className="agenda-minimal-line1">
                              <button
                                type="button"
                                className="agenda-customer-name-btn"
                                onClick={() => onCustomer(customer)}
                              >
                                {customer.customer_name}
                              </button>
                              {modelText && <span className="agenda-model-tag">{modelText}</span>}
                              <span className="agenda-minimal-meta">{facts.join(' · ')}</span>
                            </div>
                            {singleNote && <p className="agenda-minimal-line2">{singleNote}</p>}
                          </div>

                          <div className="agenda-minimal-row-right">
                            {waitText && <span className="agenda-minimal-time">{waitText}</span>}
                            <button
                              type="button"
                              className="agenda-btn-minimal is-accent-hover"
                              onClick={() => onCustomer(customer)}
                            >
                              Trả lời
                            </button>
                            <button
                              type="button"
                              className="agenda-btn-minimal is-muted"
                              onClick={() => onCustomer({ ...customer, tool: 'summary' })}
                            >
                              Hồ sơ
                            </button>
                          </div>
                        </div>
                      );
                    })}

                    {filteredCustomers.length > 6 && (
                      <button
                        type="button"
                        className="agenda-expand-btn"
                        onClick={() => setShowAllCustomers((prev) => !prev)}
                      >
                        {showAllCustomers
                          ? 'Thu gọn'
                          : `Xem thêm ${filteredCustomers.length - 6} khách hàng`}
                      </button>
                    )}
                  </div>
                ) : (
                  <Empty>Không có khách hàng trong mục này.</Empty>
                )}
              </section>
            </div>

            {/* RIGHT: SCHEDULE & TASKS */}
            <div className="agenda-column">
              <Panel
                id="agenda-work-panel"
                title="Lịch trình & Công việc"
                action={<span className="agenda-muted-caption">{data.work_items.total} mục</span>}
              >
                <div className="agenda-filter-tabs" aria-label="Lọc công việc">
                  {Object.entries(filters).map(([value, label]) => {
                    const tabCount = workCounts[value];
                    return (
                      <button
                        type="button"
                        key={value}
                        className={filter === value ? 'is-active' : ''}
                        aria-pressed={filter === value}
                        onClick={() => changeFilter(value)}
                      >
                        <span>{label}</span>
                        {typeof tabCount === 'number' && <em>{tabCount}</em>}
                      </button>
                    );
                  })}
                </div>

                {data.work_items.items.length ? (
                  <div className="agenda-minimal-list">{data.work_items.items.map(row)}</div>
                ) : (
                  <div className="agenda-empty-work-fallback">
                    <p className="agenda-empty-inline">
                      {filter === 'today'
                        ? 'Hôm nay chưa có lịch cố định giờ.'
                        : 'Không có mục nào trong bộ lọc này.'}
                    </p>
                    {filter === 'today' && data.unscheduled.items.length > 0 && (
                      <div className="agenda-fallback-section">
                        <div className="agenda-fallback-header">
                          <span>Việc chưa xếp giờ ({data.unscheduled.total})</span>
                          <button
                            type="button"
                            className="agenda-inline-link"
                            onClick={() => changeFilter('unscheduled')}
                          >
                            Xem tất cả
                          </button>
                        </div>
                        <div className="agenda-minimal-list">
                          {data.unscheduled.items.slice(0, 4).map(row)}
                        </div>
                      </div>
                    )}
                  </div>
                )}

                {data.work_items.total > 10 && (
                  <div className="agenda-pagination">
                    <button
                      type="button"
                      className="agenda-btn-minimal"
                      aria-label="Trang trước"
                      disabled={data.work_items.page <= 1 || resource.loading}
                      onClick={() => setPage(data.work_items.page - 1)}
                    >
                      <ChevronLeft size={14} />
                    </button>
                    <span>
                      {data.work_items.page}/{Math.ceil(data.work_items.total / 10)}
                    </span>
                    <button
                      type="button"
                      className="agenda-btn-minimal"
                      aria-label="Trang sau"
                      disabled={data.work_items.page * 10 >= data.work_items.total || resource.loading}
                      onClick={() => setPage(data.work_items.page + 1)}
                    >
                      <ChevronRight size={14} />
                    </button>
                  </div>
                )}
              </Panel>

              <Panel
                title="Sự kiện sắp đến"
                action={
                  <button type="button" className="agenda-inline-link" onClick={() => onCalendar()}>
                    Lịch tuần <ArrowRight size={12} />
                  </button>
                }
              >
                {data.upcoming_events.length ? (
                  <div className="agenda-minimal-list">
                    {data.upcoming_events.map((item) => (
                      <button
                        type="button"
                        className="agenda-upcoming"
                        key={item.id}
                        onClick={() => onCalendar(item.starts_at)}
                      >
                        <span className="agenda-upcoming-body">
                          <strong>{item.title}</strong>
                          <small>
                            <Clock3 size={11} /> {formatDateTime(item.starts_at)} ·{' '}
                            {item.customer_name || 'Cá nhân'}
                            {item.location ? ` · ${item.location}` : ''}
                          </small>
                        </span>
                        <ChevronRight size={14} className="agenda-upcoming-chevron" />
                      </button>
                    ))}
                  </div>
                ) : (
                  <Empty>Chưa có sự kiện sắp đến.</Empty>
                )}
              </Panel>
            </div>
          </div>

          {/* ROW 4: COMPACT BOTTOM INSIGHTS (VEHICLE DEMAND + MESSAGE ACTIVITY) */}
          <div className="agenda-bottom-grid" id="agenda-portfolio">
            <Panel title="Nhu cầu theo dòng xe">
              <Bars
                rows={data.model_interest.map((item) => ({
                  ...item,
                  key: item.model,
                }))}
                label={(item) => item.model}
              />
            </Panel>

            <Panel
              title="Tần suất tương tác tin nhắn"
              action={
                <select
                  aria-label="Khoảng thời gian hoạt động"
                  value={days}
                  onChange={(event) => setDays(Number(event.target.value))}
                >
                  <option value={7}>7 ngày</option>
                  <option value={30}>30 ngày</option>
                </select>
              }
            >
              <div className="agenda-activity-header-row">
                <div className="agenda-legend">
                  <span>
                    <i className="customer" />
                    Khách ({totalCustomerMsgs})
                  </span>
                  <span>
                    <i className="sales" />
                    Sales ({totalSalesMsgs})
                  </span>
                </div>
                <span className="agenda-muted-caption">
                  TB {Math.round((totalCustomerMsgs + totalSalesMsgs) / days)} tin/ngày
                </span>
              </div>

              <div
                className="agenda-activity-chart"
                role="img"
                aria-label={`Số tin nhắn khách hàng và sales trong ${days} ngày`}
              >
                {data.message_activity.map((day, index) => (
                  <div
                    className="agenda-activity-day"
                    key={day.date}
                    title={`${day.date}: Khách ${day.customer}, Sales ${day.sales}`}
                  >
                    <span className="agenda-activity-total">{day.customer + day.sales || ''}</span>
                    <div className="agenda-activity-stack">
                      <span className="sales" style={{ height: `${(day.sales / activityMax) * 90}px` }} />
                      <span className="customer" style={{ height: `${(day.customer / activityMax) * 90}px` }} />
                    </div>
                    <small>
                      {days === 7 || index % 5 === 0 || index === days - 1
                        ? day.date.slice(5).split('-').reverse().join('/')
                        : ''}
                    </small>
                  </div>
                ))}
              </div>
            </Panel>
          </div>
        </>
      )}
    </div>
  );
}
