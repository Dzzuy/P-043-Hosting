import { ArrowRight, BookIcon, ChevronRight, ProgressIcon } from '../common/Icons';
import { CopilotLogo } from '../common/CopilotLogo';
import { getVehicleImage } from '../../data/vehicleData';

const quickActions = [
  {
    id: 'copilot',
    title: 'Trợ lý Copilot',
    description: 'Tra cứu thông số, so sánh xe và tình huống tư vấn nhanh chóng.',
    action: 'Mở Copilot',
    icon: <CopilotLogo style={{ width: 27, height: 27 }} />,
  },
  {
    id: 'roleplay',
    title: 'Thực chiến',
    description: 'Mô phỏng tư vấn khách hàng với AI, bám sát tình huống thực tế.',
    action: 'Chọn kịch bản',
    icon: <span className="roleplay-file-icon" aria-hidden="true" />,
  },
  {
    id: 'knowledge',
    title: 'Cẩm nang sản phẩm',
    description: 'Thông số, tính năng và điểm khác biệt của các dòng xe VinFast.',
    action: 'Xem tài liệu',
    icon: <BookIcon style={{ width: 27, height: 27 }} />,
  },
];

export function HomeView({ scenarios, scenarioStatus, onRetryScenarios, onNavigate }) {
  const recommendedScenarios = scenarios.slice(0, 3);

  return (
    <div className="advisor-home">
      <section className="home-hero" aria-label="Chào mừng">
        <div className="home-hero-content">
          <span className="home-hero-eyebrow">AI SALES COACH &amp; CO-PILOT</span>
          <h1>Chúc bạn một ngày tư vấn bứt phá!</h1>
          <p>Luyện tập thông minh hơn. Tư vấn tự tin hơn. Chinh phục nhiều khách hàng hơn.</p>
        </div>
      </section>

      <section className="home-quick" aria-labelledby="home-quick-title">
        <div className="home-section-heading">
          <h2 id="home-quick-title">Chọn công cụ</h2>
        </div>
        <div className="home-quick-grid">
          {quickActions.map((item) => (
            <button className={`home-quick-card home-quick-${item.id}`} key={item.id} type="button" onClick={() => onNavigate(item.id)}>
              <span className="home-quick-icon">{item.icon}</span>
              <span className="home-quick-copy">
                <strong>{item.title}</strong>
                <span>{item.description}</span>
                <span className="home-quick-link">{item.action} <ArrowRight style={{ width: 16, height: 16 }} /></span>
              </span>
              <ChevronRight className="home-quick-chevron" style={{ width: 18, height: 18 }} />
            </button>
          ))}
        </div>
      </section>

      <div className="home-lower-grid">
        <section className="home-scenarios" aria-labelledby="home-scenarios-title">
          <div className="home-section-heading home-section-heading-split">
            <div>
              <h2 id="home-scenarios-title">Kịch bản đề xuất</h2>
              <p>Các tình huống hiện có để bạn bắt đầu luyện tập</p>
            </div>
            <button type="button" className="home-text-link" onClick={() => onNavigate('roleplay')}>
              Xem tất cả <ArrowRight style={{ width: 16, height: 16 }} />
            </button>
          </div>

          {scenarioStatus === 'loading' && <div className="home-state" role="status">Đang tải kịch bản…</div>}
          {scenarioStatus === 'error' && (
            <div className="home-state" role="alert">
              <span>Không tải được kịch bản.</span>
              <button type="button" onClick={onRetryScenarios}>Thử lại</button>
            </div>
          )}
          {scenarioStatus === 'ready' && recommendedScenarios.length === 0 && (
            <div className="home-state">Hiện chưa có kịch bản để đề xuất.</div>
          )}
          {scenarioStatus === 'ready' && recommendedScenarios.length > 0 && (
            <div className="home-scenario-list">
              {recommendedScenarios.map((scenario) => {
                const model = scenario.model_badge || scenario.model || 'VinFast';
                const image = getVehicleImage(model);
                return (
                  <article className="home-scenario-card" key={scenario.scenario_id}>
                    <div className="home-scenario-copy">
                      <div className="home-scenario-badges">
                        <span className="home-model-badge">{model}</span>
                        {scenario.difficulty && <span className="home-difficulty-badge">Độ khó: {scenario.difficulty}</span>}
                      </div>
                      <h3>{scenario.title}</h3>
                    </div>
                    {image && <img className="home-scenario-image" src={image} alt={model} />}
                    <button type="button" onClick={() => onNavigate('roleplay')}>Chọn kịch bản <ArrowRight style={{ width: 16, height: 16 }} /></button>
                  </article>
                );
              })}
            </div>
          )}
        </section>

        <aside className="home-progress" aria-labelledby="home-progress-title">
          <div className="home-progress-heading">
            <span className="home-progress-icon"><ProgressIcon style={{ width: 25, height: 25 }} /></span>
            <div>
              <h2 id="home-progress-title">Theo dõi tiến độ</h2>
              <p>Xem kết quả từ các phiên thực chiến của bạn</p>
            </div>
          </div>
          <div className="home-progress-empty">
            <p>Điểm kỹ năng và bằng chứng được hiển thị sau khi bạn hoàn thành một phiên thực chiến. Trang chủ hiện chưa có số liệu tiến độ tổng hợp.</p>
            <button type="button" onClick={() => onNavigate('roleplay')}>Đến Thực chiến <ArrowRight style={{ width: 16, height: 16 }} /></button>
          </div>
        </aside>
      </div>
    </div>
  );
}
