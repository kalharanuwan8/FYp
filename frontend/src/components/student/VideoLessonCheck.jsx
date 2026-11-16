import { useEffect, useState } from 'react';
import { Sparkles, BookOpen } from 'lucide-react';
import { quizService } from '../../services/quizService';
import { Button, Card, LoadingSpinner, ErrorBanner } from '../common';

/**
 * Questions about the video the student just watched.
 * A miss opens the teacher's other version as a fresh way to study the same lesson.
 */
export default function VideoLessonCheck({ material, alternate, onClose, onStudyAgain }) {
  const [quiz, setQuiz] = useState(null);
  const [attemptId, setAttemptId] = useState(null);
  const [qIndex, setQIndex] = useState(0);
  const [selected, setSelected] = useState({});
  const [phase, setPhase] = useState('loading');
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const data = await quizService.getQuizDetail(material.quiz_id);
        const attempt = await quizService.startAttempt(material.quiz_id, {
          source: 'lesson_check',
        });
        if (cancelled) return;
        setQuiz(data);
        setAttemptId(attempt.attempt_id);
        setPhase('quiz');
      } catch (err) {
        if (!cancelled) {
          setError(err.response?.data?.error || 'Could not open the lesson questions.');
          setPhase('error');
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [material.quiz_id]);

  const questions = quiz?.questions || [];
  const current = questions[qIndex];

  const submit = async (nextAnswers) => {
    setBusy(true);
    setError(null);
    try {
      const graded = await quizService.submitAttempt(attemptId, {
        answers: questions.map((q) => ({
          question_id: q.id,
          selected_option_id: nextAnswers[q.id] || null,
        })),
      });
      setResult(graded);
      setPhase('done');
    } catch (err) {
      setError(err.response?.data?.error || 'Could not save your answers.');
    } finally {
      setBusy(false);
    }
  };

  const goNext = () => {
    if (!current || !selected[current.id]) return;
    if (qIndex < questions.length - 1) {
      setQIndex((i) => i + 1);
      return;
    }
    submit(selected);
  };

  const alternateOffer = (result?.remediation?.offers || []).find(
    (offer) => offer.kind === 'alternative_material'
  );
  const studyTarget = alternateOffer
    ? {
        id: alternateOffer.content_id,
        title: alternateOffer.title,
        file_url: alternateOffer.file_url,
        content_type: alternateOffer.content_type,
      }
    : alternate;

  const total = result?.total_questions || 0;
  const correct = result?.correct_count || 0;
  const wrongRate = total > 0 ? (total - correct) / total : 0;
  // More than half the answers wrong — same cutoff the server uses for restudy.
  const needsRestudy = Boolean(result?.remediation) || wrongRate > 0.5;
  const sameAsVideo = studyTarget && Number(studyTarget.id) === Number(material.id);

  const studyAgain = async () => {
    if (result?.remediation?.event_id && alternateOffer) {
      try {
        await quizService.recordRemediationChoice(
          result.remediation.event_id,
          'alternative_material'
        );
      } catch {
        /* opening the lesson still matters if the log fails */
      }
    }
    if (studyTarget) onStudyAgain(studyTarget);
  };

  return (
    <div className="fixed inset-0 z-[80] bg-bg/80 backdrop-blur-sm flex items-center justify-center p-4">
      <Card className="max-w-lg w-full p-6 md:p-8 space-y-5 max-h-[90vh] overflow-y-auto">
        {phase === 'loading' && <LoadingSpinner label="Opening the lesson questions…" />}

        {phase === 'error' && (
          <div className="space-y-4">
            <ErrorBanner message={error} />
            <Button variant="secondary" onClick={onClose}>
              Back to the lesson
            </Button>
          </div>
        )}

        {phase === 'quiz' && current && (
          <div className="space-y-5">
            <div>
              <p className="text-sm font-semibold text-primary inline-flex items-center gap-2">
                <Sparkles className="w-4 h-4" aria-hidden="true" />
                Questions about this video
              </p>
              <h2 className="font-display text-2xl font-bold text-text mt-1">{material.title}</h2>
              <p className="text-sm text-text-muted mt-1">
                Question {qIndex + 1} of {questions.length}
              </p>
            </div>
            {error && <ErrorBanner message={error} />}
            <p className="text-lg font-semibold text-text">{current.question_text}</p>
            <div className="space-y-2" role="radiogroup" aria-label="Answer">
              {(current.options || []).map((opt) => {
                const chosen = selected[current.id] === opt.id;
                return (
                  <button
                    key={opt.id}
                    type="button"
                    role="radio"
                    aria-checked={chosen}
                    onClick={() => setSelected((prev) => ({ ...prev, [current.id]: opt.id }))}
                    className={`w-full text-left min-h-11 px-4 py-3 rounded-2xl border cursor-pointer ${
                      chosen
                        ? 'border-primary border-2 bg-primary-soft'
                        : 'border-border bg-surface hover:border-primary/40'
                    }`}
                  >
                    {opt.option_text}
                  </button>
                );
              })}
            </div>
            <Button size="lg" className="w-full" disabled={busy || !selected[current.id]} onClick={goNext}>
              {qIndex < questions.length - 1 ? 'Next' : busy ? 'Checking…' : 'See how you did'}
            </Button>
          </div>
        )}

        {phase === 'done' && result && needsRestudy && (
          <div className="space-y-5 text-center">
            <p className="text-4xl" aria-hidden="true">
              🌱
            </p>
            <div className="space-y-2">
              <p className="text-sm font-semibold text-primary">Let’s take another pass</p>
              <h2 className="font-display text-2xl font-bold text-text">Study it a lighter way</h2>
              <p className="text-sm text-text-muted">
                You got {correct} of {total} right, so more than half still needs a look.
                No rush — pick the version that feels easier and enjoy going through it again.
              </p>
            </div>
            {studyTarget && !sameAsVideo && (
              <div className="rounded-2xl border border-primary/30 bg-primary-soft/50 p-4 text-left">
                <p className="text-xs font-semibold uppercase tracking-wide text-primary">
                  A calmer version
                </p>
                <p className="font-display text-lg font-bold text-text mt-1">{studyTarget.title}</p>
              </div>
            )}
            {studyTarget && !sameAsVideo && (
              <Button size="lg" className="w-full" onClick={studyAgain}>
                <BookOpen className="w-4 h-4" aria-hidden="true" />
                Study the easier version
              </Button>
            )}
            <Button
              size="lg"
              variant={studyTarget && !sameAsVideo ? 'secondary' : 'primary'}
              className="w-full"
              onClick={() => onStudyAgain(material)}
            >
              Watch the video again
            </Button>
            <Button variant="ghost" className="w-full" onClick={onClose}>
              Not now
            </Button>
          </div>
        )}

        {phase === 'done' && result && !needsRestudy && (
          <div className="space-y-4 text-center">
            <h2 className="font-display text-2xl font-bold text-text">You have the idea</h2>
            <p className="text-sm text-text-muted">
              {correct} of {total} correct. That lesson is yours.
            </p>
            <Button size="lg" className="w-full" onClick={onClose}>
              Back to the lesson
            </Button>
          </div>
        )}
      </Card>
    </div>
  );
}
