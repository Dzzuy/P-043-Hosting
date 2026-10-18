import { useCallback, useEffect, useMemo, useState } from 'react';
import { Lightbulb } from 'lucide-react';
import { ModeChooserDialog } from './ModeChooserDialog';
import { ScenarioCatalog } from './ScenarioCatalog';
import { PracticeRoom } from './PracticeRoom';
import { EvaluationScorecard } from './EvaluationScorecard';
import { HistoryModal } from './HistoryModal';
import { AdvisorAssignmentsView } from './AdvisorAssignmentsView';
import { AdvisorProgress } from './AdvisorProgress';
import { PracticeHistory } from './PracticeHistory';
import { useLoad } from '../../hooks/useLoad';
import './advisorProgress.css';
import { practiceApi } from '../../api/practiceApi';
import { apiErrorNotice } from '../../utils/practiceNotices';
import { NoticeDialog } from '../common/NoticeDialog';
import { authApi } from '../../api/authApi';
import { ErrorState } from '../common/ErrorState';

export function RoleplayView({ scenarios, scenarioStatus, onRetryScenarios, onOpenKnowledge }) {
  const [notice, setNotice] = useState(null);
  const [viewMode, setViewMode] = useState('catalog');
  const [activeScenario, setActiveScenario] = useState(null);
  const [activeSession, setActiveSession] = useState(null);
  const [evaluationResult, setEvaluationResult] = useState(null);
  const [attemptDetail, setAttemptDetail] = useState(null);
  const [detailStatus, setDetailStatus] = useState('idle');
  const [retryingEvaluation, setRetryingEvaluation] = useState(false);
  const [selectedSessionId, setSelectedSessionId] = useState(null);
  const [history, setHistory] = useState([]);
  const [historyStatus, setHistoryStatus] = useState('loading');
  const [historyError, setHistoryError] = useState('');
  const [historyScenarioId, setHistoryScenarioId] = useState(null);
  const [startError, setStartError] = useState('');
  const [pendingStart, setPendingStart] = useState(null);
  const [initialMode, setInitialMode] = useState('text');
  const [starting, setStarting] = useState(false);
  const [refreshToken, setRefreshToken] = useState(0);
  const progress = useLoad(() => practiceApi.getProgress(), `progress-${refreshToken}`, 'Không tải được tiến độ.');
  const assignmentsLoad = useLoad(() => practiceApi.getAssignments(), `assignments-${refreshToken}`, 'Không thể tải bài được giao.');

  const loadHistory = useCallback(async () => {
    setHistoryStatus('loading');
    setHistoryError('');
    try {
      setHistory(await practiceApi.getHistory());
      setHistoryStatus('ready');
    } catch (error) {
      setHistoryError(apiErrorNotice(error)?.message || apiErrorNotice(error)?.title || 'Vui lòng thử lại.');
      setNotice(apiErrorNotice(error));
      setHistoryStatus('error');
    }
  }, []);

  useEffect(() => {
    let mounted = true;
    practiceApi.getHistory().then((items) => {
      if (mounted) {
        setHistory(items);
        setHistoryStatus('ready');
      }
    }).catch((error) => {
      if (mounted) {
        setHistoryError(apiErrorNotice(error)?.message || apiErrorNotice(error)?.title || 'Vui lòng thử lại.');
        setNotice(apiErrorNotice(error));
        setHistoryStatus('error');
      }
    });
    return () => { mounted = false; };
  }, []);

  const latestByScenario = useMemo(() => {
    const latest = {};
    for (const attempt of history) {
      if (!latest[attempt.scenario_id]) latest[attempt.scenario_id] = attempt;
    }
    return latest;
  }, [history]);

  // Entry points open the mode chooser first; the session starts once a mode is picked.
  const requestStartScenario = (scenarioId, assignmentId = null) => {
    if (starting || !scenarios.some((item) => item.scenario_id === scenarioId)) return;
    setPendingStart({ scenarioId, assignmentId });
  };

  const startWithMode = (choice) => {
    if (!pendingStart) return;
    const { scenarioId, assignmentId } = pendingStart;
    setPendingStart(null);
    handleStartScenario(scenarioId, assignmentId, choice);
  };

  const handleStartScenario = async (scenarioId, assignmentId = null, mode = 'text') => {
    const scen = scenarios.find((s) => s.scenario_id === scenarioId);
    if (!scen || starting) return;
    setInitialMode(mode);
    setActiveScenario(scen);
    setStartError('');
    setStarting(true);
    try {
      const sessionView = await practiceApi.startSession(scen.scenario_id, assignmentId);
      setActiveSession(sessionView);
      setViewMode('room');
    } catch (error) {
      setStartError(apiErrorNotice(error)?.message || apiErrorNotice(error)?.title || 'Vui lòng thử lại.');
      setNotice(apiErrorNotice(error));
    } finally {
      setStarting(false);
    }
  };

  const handleFinishSession = (resultView) => {
    setEvaluationResult(resultView);
    setAttemptDetail(null);
    setViewMode('evaluation');
    loadHistory();
    setRefreshToken((value) => value + 1);
  };

  const handleBackToCatalog = () => {
    setViewMode('catalog');
    setActiveSession(null);
    setEvaluationResult(null);
    setAttemptDetail(null);
    loadHistory();
    setRefreshToken((value) => value + 1);
  };

  const openAttempt = async (sessionId) => {
    setHistoryScenarioId(null);
    setSelectedSessionId(sessionId);
    setDetailStatus('loading');
    setViewMode('attempt');
    try {
      const detail = await practiceApi.getAttempt(sessionId);
      setAttemptDetail(detail);
      setActiveScenario(scenarios.find((s) => s.scenario_id === detail.attempt.scenario_id) || null);
      setDetailStatus('ready');
    } catch (error) {
      setStartError(apiErrorNotice(error)?.message || apiErrorNotice(error)?.title || 'Vui lòng thử lại.');
      setNotice(apiErrorNotice(error));
      setDetailStatus('error');
    }
  };

  const retryFailedEvaluation = async () => {
    if (!attemptDetail || retryingEvaluation) return;
    setRetryingEvaluation(true);
    try {
      await practiceApi.finishSession(attemptDetail.attempt.session_id);
      setAttemptDetail(await practiceApi.getAttempt(attemptDetail.attempt.session_id));
      await loadHistory();
    } catch (error) {
      console.debug('Practice evaluation failed', { code: error.code, status: error.status });
      setNotice(apiErrorNotice(error));
    } finally {
      setRetryingEvaluation(false);
    }
  };

  const scenarioNames = useMemo(
    () => Object.fromEntries(scenarios.map((item) => [item.scenario_id, item.title])),
    [scenarios],
  );
  const approvedCount = progress.data?.approved_sessions;
  const visibleHistory = historyScenarioId ? history.filter((item) => item.scenario_id === historyScenarioId) : history;

  return (
    <div>
      {pendingStart && <ModeChooserDialog onClose={() => setPendingStart(null)} onChoose={startWithMode} />}
      <NoticeDialog notice={notice} onClose={() => setNotice(null)} onAction={async (id) => {
        setNotice(null);
        if (id === 'retry_finish') await retryFailedEvaluation();
        if (id === 'login') { try { await authApi.logout(); } finally { window.location.reload(); } }
      }} />
      {scenarioStatus === 'loading' && <p>Đang tải tình huống từ backend...</p>}
      {scenarioStatus === 'error' && <ErrorState message="Không tải được tình huống từ backend." onRetry={onRetryScenarios} />}
      {viewMode === 'catalog' && startError && <ErrorState message={startError} onRetry={() => handleStartScenario(activeScenario?.scenario_id, null, initialMode)} />}
      {viewMode === 'catalog' && (
        <div className="ap-page">
          <div className="ap-title">
            <div>
            <h1>Phòng luyện tập</h1>
            {approvedCount != null && (
              <p>{approvedCount} bài đã được quản lý duyệt. Điểm bên dưới chỉ tính các bài đó.</p>
            )}
            </div>
            <p className="ap-knowledge-tip">
              <Lightbulb size={16} aria-hidden="true" />
              <span>Để tư vấn tốt hơn, hãy ôn lại <button type="button" onClick={onOpenKnowledge}>Kho kiến thức</button>.</span>
            </p>
          </div>
          <div className="ap-top">
            <AdvisorProgress progress={progress} />
            <AdvisorAssignmentsView
              scenarios={scenarios}
              assignments={assignmentsLoad.data || []}
              status={assignmentsLoad.status}
              error={assignmentsLoad.error}
              onReload={assignmentsLoad.reload}
              onStart={(assignment) => requestStartScenario(assignment.scenario_id, assignment.assignment_id)}
            />
          </div>
          <ScenarioCatalog
            scenarios={scenarios}
            onStartScenario={requestStartScenario}
            onOpenHistory={setHistoryScenarioId}
            latestByScenario={latestByScenario}
            progressScenarios={progress.data?.scenarios || null}
            assignments={assignmentsLoad.data || []}
            starting={starting}
          />
          <div className="ap-lower ap-lower--single">
            <PracticeHistory
              history={history}
              status={historyStatus}
              error={historyError}
              onRetry={loadHistory}
              onSelectSession={openAttempt}
              scenarioNames={scenarioNames}
            />
          </div>
        </div>
      )}
      {viewMode === 'room' && (
        <PracticeRoom initialMode={initialMode} scenario={activeScenario} session={activeSession} onFinish={handleFinishSession} onSavedAttempt={openAttempt} onExit={handleBackToCatalog} />
      )}
      {viewMode === 'evaluation' && (
        <EvaluationScorecard result={evaluationResult} scenario={activeScenario} onRetry={() => requestStartScenario(activeScenario?.scenario_id)} onBackToCatalog={handleBackToCatalog} onOpenAttempt={openAttempt} />
      )}
      {viewMode === 'attempt' && (
        <div className="ap-page">
          <button type="button" className="ap-back" onClick={handleBackToCatalog}>Về thư viện tình huống</button>
          {detailStatus === 'loading' && <p className="ap-state" role="status">Đang tải phiên luyện tập…</p>}
          {detailStatus === 'error' && <ErrorState message={startError} onRetry={() => openAttempt(selectedSessionId)} />}
          {detailStatus === 'ready' && attemptDetail && (
            <>
              <section className="ap-card" aria-labelledby="ap-saved-h">
                <h2 id="ap-saved-h">Hội thoại đã lưu</h2>
                <ol className="ap-saved-chat">
                  {(attemptDetail.session.messages || []).map((message) => (
                    <li key={message.message_id} id={`message-${message.message_id}`} className={message.role === 'advisor' ? 'ap-from-advisor' : ''}>
                      <span className="ap-saved-who">{message.role === 'advisor' ? 'Bạn' : 'Khách hàng'}</span>
                      <div className="ap-saved-bubble">{message.content}</div>
                    </li>
                  ))}
                </ol>
              </section>
              {!attemptDetail.ai_evaluation.result && attemptDetail.session.termination_status !== 'active' ? (
                <div role="alert" className="ap-card">
                  <p>{attemptDetail.attempt.evaluation_status === 'pending'
                    ? 'Hội thoại đã lưu. Nếu việc chấm điểm bị gián đoạn, bạn có thể thử lại.'
                    : 'Phiên này đã lưu nhưng chấm điểm thất bại.'}</p>
                  <button type="button" className="ap-btn ap-btn--primary" onClick={retryFailedEvaluation} disabled={retryingEvaluation}>
                    {retryingEvaluation ? 'Đang chấm điểm lại…' : 'Thử chấm điểm lại'}
                  </button>
                </div>
              ) : (
                <EvaluationScorecard
                  result={{ ...attemptDetail.ai_evaluation, result: attemptDetail.manager_review?.approved_result || attemptDetail.ai_evaluation.result }}
                  scenario={activeScenario}
                  generalComment={attemptDetail.manager_review?.general_comment || null}
                  onRetry={() => requestStartScenario(attemptDetail.attempt.scenario_id)}
                  onBackToCatalog={handleBackToCatalog}
                  showTranscriptLinks
                />
              )}
            </>
          )}
        </div>
      )}
      <HistoryModal
        isOpen={historyScenarioId !== null}
        onClose={() => setHistoryScenarioId(null)}
        attempts={visibleHistory}
        status={historyStatus}
        error={historyError}
        onRetry={loadHistory}
        onSelectSession={openAttempt}
      />
    </div>
  );
}
