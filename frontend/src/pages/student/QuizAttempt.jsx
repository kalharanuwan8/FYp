import { useState, useEffect, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { ArrowLeft, Check, Play } from 'lucide-react';
import { quizService } from '../../services/quizService';
import WebcamCapture from '../../components/monitoring/WebcamCapture';
import InterventionOverlay from '../../components/intervention/InterventionOverlay';
import { useMonitoringSession } from '../../hooks/useMonitoringSession';
import { usePreferences } from '../../context/PreferencesContext';
import { celebrateIfAllowed } from '../../utils/celebrate';
import { Button, Card, LoadingSpinner, ErrorBanner, XPChip } from '../../components/common';

export default function QuizAttempt() {
  const { quizId } = useParams();
  const navigate = useNavigate();
  const { reduceMotion } = usePreferences();

  const [quiz, setQuiz] = useState(null);
  const [attemptId, setAttemptId] = useState(null);
  const [answers, setAnswers] = useState({});
  const [qIndex, setQIndex] = useState(0);
  const [phase, setPhase] = useState('loading');
  const [result, setResult] = useState(null);
  const [pastAttempt, setPastAttempt] = useState(null);
  const [error, setError] = useState(null);
  const [submitting, setSubmitting] = useState(false);
  const [feedback, setFeedback] = useState(null);
  const [activeIntervention, setActiveIntervention] = useState(null);
  const [monitorEnabled, setMonitorEnabled] = useState(false);
  const [remediationChoice, setRemediationChoice] = useState(null);
  const [remediationBusy, setRemediationBusy] = useState(false);
  const [selectedOffer, setSelectedOffer] = useState(null);

  const onIntervention = useCallback((intervention) => {
    setActiveIntervention(intervention);
  }, []);

  const {
    webcamRef,
    canvasRef,
    cameraActive,
    activeSession,
    startMonitoredSession,
    stopMonitoredSession,
  } = useMonitoringSession({
    intervalMs: 2000,
    onIntervention,
    isQuizContext: true,
  });

  useEffect(() => {
    if (!quizId) return;
    (async () => {
      setPhase('loading');
      try {
        const quizData = await quizService.getQuizDetail(quizId);
        setQuiz(quizData);
        try {
          const attempts = await quizService.listQuizAttempts(quizId);
          const completed = (attempts || []).find((a) => a.completed_at !== null);
          if (completed) setPastAttempt(completed);
        } catch {
          /* optional */
        }
        setPhase('intro');
      } catch (err) {
        setError(err.response?.data?.error || 'Failed to load quiz.');
        setPhase('error');
      }
    })();
  }, [quizId]);

  const questions = quiz?.questions || [];
  const current = questions[qIndex];
  const totalQuestions = questions.length;

  const handleStartAttempt = async () => {
    setError(null);
    setSubmitting(true);
    try {
      const data = await quizService.startAttempt(quizId);
      setAttemptId(data.attempt_id);
      setQIndex(0);
      setPhase('in_progress');
      if (quiz?.module_id) {
        const mon = await startMonitoredSession(quiz.module_id);
        if (mon?.ok) setMonitorEnabled(true);
      }
    } catch (err) {
      setError(err.response?.data?.error || 'Failed to start quiz.');
    } finally {
      setSubmitting(false);
    }
  };

  const handleInterventionResponse = async (interventionId, userResponse, extra = {}) => {
    if (extra.dismiss_only) {
      setActiveIntervention(null);
      return null;
    }
    if (!activeSession) {
      setActiveIntervention(null);
      return null;
    }
    try {
      const { default: sessionService } = await import('../../services/sessionService');
      const res = await sessionService.recordInterventionResponse(
        activeSession.session_id,
        interventionId,
        userResponse,
        extra
      );
      if (!extra.defer_clear) setActiveIntervention(null);
      return res;
    } catch {
      setActiveIntervention(null);
      return null;
    }
  };

  const handleRemediationChoice = async (offer) => {
    const remediation = result?.remediation;
    if (!remediation?.event_id || !offer?.kind) return;
    setRemediationBusy(true);
    try {
      await quizService.recordRemediationChoice(remediation.event_id, offer.kind);
      setRemediationChoice(offer.kind);
      setSelectedOffer(offer);
      if (offer.kind === 'alternative_material' && (offer.content_id || offer.file_url)) {
        const apiBase = import.meta.env.VITE_API_BASE_URL || 'http://localhost:5000/api';
        const token = localStorage.getItem('access_token') || '';
        const url = offer.content_id
          ? `${apiBase}/courses/materials/${offer.content_id}/file?token=${encodeURIComponent(token)}`
          : offer.file_url;
        window.open(url, '_blank', 'noopener,noreferrer');
      }
    } catch (err) {
      setError(err.response?.data?.error || 'Could not save your choice.');
    } finally {
      setRemediationBusy(false);
    }
  };

  // Ends the monitored session only; the quiz attempt itself carries on.
  const handleStopMonitoring = async () => {
    setActiveIntervention(null);
    try {
      await stopMonitoredSession();
    } catch {
      /* ignore */
    }
    setMonitorEnabled(false);
    setFeedback({ type: 'gentle', text: 'Monitoring stopped. You can finish the quiz as normal.' });
  };

  const selectOption = (questionId, optionId) => {
    setAnswers((prev) => ({
      ...prev,
      [questionId]: { question_id: questionId, selected_option_id: optionId },
    }));
    setFeedback({ type: 'gentle', text: 'Got it — tap Next when ready.' });
  };

  const setShortAnswer = (questionId, text) => {
    setAnswers((prev) => ({
      ...prev,
      [questionId]: { question_id: questionId, answer_text: text },
    }));
  };

  const goBack = () => {
    setFeedback(null);
    setQIndex((i) => Math.max(0, i - 1));
  };

  const answeredCount = questions.filter((q) => {
    const a = answers[q.id];
    return a?.selected_option_id || (a?.answer_text || '').trim();
  }).length;

  const goNext = async () => {
    setFeedback(null);
    if (qIndex < totalQuestions - 1) {
      setQIndex((i) => i + 1);
      return;
    }
    // Submit
    if (!attemptId) return;
    setSubmitting(true);
    try {
      const graded = await quizService.submitAttempt(attemptId, {
        answers: Object.values(answers),
      });
      setResult(graded);
      setPhase('submitted');
      if (graded.xp_gained) {
        await celebrateIfAllowed({ reduceMotion });
      }
      if (monitorEnabled) {
        try {
          await stopMonitoredSession();
        } catch {
          /* ignore */
        }
        setMonitorEnabled(false);
      }
    } catch (err) {
      setError(err.response?.data?.error || 'Failed to submit quiz.');
    } finally {
      setSubmitting(false);
    }
  };

  if (phase === 'loading') return <LoadingSpinner label="Loading quiz…" />;

  if (phase === 'error') {
    return (
      <div className="max-w-xl mx-auto space-y-4">
        <button
          type="button"
          onClick={() => navigate(-1)}
          className="text-sm font-semibold text-primary flex items-center gap-1 min-h-11"
        >
          <ArrowLeft className="w-4 h-4" /> Back
        </button>
        <ErrorBanner message={error} />
      </div>
    );
  }

  return (
    <div className="learning-shell max-w-xl mx-auto space-y-6 animate-fade-in px-1">
      <button
        type="button"
        onClick={() => navigate(-1)}
        className="text-sm font-semibold text-text-muted flex items-center gap-1 min-h-11 cursor-pointer"
      >
        <ArrowLeft className="w-4 h-4" /> Back
      </button>

      <InterventionOverlay
        intervention={activeIntervention}
        onRespond={handleInterventionResponse}
        inlineHint
      />

      {phase === 'intro' && quiz && (
        <Card className="p-6 md:p-8 space-y-5 bg-learning">
          <h1 className="font-display text-2xl font-bold text-text">{quiz.title}</h1>
          <p className="text-text-muted">
            {totalQuestions} question{totalQuestions === 1 ? '' : 's'} · one at a time
          </p>
          {error && <ErrorBanner message={error} />}
          {pastAttempt ? (
            <div className="rounded-2xl bg-mint/15 border border-mint/30 p-4 text-sm space-y-3">
              <p className="font-semibold text-text">You have completed this quiz.</p>
              <p className="text-text-muted">Your score was {pastAttempt.score}%. Nice work finishing it.</p>
              <Button variant="secondary" onClick={() => navigate(-1)}>
                Back to lesson
              </Button>
            </div>
          ) : (
            <Button size="lg" onClick={handleStartAttempt} disabled={submitting}>
              <Play className="w-4 h-4" />
              {submitting ? 'Starting…' : 'Start quiz'}
            </Button>
          )}
        </Card>
      )}

      {phase === 'in_progress' && current && (
        <div className="space-y-5">
          {monitorEnabled && (
            <div className="flex items-center gap-3 text-sm text-text-muted">
              <WebcamCapture
                videoRef={webcamRef}
                canvasRef={canvasRef}
                cameraActive={cameraActive}
                compact
              />
              <span className="flex-1">Camera on for helpful hints · stays private</span>
              <Button variant="ghost" size="sm" onClick={handleStopMonitoring}>
                Stop monitoring
              </Button>
            </div>
          )}

          <div className="space-y-2">
            <div className="flex items-center justify-between gap-3 text-sm">
              <p className="font-semibold text-text">
                Question {qIndex + 1} of {totalQuestions}
              </p>
              <p className="text-text-muted">
                {answeredCount} answered · {totalQuestions - answeredCount} to go
              </p>
            </div>
            <div
              className="h-3 rounded-full bg-border overflow-hidden"
              role="progressbar"
              aria-valuemin={0}
              aria-valuemax={totalQuestions}
              aria-valuenow={qIndex + 1}
              aria-label={`Question ${qIndex + 1} of ${totalQuestions}`}
            >
              <div
                className="h-full bg-primary rounded-full transition-all"
                style={{ width: `${((qIndex + 1) / totalQuestions) * 100}%` }}
              />
            </div>
            <div className="flex justify-center gap-2" aria-hidden="true">
              {questions.map((_, i) => (
                <span
                  key={i}
                  className={`w-2.5 h-2.5 rounded-full ${
                    i === qIndex ? 'bg-primary' : i < qIndex ? 'bg-success' : 'bg-border'
                  }`}
                />
              ))}
            </div>
          </div>

          <Card className="p-6 md:p-8 space-y-5 bg-learning shadow-soft">
            <h2 className="font-display text-xl md:text-2xl font-bold text-text leading-snug">
              {current.question_text}
            </h2>

            {current.question_type === 'multiple_choice' ? (
              <div
                className="space-y-2"
                role="radiogroup"
                aria-label={current.question_text}
                onKeyDown={(e) => {
                  if (!['ArrowDown', 'ArrowRight', 'ArrowUp', 'ArrowLeft'].includes(e.key)) return;
                  const opts = current.options || [];
                  if (opts.length === 0) return;
                  e.preventDefault();
                  const currentIdx = opts.findIndex(
                    (o) => o.id === answers[current.id]?.selected_option_id
                  );
                  const delta = e.key === 'ArrowDown' || e.key === 'ArrowRight' ? 1 : -1;
                  const nextIdx =
                    currentIdx === -1
                      ? 0
                      : (currentIdx + delta + opts.length) % opts.length;
                  selectOption(current.id, opts[nextIdx].id);
                }}
              >
                {(current.options || []).map((opt) => {
                  const selected = answers[current.id]?.selected_option_id === opt.id;
                  return (
                    <button
                      key={opt.id}
                      type="button"
                      role="radio"
                      aria-checked={selected}
                      onClick={() => selectOption(current.id, opt.id)}
                      className={`w-full text-left min-h-14 px-4 py-3 rounded-2xl border text-base cursor-pointer transition-colors flex items-center gap-3 ${
                        selected
                          ? 'border-primary border-2 bg-primary-soft font-semibold text-text'
                          : 'border-border bg-bg hover:border-primary/40 font-medium text-text'
                      }`}
                    >
                      <span
                        className={`w-5 h-5 rounded-full border-2 flex items-center justify-center shrink-0 ${
                          selected
                            ? 'border-primary bg-primary text-on-primary'
                            : 'border-border text-transparent'
                        }`}
                        aria-hidden="true"
                      >
                        <Check className="w-3 h-3" />
                      </span>
                      <span className="flex-1">{opt.option_text}</span>
                      {selected && <span className="text-xs font-bold text-primary">Selected</span>}
                    </button>
                  );
                })}
              </div>
            ) : (
              <div className="space-y-2">
                <label
                  htmlFor={`short-answer-${current.id}`}
                  className="block text-sm font-semibold text-text"
                >
                  Your answer to: {current.question_text}
                </label>
                <textarea
                  id={`short-answer-${current.id}`}
                  value={answers[current.id]?.answer_text || ''}
                  onChange={(e) => setShortAnswer(current.id, e.target.value)}
                  rows={3}
                  className="w-full rounded-2xl border border-border bg-bg px-4 py-3 text-base text-text"
                  placeholder="Type your answer…"
                />
              </div>
            )}

            {feedback && (
              <p className="text-sm text-text-muted" role="status" aria-live="polite">
                {feedback.text}
              </p>
            )}

            <div className="flex gap-3">
              <Button
                variant="secondary"
                size="lg"
                disabled={qIndex === 0 || submitting}
                onClick={goBack}
              >
                Back
              </Button>
              <Button
                size="lg"
                className="flex-1"
                disabled={
                  submitting ||
                  (!answers[current.id]?.selected_option_id &&
                    !(answers[current.id]?.answer_text || '').trim())
                }
                onClick={goNext}
              >
                {qIndex < totalQuestions - 1
                  ? 'Next'
                  : submitting
                    ? 'Finishing…'
                    : 'Finish quiz'}
              </Button>
            </div>
          </Card>
        </div>
      )}

      {phase === 'submitted' && result && (
        <div className="space-y-4">
          <Card className="p-6 md:p-8 space-y-5 text-center">
            <p className="text-4xl" aria-hidden="true">
              🌟
            </p>
            <h1 className="font-display text-2xl font-bold text-text">You have completed this quiz</h1>
            <p className="text-lg text-text">
              Score: <strong>{result.score}%</strong>
              {result.correct_count != null && (
                <span className="text-text-muted text-base">
                  {' '}
                  ({result.correct_count}/{result.total_questions} correct)
                </span>
              )}
            </p>
            {result.xp_gained > 0 && (
              <div className="flex justify-center">
                <XPChip xp={result.xp_gained} />
              </div>
            )}
            <Button size="lg" onClick={() => navigate(-1)}>
              Back to lesson
            </Button>
          </Card>

          {result.remediation && (
            <Card className="p-6 md:p-8 space-y-4 text-left bg-learning rounded-2xl border border-border shadow-soft">
              <h2 className="font-display text-xl font-bold text-text">
                Let&apos;s try this another way
              </h2>
              <p className="text-sm text-text-muted">
                The same ideas can help more when they are shown in a different form.
              </p>

              {!remediationChoice && (
                <div className="space-y-3">
                  {(result.remediation.offers || []).map((offer) => {
                    let label = 'Continue';
                    if (offer.kind === 'alternative_material') label = 'Open the written version';
                    else if (offer.kind === 'approved_pack') label = 'Read the explanation';
                    else if (offer.kind === 'guided_rewatch') label = 'Watch in short parts';
                    return (
                      <Button
                        key={`${offer.kind}-${offer.content_id}`}
                        size="lg"
                        variant="secondary"
                        className="w-full justify-center"
                        disabled={remediationBusy}
                        onClick={() => handleRemediationChoice(offer)}
                      >
                        {label}
                        {offer.title ? ` — ${offer.title}` : ''}
                      </Button>
                    );
                  })}
                </div>
              )}

              {remediationChoice && selectedOffer && (
                <div className="rounded-2xl bg-mint/15 border border-mint/30 p-4 text-sm space-y-3">
                  {selectedOffer.kind === 'alternative_material' && (
                    <>
                      <p className="font-semibold text-text">{selectedOffer.title}</p>
                      <p className="text-text-muted">
                        A written version of this lesson is ready for you.
                      </p>
                      {(selectedOffer.content_id || selectedOffer.file_url) && (
                        <Button
                          variant="secondary"
                          onClick={() => {
                            const apiBase =
                              import.meta.env.VITE_API_BASE_URL || 'http://localhost:5000/api';
                            const token = localStorage.getItem('access_token') || '';
                            const url = selectedOffer.content_id
                              ? `${apiBase}/courses/materials/${selectedOffer.content_id}/file?token=${encodeURIComponent(token)}`
                              : selectedOffer.file_url;
                            window.open(url, '_blank', 'noopener,noreferrer');
                          }}
                        >
                          Open the written version
                        </Button>
                      )}
                    </>
                  )}
                  {selectedOffer.kind === 'approved_pack' && (
                    <>
                      <p className="font-semibold text-text">{selectedOffer.title}</p>
                      <p className="text-text whitespace-pre-wrap">{selectedOffer.summary}</p>
                      {(selectedOffer.milestones || []).length > 0 && (
                        <ol className="list-decimal pl-5 space-y-2 text-text">
                          {selectedOffer.milestones.map((m) => (
                            <li key={m.id}>
                              <span className="font-medium">{m.question}</span>
                              {(m.options || []).length > 0 && (
                                <ul className="list-disc pl-5 text-text-muted mt-1">
                                  {m.options.map((opt, idx) => (
                                    <li key={idx}>{opt}</li>
                                  ))}
                                </ul>
                              )}
                            </li>
                          ))}
                        </ol>
                      )}
                    </>
                  )}
                  {selectedOffer.kind === 'guided_rewatch' && (
                    <>
                      <p className="font-semibold text-text">{selectedOffer.title}</p>
                      <p className="text-text-muted">
                        Watch the video in short parts. Use the checkpoint questions between parts.
                      </p>
                      {(selectedOffer.milestones || []).length > 0 && (
                        <ol className="list-decimal pl-5 space-y-2 text-text">
                          {selectedOffer.milestones.map((m) => (
                            <li key={m.id}>{m.question}</li>
                          ))}
                        </ol>
                      )}
                      <Button size="lg" onClick={() => navigate(-1)}>
                        Back to the video
                      </Button>
                    </>
                  )}
                </div>
              )}
            </Card>
          )}
        </div>
      )}
    </div>
  );
}
