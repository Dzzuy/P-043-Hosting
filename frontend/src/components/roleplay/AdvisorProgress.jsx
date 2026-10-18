import { useState } from 'react';
import { Info } from 'lucide-react';
import { SkillHelpDialog } from './SkillHelpDialog';
import { CRITERIA, fmtDelta, fmtScore, sparkPoints } from '../../utils/scoreFormat';
import './advisorProgress.css';

function changeLine(change) {
  if (change == null) return null;
  const rounded = Math.round(change * 10) / 10;
  if (rounded === 0) return 'Giữ nguyên so với 8 tuần trước';
  return `${rounded > 0 ? 'Tăng' : 'Giảm'} ${fmtScore(Math.abs(rounded))} điểm so với 8 tuần trước`;
}

export function AdvisorProgress({ progress }) {
  const { status, data, error, reload } = progress;
  return (
    <section className="ap-card ap-progress" aria-labelledby="ap-score-h">
      {status === 'loading' && <p className="ap-state" role="status">Đang tải tiến độ của bạn…</p>}
      {status === 'error' && (
        <p className="ap-state ap-state--error" role="alert">
          {error || 'Không tải được tiến độ.'} <button type="button" className="ap-link" onClick={reload}>Thử lại</button>
        </p>
      )}
      {status === 'ready' && data && data.approved_sessions === 0 && (
        <div className="ap-empty">
          <h2 id="ap-score-h">Điểm của bạn</h2>
          <p className="ap-state">Chưa có bài nào được quản lý duyệt. Hoàn thành một tình huống bên dưới, điểm sẽ hiện ở đây sau khi được duyệt.</p>
        </div>
      )}
      {status === 'ready' && data && data.approved_sessions > 0 && <ProgressBody data={data} />}
    </section>
  );
}

function ProgressBody({ data }) {
  const [showSkillHelp, setShowSkillHelp] = useState(false);
  const trend = data.trend || [];
  const values = trend.map((item) => numeric(item.avg_score));
  const runs = sparkPoints(values, 280, 70, 4);
  const filled = values.filter((value) => value != null);
  const lastPoint = runs.flat().slice(-1)[0];
  const headline = data.current_week_avg ?? data.overall_avg;
  const change = changeLine(data.change_8w);
  return (
    <>
      <div className="ap-score">
        <h2 id="ap-score-h">Điểm của bạn</h2>
        <div className="ap-score-value">
          <strong>{fmtScore(headline)}</strong>
          <span>{data.current_week_avg != null ? '/ 3 ở tuần này' : '/ 3 trung bình'}</span>
        </div>
        {change && <p className="ap-change">{change}</p>}
        {filled.length > 0 && (
          <svg
            role="img"
            aria-label={`Điểm theo tuần: ${filled.map((value) => fmtScore(value)).join('; ')}`}
            viewBox="-8 -8 296 86"
            className="ap-spark"
          >
            <line x1="0" y1="35" x2="280" y2="35" className="ap-spark-ref" />
            {runs.map((run) => (
              run.length > 1 ? <polyline key={`${run[0].x}-${run.length}`} fill="none" points={run.map((point) => `${point.x},${point.y}`).join(' ')} /> : null
            ))}
            {lastPoint && <circle cx={lastPoint.x} cy={lastPoint.y} r="5" />}
          </svg>
        )}
        <span className="ap-caption">{trend.length} tuần, đường gạch là mức 2 (chuẩn chuyên nghiệp)</span>
      </div>

      <div className="ap-skills">
        <div className="ap-skills-heading"><h2>Từng kỹ năng</h2><button type="button" className="ap-skills-info" aria-label="Giải thích 5 kỹ năng tư vấn" aria-haspopup="dialog" onClick={() => setShowSkillHelp(true)}><Info size={16} aria-hidden="true" /></button></div>
        {showSkillHelp && <SkillHelpDialog onClose={() => setShowSkillHelp(false)} />}
        <SkillRadar criteria={data.criteria} />
      </div>
    </>
  );
}

function numeric(value) {
  return value != null && value !== '' && Number.isFinite(Number(value)) ? Number(value) : null;
}

function radarPoint(index, score) {
  if (score == null) return null;
  const angle = -Math.PI / 2 + index * Math.PI * 2 / CRITERIA.length;
  const radius = Math.min(3, Math.max(0, score)) / 3 * 80;
  return { x: 180 + Math.cos(angle) * radius, y: 145 + Math.sin(angle) * radius };
}

