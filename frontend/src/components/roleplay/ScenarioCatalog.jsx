import { useState } from 'react';
import { ArrowRight, ClockIcon, TargetIcon, UsersIcon } from '../common/Icons';
import { SKILL_LABELS } from '../../data/scenarioData';
import { getVehicleImage } from '../../data/vehicleData';

export function ScenarioCatalog({ scenarios, onStartScenario, onOpenHistory, latestByScenario = {}, starting = false }) {
  const [filterModel, setFilterModel] = useState('all');
  const [filterDifficulty, setFilterDifficulty] = useState('all');
  const models = [...new Set(scenarios.map((scenario) => scenario.model).filter(Boolean))];
  const difficulties = ['Cơ bản', 'Tiêu chuẩn', 'Nâng cao'];
  const filtered = scenarios.filter((scenario) =>
    (filterModel === 'all' || scenario.model === filterModel)
    && (filterDifficulty === 'all' || scenario.difficulty === filterDifficulty));

  return (
    <section className="practice-catalog" aria-label="Chọn tình huống luyện tập">
      <div className="practice-filters">
        <div className="practice-filter-group">
          <strong>Dòng xe:</strong>
          <button type="button" className={filterModel === 'all' ? 'selected' : ''} onClick={() => setFilterModel('all')}>Tất cả mẫu xe</button>
          {models.map((model) => <button type="button" key={model} className={filterModel === model ? 'selected' : ''} onClick={() => setFilterModel(model)}>{model}</button>)}
        </div>
        <div className="practice-filter-group">
          <strong>Độ khó:</strong>
          <button type="button" className={filterDifficulty === 'all' ? 'selected' : ''} onClick={() => setFilterDifficulty('all')}>Tất cả</button>
          {difficulties.map((difficulty) => <button type="button" key={difficulty} className={filterDifficulty === difficulty ? 'selected' : ''} onClick={() => setFilterDifficulty(difficulty)}>{difficulty}</button>)}
        </div>
      </div>
      {filtered.length === 0 ? <p className="practice-no-scenarios">Không có tình huống phù hợp với bộ lọc.</p> : (
        <div className="practice-scenario-grid">
          {filtered.map((scenario) => {
            const image = getVehicleImage(scenario.model || scenario.title);
            const latest = latestByScenario[scenario.scenario_id];
            return (
              <article className="practice-scenario-card" key={scenario.scenario_id}>
                <div className="practice-scenario-head">
                  <div className="practice-scenario-badges">
                    <span className="practice-model-badge">{scenario.model}</span>
                    <span className="practice-difficulty-badge">Độ khó: {scenario.difficulty}</span>
                  </div>
                  {image && <img className="practice-vehicle-image" src={image} alt={scenario.model} />}
                </div>
                <h2>{scenario.title}</h2>
                {latest && <p className="practice-latest">Kết quả gần nhất: {latest.approved_score ?? latest.ai_score ?? '—'} / 3</p>}
                <div className="practice-scenario-details">
                  <div><UsersIcon aria-hidden="true" /><p><strong>Khách hàng mục tiêu</strong><span>{scenario.visible_context}</span></p></div>
                  <div><TargetIcon aria-hidden="true" /><p><strong>Mục tiêu</strong><span>{scenario.training_objective}</span></p></div>
                </div>
                <div className="practice-skill-list">
                  {(scenario.target_skills || []).map((skill) => <span key={skill}>{SKILL_LABELS[skill] || skill}</span>)}
                </div>
                <div className="practice-scenario-footer">
                  <span>Khai thác nhu cầu trong hội thoại</span>
                  <div className="practice-scenario-actions">
                    <button type="button" className="practice-history-button" onClick={() => onOpenHistory(scenario.scenario_id)}><ClockIcon aria-hidden="true" /> Lịch sử</button>
                    <button type="button" className="practice-start-button" onClick={() => onStartScenario(scenario.scenario_id)} disabled={starting}>Vào phòng luyện tập <ArrowRight aria-hidden="true" /></button>
                  </div>
                </div>
              </article>
            );
          })}
        </div>
      )}
    </section>
  );
}
