import { fmtDayMonth, fmtScore } from '../../utils/scoreFormat';
import './advisorProgress.css';

// App.jsx may already have relabelled difficulty to Cơ bản, Tiêu chuẩn or Nâng cao.
const DIFFICULTY = {
  Easy: 'Dễ', Medium: 'Trung bình', Hard: 'Khó', 'Cơ bản': 'Dễ', 'Tiêu chuẩn': 'Trung bình', 'Nâng cao': 'Khó',
};

/** Scenario -> official transparent VinFast exterior photo. */
function carFor(scenario) {
  if (scenario.scenario_id === 'SCENARIO_03_VF6_APARTMENT') return { src: '/vehicles/official/vf-6-green.webp', alt: 'VinFast VF 6 màu xanh', width: 200, height: 106 };
  const match = /VF[\s_-]*(Wild|[356789])(?![a-z0-9])/i.exec(`${scenario.model_badge || ''} ${scenario.model || ''} ${scenario.scenario_id} ${scenario.title}`);
  if (!match) return null;
  const model = match[1].toLowerCase();
  return { src: `/vehicles/official/vf-${model}.webp`, alt: `VinFast VF ${model === 'wild' ? 'Wild' : model}`, width: 200, height: 106 };
}

/** The customer's quoted opening line inside visible_context, else the whole context. */
function openingLine(context) {
  const text = String(context || '').trim();
  const quoted = /['‘“"](.+)['’”"]/s.exec(text);
  return quoted ? { text: quoted[1].trim(), quoted: true } : { text, quoted: false };
}

function lastResult(entry, latest) {
  if (entry) {
    if (entry.last_status === 'approved') {
      const day = fmtDayMonth(entry.last_completed_at);
      return `Lần gần nhất ${fmtScore(entry.last_score)} / 3${day ? `, ngày ${day}` : ''}`;
    }
    if (entry.last_status === 'pending_review') {
      return `Đang chờ quản lý duyệt${entry.last_score != null ? `, AI chấm ${fmtScore(entry.last_score)} / 3` : ''}`;
    }
    if (entry.last_status === 'failed') return 'Lần gần nhất chấm điểm thất bại';
    return 'Chưa luyện tình huống này';
  }
  if (latest) return `Lần gần nhất ${fmtScore(latest.approved_score ?? latest.ai_score)} / 3`;
  return 'Chưa luyện tình huống này';
}

export function ScenarioCatalog({
  scenarios, onStartScenario, onOpenHistory, latestByScenario = {}, progressScenarios = null, assignments = [], starting = false,
}) {
  const assignedFor = (scenarioId) => assignments
    .filter((item) => item.scenario_id === scenarioId && item.status !== 'completed')
    .sort((a, b) => String(a.due_date || '9999').localeCompare(String(b.due_date || '9999')))[0];

  return (
    <section className="ap-card" aria-labelledby="ap-library-h">
      <div className="ap-card-head">
        <h2 id="ap-library-h">Thư viện tình huống</h2>
      </div>
      {scenarios.length === 0 ? <p className="ap-state">Chưa có tình huống nào.</p> : (
        <ul className="ap-scenarios">
          {scenarios.map((scenario) => {
            const car = carFor(scenario);
            const opening = openingLine(scenario.visible_context);
            const assigned = assignedFor(scenario.scenario_id);
            const due = assigned?.due_date ? fmtDayMonth(`${assigned.due_date}T00:00:00`) : '';
            // Scenarios whose acceptable outcomes include an upsell get the "Luyện Upsale!" sticker.
            const upsell = (scenario.outcome_labels || []).some((label) => /upsell/i.test(label));
            return (
              <li className="ap-scenario" key={scenario.scenario_id}>
                {upsell && <span className="ap-upsell">Luyện Upsale!</span>}
                <div className="ap-scenario-media">
                  {car && <img src={car.src} alt={car.alt} width={car.width} height={car.height} loading="lazy" />}
                  <button type="button" className="ap-btn ap-btn--primary" onClick={() => onStartScenario(scenario.scenario_id)} disabled={starting}>
                    Vào phòng luyện tập
                  </button>
                </div>
                <div className="ap-scenario-body">
                  <div className="ap-scenario-top">
                    <h3>{scenario.title}</h3>
                    <span className="ap-level">{DIFFICULTY[scenario.difficulty] || scenario.difficulty}</span>
                  </div>
                  <p className="ap-opening">{opening.quoted ? `“${opening.text}”` : opening.text}</p>
                  {assigned && <p className="ap-assigned">Quản lý giao{due ? `, hạn ${due}` : ''}</p>}
                  <div className="ap-scenario-foot">
                    <span className="ap-last">{lastResult(progressScenarios?.[scenario.scenario_id], latestByScenario[scenario.scenario_id])}</span>
                    <button type="button" className="ap-text-btn" onClick={() => onOpenHistory(scenario.scenario_id)}>Lịch sử</button>
                  </div>
                </div>
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}