function pointList(points) {
  return points.map((point) => `${point.x},${point.y}`).join(' ');
}

function partialPath(points) {
  // Missing axes remain gaps instead of suggesting a zero or invented score.
  let path = points.map((point, index) => point ? `${index && points[index - 1] ? 'L' : 'M'}${point.x},${point.y}` : '').join(' ');
  if (points[0] && points.at(-1)) path += ` M${points.at(-1).x},${points.at(-1).y} L${points[0].x},${points[0].y}`;
  return path;
}

function SkillRadar({ criteria }) {
  const skills = CRITERIA.map((criterion) => ({ ...criterion, score: numeric(criteria?.[criterion.key]?.latest_avg), delta: numeric(criteria?.[criterion.key]?.change_4w) }));
  const current = skills.map((skill, index) => radarPoint(index, skill.score));
  const previous = skills.map((skill, index) => radarPoint(index, skill.score != null && skill.delta != null ? skill.score - skill.delta : null));
  const hasPrevious = previous.every(Boolean);
  const summary = skills.map((skill) => `${skill.label}: ${skill.score == null ? 'chưa có điểm' : `${fmtScore(skill.score)} trên 3`}${skill.delta == null ? '' : `, thay đổi ${fmtDelta(skill.delta)} so với 4 tuần trước`}`).join('; ');
  const labels = ['Nhu cầu', 'Sản phẩm', 'Phản đối', 'Chính sách', 'Chốt bước'];
  const positions = [{ x: 180, y: 30 }, { x: 310, y: 110 }, { x: 255, y: 230 }, { x: 105, y: 230 }, { x: 50, y: 110 }];
  if (!current.some(Boolean)) return <p className="ap-state">Chưa đủ dữ liệu từng kỹ năng.</p>;
  return <>
    <div className="ap-radar-frame">
      <svg viewBox="0 0 360 260" className="ap-radar" role="img" aria-label={summary}>
        {[1, 2, 3].map((level) => <polygon key={level} points={pointList(skills.map((_, index) => radarPoint(index, level)))} className="ap-radar-grid" />)}
        {skills.map((skill, index) => { const end = radarPoint(index, 3); return <line key={skill.key} x1="180" y1="145" x2={end.x} y2={end.y} className="ap-radar-axis" />; })}
        <text x="185" y="141" className="ap-radar-tick">0</text>
        {[1, 2, 3].map((level) => <text key={level} x="185" y={145 - level * 80 / 3 + 4} className="ap-radar-tick">{level}</text>)}
        {hasPrevious && <g><polygon points={pointList(previous)} className="ap-radar-previous" />{previous.map((point, index) => <circle key={skills[index].key} cx={point.x} cy={point.y} r="2.5" className="ap-radar-previous-dot" />)}</g>}
        <g className="ap-radar-current">
          {current.every(Boolean) ? <polygon points={pointList(current)} className="ap-radar-area" /> : <path d={partialPath(current)} className="ap-radar-partial" />}
          {current.map((point, index) => point && <circle key={skills[index].key} cx={point.x} cy={point.y} r="5" />)}
        </g>
        {skills.map((skill, index) => {
          const { x, y } = positions[index];
          return <text key={skill.key} x={x} y={y} textAnchor="middle" className="ap-radar-label">
            <title>{skill.label}</title>
            <tspan x={x}>{labels[index]}</tspan>
            <tspan x={x} dy="18" className="ap-radar-score">{fmtScore(skill.score)}</tspan>{skill.delta != null && <tspan dx="6" className="ap-radar-delta">{fmtDelta(skill.delta)}</tspan>}
          </text>;
        })}
      </svg>
    </div>
    <ul className="ap-sr-only">{skills.map((skill) => <li key={skill.key}>{skill.label}: {fmtScore(skill.score)} / 3{skill.delta != null && `; ${fmtDelta(skill.delta)} so với 4 tuần trước`}</li>)}</ul>
    <div className="ap-radar-legend"><span><i className="ap-legend-current" aria-hidden="true" />Hiện tại</span>{hasPrevious && <span><i className="ap-legend-previous" aria-hidden="true" />4 tuần trước</span>}</div>
  </>;
}
