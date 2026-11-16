import { useState, useEffect, useCallback, useRef } from 'react';
import { useParams, useNavigate, useOutletContext } from 'react-router-dom';
import {
  ArrowLeft,
  ChevronDown,
  Plus,
  FileText,
  Video,
  HelpCircle,
  Lightbulb,
  Lock,
  Play,
  Square,
  Coffee,
  Eye,
  EyeOff,
} from 'lucide-react';
import { courseService } from '../../services/courseService';
import { sessionService } from '../../services/sessionService';
import FocusInterventionOverlay from '../../components/student/FocusInterventionOverlay';
import ScreenCalibrationOverlay from '../../components/student/ScreenCalibrationOverlay';
import GazeSelfTest from '../../components/student/GazeSelfTest';
import VideoLearningPlayer from '../../components/student/VideoLearningPlayer';
import VideoLessonCheck from '../../components/student/VideoLessonCheck';
import DocumentReader from '../../components/student/DocumentReader';
import WebcamCapture from '../../components/monitoring/WebcamCapture';
import FocusBuddy from '../../components/student/FocusBuddy';
import DemoPanel from '../../components/student/DemoPanel';
import SessionSummary from '../../components/student/SessionSummary';
import { useMonitoringSession } from '../../hooks/useMonitoringSession';
import { useHeartbeatBus } from '../../hooks/useHeartbeatBus';
import { usePreferences } from '../../context/PreferencesContext';
import { Button, Card, LoadingSpinner, ErrorBanner, ConfirmDialog } from '../../components/common';
import { accentForId } from '../../utils/subjectAccents';
import { buildLocalDemoIntervention } from '../../utils/demoInterventions';

/** Lesson quiz stored on the video, or the quiz sitting in the same module. */
function withLessonQuiz(item, mod) {
  const contents = mod?.contents || [];
  const titled = `${item?.title || ''} — lesson check`;
  const quizzes = contents.filter((c) => c.content_type === 'quiz' && c.quiz_id);
  const videos = contents.filter(
    (c) =>
      c.content_type === 'video' ||
      (c.file_url && (String(c.file_url).endsWith('.mp4') || String(c.file_url).endsWith('.webm')))
  );
  const linked =
    quizzes.find((c) => c.title === titled) ||
    (quizzes.length === 1 ? quizzes[0] : null) ||
    (videos.length <= 1 ? quizzes[0] : null);
  return {
    ...item,
    module_id: mod?.id || item?.module_id,
    quiz_id: item?.quiz_id || linked?.quiz_id || null,
  };
}

export default function SubjectDetail() {
  const { id } = useParams();
  const navigate = useNavigate();
  const { setFocusMode, refreshProgress, profile, refreshProfile } = useOutletContext() || {};
  const gazeCalibrated = Boolean(profile?.gaze_calibrated);
  const { showCameraPreview, breakIntervalMinutes, updatePreferences } = usePreferences();

  const [subject, setSubject] = useState(null);
  const [isEnrolled, setIsEnrolled] = useState(false);
  const [loading, setLoading] = useState(true);
  const [actionLoading, setActionLoading] = useState(false);
  const [pageError, setPageError] = useState(null);
  const [actionError, setActionError] = useState(null);
  const [dropConfirmOpen, setDropConfirmOpen] = useState(false);
  const [activeVideoMaterial, setActiveVideoMaterial] = useState(null);
  const [lessonCheck, setLessonCheck] = useState(null);
  const [activeDocumentMaterial, setActiveDocumentMaterial] = useState(null);
  const [activeModuleTitle, setActiveModuleTitle] = useState('');
  const [sessionModule, setSessionModule] = useState(null);
  const [sessionStep, setSessionStep] = useState(null);
  const [activeIntervention, setActiveIntervention] = useState(null);
  const [sessionSummary, setSessionSummary] = useState(null);
  const [elapsedSec, setElapsedSec] = useState(0);
  const [calibratingOpen, setCalibratingOpen] = useState(false);
  const [calibKey, setCalibKey] = useState(0);
  const [selfTestOpen, setSelfTestOpen] = useState(false); // PLAN 8 guided gaze test
  const selfTestOpenRef = useRef(false);
  const { onHeartbeat, subscribeHeartbeat } = useHeartbeatBus();
  const [lastBreakAtSec, setLastBreakAtSec] = useState(0);
  const [simulateIgnore, setSimulateIgnore] = useState(false);
  const showCam = showCameraPreview;
  const [expandedModuleId, setExpandedModuleId] = useState(null);

  // A video opened before its quiz existed still needs that quiz when it ends.
  useEffect(() => {
    if (!activeVideoMaterial || activeVideoMaterial.quiz_id || !subject) return;
    const mod = (subject.modules || []).find(
      (m) => Number(m.id) === Number(activeVideoMaterial.module_id)
    );
    const next = withLessonQuiz(activeVideoMaterial, mod);
    if (next.quiz_id) setActiveVideoMaterial(next);
  }, [activeVideoMaterial, subject]);

  // A newly arrived intervention REPLACES the open one (e.g. T1 banner → T2 pause).
  const handleInterventionFromMl = useCallback((intervention) => {
    // The gaze self-test deliberately looks away; don't pop prompts over it.
    if (selfTestOpenRef.current) return;
    setActiveIntervention(intervention);
  }, []);

  const {
    webcamRef,
    canvasRef,
    cameraActive,
    activeSession,
    lastVerdict,
    mlMode,
    confidence,
    gazeDebug,
    error: monitorError,
    startMonitoredSession,
    stopMonitoredSession,
    triggerManualIntervention,
    setCalibrating,
    setCalibrationTarget,
    finishCalibration: finishScreenCalibration,
    faceDetected,
  } = useMonitoringSession({
    intervalMs: 1000, // PLAN 8: consistent 1 s heartbeat during focus sessions
    onIntervention: handleInterventionFromMl,
    onHeartbeat,
  });

  const getBackendOrigin = () => {
    const apiBase = import.meta.env.VITE_API_BASE_URL || 'http://localhost:5000/api';
    return apiBase.replace(/\/api\/?$/, '');
  };

  const resolveMediaUrl = (itemOrUrl) => {
    // Prefer authenticated material file route when we have a content id.
    if (itemOrUrl && typeof itemOrUrl === 'object' && itemOrUrl.id) {
      const apiBase = import.meta.env.VITE_API_BASE_URL || 'http://localhost:5000/api';
      const token = localStorage.getItem('access_token') || '';
      return `${apiBase}/courses/materials/${itemOrUrl.id}/file?token=${encodeURIComponent(token)}`;
    }
    const fileUrl = itemOrUrl;
    if (!fileUrl) return '#';
    if (fileUrl.startsWith('http://') || fileUrl.startsWith('https://')) return fileUrl;
    const origin = getBackendOrigin();
    return `${origin}${fileUrl.startsWith('/') ? '' : '/'}${fileUrl}`;
  };

  const fetchDetails = async () => {
    setLoading(true);
    setPageError(null);
    try {
      const subjectData = await courseService.getSubjectDetail(id);
      setSubject(subjectData);
      const enrollmentsData = await courseService.listMyEnrollments();
      const myIds = new Set((enrollmentsData.enrollments || []).map((s) => s.id));
      setIsEnrolled(myIds.has(Number(id)));
    } catch (err) {
      setPageError(err.response?.data?.error || 'Failed to load course detail');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (id) fetchDetails();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  useEffect(() => {
    setFocusMode?.(Boolean(activeSession));
    return () => setFocusMode?.(false);
  }, [activeSession, setFocusMode]);

  useEffect(() => {
    if (!activeSession) {
      setElapsedSec(0);
      return undefined;
    }
    const idTimer = setInterval(() => setElapsedSec((s) => s + 1), 1000);
    return () => clearInterval(idTimer);
  }, [activeSession]);

  // Suggested break every N minutes (elapsed >= interval, not modulo)
  useEffect(() => {
    if (!activeSession || activeIntervention || calibratingOpen) return undefined;
    const interval = (breakIntervalMinutes || 18) * 60;
    if (elapsedSec >= interval && elapsedSec - lastBreakAtSec >= interval) {
      setLastBreakAtSec(elapsedSec);
      setActiveIntervention({
        intervention_id: null,
        tier: 4,
        intervention_type: 'suggest_break',
        message: "You've been focusing for a while — nice work. Take a short stretch?",
        payload: { break_seconds: 60 },
      });
    }
    return undefined;
  }, [
    elapsedSec,
    activeSession,
    activeIntervention,
    breakIntervalMinutes,
    lastBreakAtSec,
    calibratingOpen,
  ]);

  const handleEnroll = async () => {
    setActionLoading(true);
    setActionError(null);
    try {
      await courseService.enroll(id);
      await fetchDetails();
    } catch (err) {
      setActionError(err.response?.data?.error || 'Failed to enroll');
    } finally {
      setActionLoading(false);
    }
  };

  const handleDropEnrollment = async () => {
    setActionLoading(true);
    try {
      await courseService.dropEnrollment(id);
      setDropConfirmOpen(false);
      await fetchDetails();
    } catch (err) {
      setActionError(err.response?.data?.error || 'Failed to drop enrollment');
    } finally {
      setActionLoading(false);
    }
  };

  const beginCalibration = useCallback(() => {
    setCalibKey((k) => k + 1);
    setCalibratingOpen(true);
    setCalibrating(true);
  }, [setCalibrating]);

  /** Close the overlay (it already flushed the 'finish' heartbeat itself). */
  const closeCalibration = useCallback(() => {
    setCalibratingOpen(false);
    setCalibrating(false);
  }, [setCalibrating]);

  useEffect(() => {
    selfTestOpenRef.current = selfTestOpen;
  }, [selfTestOpen]);

  const openSelfTest = useCallback(() => setSelfTestOpen(true), []);
  const closeSelfTest = useCallback(() => setSelfTestOpen(false), []);
  const recalibrateFromSelfTest = useCallback(() => {
    setSelfTestOpen(false);
    beginCalibration();
  }, [beginCalibration]);

  const handleStartSession = async (mod, step = null) => {
    setActionError(null);
    setSessionSummary(null);
    setActiveIntervention(null);
    setLastBreakAtSec(0);
    const result = await startMonitoredSession(mod.id);
    if (result?.ok) {
      setSessionModule(mod);
      setSessionStep(step);
      if (!gazeCalibrated) beginCalibration();
    } else {
      setActionError(result?.error || monitorError || 'Failed to start focus session');
    }
  };

  const handleCalibrationDone = useCallback(
    async (result) => {
      closeCalibration();
      if (result?.ok) {
        await refreshProfile?.();
      }
    },
    [closeCalibration, refreshProfile]
  );

  const handleInterventionResponse = async (interventionId, userResponse, extra = {}) => {
    if (extra.dismiss_only) {
      setActiveIntervention(null);
      return null;
    }
    // Local pomodoro break (no backend id)
    if (!interventionId || !activeSession) {
      setActiveIntervention(null);
      return null;
    }
    try {
      const res = await sessionService.recordInterventionResponse(
        activeSession.session_id,
        interventionId,
        userResponse,
        extra
      );
      if (!extra.defer_clear) setActiveIntervention(null);
      if (userResponse === 'ended') handleStopSession();
      return res;
    } catch (err) {
      console.error(err);
      setActiveIntervention(null);
      return null;
    }
  };

  const handleStopSession = async () => {
    if (!activeSession) return;
    try {
      closeCalibration();
      const summary = await stopMonitoredSession();
      setSessionSummary(summary);
      setSessionModule(null);
      setSessionStep(null);
      setActiveIntervention(null);
      refreshProgress?.();
    } catch (err) {
      setActionError(err.response?.data?.error || 'Failed to stop session');
    }
  };

  const handleNeedBreak = () => {
    setActiveIntervention({
      intervention_id: null,
      tier: 4,
      intervention_type: 'suggest_break',
      message: 'Take a moment — stretch or breathe.',
      payload: { break_seconds: 60 },
    });
  };

  const handleOpenMaterial = async (item, mod) => {
    const isVideo =
      item.content_type === 'video' ||
      (item.file_url &&
        (item.file_url.endsWith('.mp4') || item.file_url.endsWith('.webm')));
    if (isVideo) {
      if (activeSession) {
        try {
          await stopMonitoredSession();
        } catch {
          /* best-effort */
        }
        setSessionModule(null);
        setActiveIntervention(null);
      }
      setActiveVideoMaterial(withLessonQuiz(item, mod));
      setActiveModuleTitle(mod.title);
    } else if (item.content_type === 'quiz' && item.quiz_id) {
      navigate(`/student/quizzes/${item.quiz_id}`);
    } else if (item.content_type === 'document' || item.file_url) {
      setActiveDocumentMaterial(item);
      setActiveModuleTitle(mod.title);
    } else {
      window.open(resolveMediaUrl(item), '_blank');
    }
  };

  const accent = accentForId(id);
  const verdictU = String(lastVerdict || '').toUpperCase();
  const onTrack = !lastVerdict || verdictU === 'FOCUSED';
  const buddyUnknown = verdictU === 'UNKNOWN';
  const formatTimer = (s) => {
    const m = Math.floor(s / 60);
    const sec = s % 60;
    return `${m}:${String(sec).padStart(2, '0')}`;
  };

  const contentIcon = (type) => {
    const map = {
      video: Video,
      quiz: HelpCircle,
      other: Lightbulb,
    };
    const Icon = map[type] || FileText;
    return <Icon className="w-4 h-4" aria-hidden="true" />;
  };

  const contentTypeLabel = (type) => {
    const map = {
      video: 'Video lesson',
      quiz: 'Quiz',
      document: 'Document',
      other: 'Activity',
    };
    return map[type] || 'Document';
  };

  if (loading) return <LoadingSpinner label="Loading your path…" />;

  if (pageError || !subject) {
    return (
      <div className="max-w-3xl mx-auto space-y-4">
        <button
          type="button"
          onClick={() => navigate('/student/courses')}
          className="text-sm font-semibold text-primary flex items-center gap-1.5 min-h-11"
        >
          <ArrowLeft className="w-4 h-4" /> Back
        </button>
        <ErrorBanner message={pageError || 'Subject not found'} />
      </div>
    );
  }

  const modules = subject.modules || [];
  const lessonAlternate = lessonCheck
    ? modules
        .flatMap((mod) => mod.contents || [])
        .find((c) => Number(c.remediation_for_content_id) === Number(lessonCheck.id)) || null
    : null;
  const lessonCheckNode = lessonCheck ? (
    <VideoLessonCheck
      material={lessonCheck}
      alternate={lessonAlternate}
      onClose={() => setLessonCheck(null)}
      onStudyAgain={(item) => {
        setLessonCheck(null);
        const withModule = {
          ...item,
          module_id: item.module_id || lessonCheck?.module_id,
        };
        const isVideo =
          withModule.content_type === 'video' ||
          (withModule.file_url &&
            (withModule.file_url.endsWith('.mp4') || withModule.file_url.endsWith('.webm')));
        if (isVideo) {
          setActiveDocumentMaterial(null);
          setActiveVideoMaterial(withModule);
        } else {
          setActiveVideoMaterial(null);
          setActiveDocumentMaterial(withModule);
        }
      }}
    />
  ) : null;

  // ——— Focus mode shell ———
  if (activeSession && sessionModule) {
    return (
      <div
        className="min-h-screen flex flex-col learning-shell bg-bg"
        style={{
          boxShadow: `inset 4px 0 0 0 ${accent.color}`,
        }}
      >
        <div
          className={
            showCam
              ? 'fixed bottom-4 right-4 z-40 shadow-soft rounded-2xl overflow-hidden border border-border bg-learning'
              : 'fixed w-40 h-28 opacity-0 pointer-events-none -z-10 left-0 top-0 overflow-hidden'
          }
          aria-hidden={!showCam}
        >
          <WebcamCapture
            videoRef={webcamRef}
            canvasRef={canvasRef}
            cameraActive={cameraActive}
            compact
          />
          {showCam && (
            <p className="px-2 pb-2 text-[10px] text-text-muted max-w-[11rem]">
              Hiding preview does not stop monitoring.
            </p>
          )}
        </div>

        <ScreenCalibrationOverlay
          key={calibKey}
          open={calibratingOpen}
          faceFound={faceDetected !== false}
          setCalibrationTarget={setCalibrationTarget}
          finishCalibration={finishScreenCalibration}
          onDone={handleCalibrationDone}
          onRetry={beginCalibration}
          onTest={openSelfTest}
        />
        <GazeSelfTest
          open={selfTestOpen}
          onClose={closeSelfTest}
          onRecalibrate={recalibrateFromSelfTest}
          subscribeHeartbeat={subscribeHeartbeat}
        />
        {/* "Simulate ignore" (demo): prompts stay visible but can't be answered. */}
        <div className={simulateIgnore ? 'contents pointer-events-none' : 'contents'}>
          <FocusInterventionOverlay
            key={
              activeIntervention
                ? `${activeIntervention.intervention_id ?? 'local'}-${activeIntervention.intervention_type ?? activeIntervention.tier}`
                : 'none'
            }
            intervention={activeIntervention}
            onRespond={handleInterventionResponse}
          />
        </div>
        <DemoPanel
          sessionId={activeSession.session_id}
          lastVerdict={lastVerdict}
          mlMode={mlMode}
          confidence={confidence}
          gazeDebug={gazeDebug}
          onSimulateIgnoreChange={setSimulateIgnore}
          onTriggerLocal={(kind) => setActiveIntervention(buildLocalDemoIntervention(kind))}
          onTriggerTier={async (tier, options) => {
            try {
              await triggerManualIntervention(tier, false, options);
            } catch (err) {
              console.error('Demo trigger failed:', err);
              // Re-throw so the demo sidebar shows its error line.
              throw new Error(
                err.response?.data?.error || err.message || 'Failed to trigger intervention',
                { cause: err }
              );
            }
          }}
        />

        <header className="focus-session-chrome flex items-center justify-between gap-3 px-4 md:px-8 py-4">
          <div className="min-w-0">
            <p className="text-xs font-semibold text-text-muted">Focus session</p>
            <h1 className="font-display font-bold text-text truncate">
              {sessionStep?.title || sessionModule.title}
            </h1>
          </div>
          <div className="flex items-center gap-2 md:gap-3 flex-wrap justify-end">
            <FocusBuddy onTrack={onTrack} unknown={buddyUnknown} />
            <span className="font-display font-bold text-text tabular-nums min-h-11 flex items-center text-sm">
              {formatTimer(elapsedSec)}
            </span>
            <button
              type="button"
              onClick={handleNeedBreak}
              className="inline-flex items-center gap-1.5 min-h-11 px-3 rounded-2xl border border-border bg-learning text-text text-sm font-semibold cursor-pointer"
            >
              <Coffee className="w-4 h-4" aria-hidden="true" />
              I need a break
            </button>
            <Button variant="secondary" onClick={handleStopSession}>
              End session
            </Button>
          </div>
        </header>

        <main className="flex-1 flex flex-col items-center justify-center p-4 md:p-10 max-w-2xl mx-auto w-full space-y-6">
          <div className="learning-panel w-full p-6 md:p-8 space-y-4 text-center">
            <p className="text-sm text-text-muted">
              Stay with this step. Your focus buddy is quietly nearby.
            </p>
            <h2 className="font-display text-2xl font-bold text-text">
              {sessionModule.title}
            </h2>
            {sessionModule.description && (
              <p className="text-text-muted prose-narrow mx-auto">{sessionModule.description}</p>
            )}
            {(sessionModule.contents || []).length > 0 && (
              <ul className="text-left space-y-2 pt-2">
                {sessionModule.contents.map((item) => (
                  <li key={item.id}>
                    <button
                      type="button"
                      onClick={() => handleOpenMaterial(item, sessionModule)}
                      className="w-full flex items-center gap-3 min-h-12 px-4 rounded-2xl border border-border bg-bg hover:border-primary text-left cursor-pointer"
                    >
                      <span
                        className="w-9 h-9 rounded-xl flex items-center justify-center text-on-primary"
                        style={{ background: accent.color }}
                        aria-hidden="true"
                      >
                        {contentIcon(item.content_type)}
                      </span>
                      <span className="font-medium text-text flex-1">{item.title}</span>
                      <span className="text-xs text-text-muted">{contentTypeLabel(item.content_type)}</span>
                      <Play className="w-4 h-4 text-text-muted" aria-hidden="true" />
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>

          <div className="flex items-center gap-3 text-sm text-text-muted">
            <button
              type="button"
              onClick={() => {
                updatePreferences({ showCameraPreview: !showCam });
              }}
              className="inline-flex items-center gap-1.5 min-h-11 px-2 cursor-pointer font-semibold"
            >
              {showCam ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
              {showCam ? 'Hide my camera' : 'Show my camera'}
            </button>
            <span aria-hidden="true">·</span>
            <span>Hiding the preview does not stop monitoring. Preview stays on this device.</span>
          </div>
        </main>

        {activeVideoMaterial && (
          <VideoLearningPlayer
            material={activeVideoMaterial}
            moduleTitle={activeModuleTitle}
            gazeCalibrated={gazeCalibrated}
            onCalibrationSaved={refreshProfile}
            onLessonComplete={() => {
              if (activeVideoMaterial?.quiz_id) setLessonCheck(activeVideoMaterial);
            }}
            onClose={() => setActiveVideoMaterial(null)}
          />
        )}
        {activeDocumentMaterial && (
          <DocumentReader
            material={activeDocumentMaterial}
            fileUrl={resolveMediaUrl(activeDocumentMaterial)}
            onClose={() => setActiveDocumentMaterial(null)}
          />
        )}
        {lessonCheckNode}
      </div>
    );
  }

  // ——— Journey path view ———
  return (
    <div className="space-y-6 max-w-3xl mx-auto animate-fade-in relative">
      <div
        className={
          showCam && cameraActive
            ? 'fixed bottom-4 right-4 z-40 shadow-lift rounded-2xl overflow-hidden border border-border'
            : 'fixed w-40 h-28 opacity-0 pointer-events-none -z-10 left-0 top-0 overflow-hidden'
        }
        aria-hidden
      >
        <WebcamCapture
          videoRef={webcamRef}
          canvasRef={canvasRef}
          cameraActive={cameraActive}
          compact
        />
      </div>

      {activeVideoMaterial && (
        <VideoLearningPlayer
          material={activeVideoMaterial}
          moduleTitle={activeModuleTitle}
          gazeCalibrated={gazeCalibrated}
          onCalibrationSaved={refreshProfile}
          onLessonComplete={() => {
            if (activeVideoMaterial?.quiz_id) setLessonCheck(activeVideoMaterial);
          }}
          onClose={() => setActiveVideoMaterial(null)}
        />
      )}
      {activeDocumentMaterial && (
        <DocumentReader
          material={activeDocumentMaterial}
          fileUrl={resolveMediaUrl(activeDocumentMaterial)}
          onClose={() => setActiveDocumentMaterial(null)}
        />
      )}
      {lessonCheckNode}

      <FocusInterventionOverlay
        intervention={activeIntervention}
        onRespond={handleInterventionResponse}
      />

      <SessionSummary
        summary={sessionSummary}
        onClose={() => setSessionSummary(null)}
        onContinue={() => {
          setSessionSummary(null);
          if (modules[0]) handleStartSession(modules[0]);
        }}
      />

      <button
        type="button"
        onClick={() => navigate('/student/courses')}
        className="text-sm font-semibold text-primary flex items-center gap-1.5 min-h-11 cursor-pointer"
      >
        <ArrowLeft className="w-4 h-4" /> My Subjects
      </button>

      {actionError && (
        <ErrorBanner message={actionError} onDismiss={() => setActionError(null)} />
      )}

      <Card className="p-6 md:p-8 space-y-4" style={{ borderTop: `4px solid ${accent.color}` }}>
        <div className="flex flex-col sm:flex-row sm:items-start justify-between gap-4">
          <div className="space-y-2">
            <p className="text-sm font-semibold" style={{ color: accent.color }}>
              {subject.grade_level_name || 'Subject'}
              {isEnrolled ? ' · Enrolled' : ''}
            </p>
            <h1 className="font-display text-2xl md:text-3xl font-bold text-text">
              {subject.title}
            </h1>
            <p className="text-text-muted prose-narrow">
              {subject.description || 'Follow the path — one step at a time.'}
            </p>
          </div>
          {!isEnrolled ? (
            <Button onClick={handleEnroll} disabled={actionLoading}>
              <Plus className="w-4 h-4" />
              {actionLoading ? 'Enrolling…' : 'Enrol'}
            </Button>
          ) : (
            <Button variant="ghost" onClick={() => setDropConfirmOpen(true)}>
              Leave subject
            </Button>
          )}
        </div>
      </Card>

      <div className="space-y-1">
        <h2 className="font-display text-xl font-bold text-text">Your learning path</h2>
        <p className="text-sm text-text-muted">
          {isEnrolled
            ? 'You are working through this subject. Open a module to see its lessons — start with the first one, or revisit any lesson.'
            : 'Enrol to open the lessons in this subject.'}
        </p>
      </div>

      {modules.length === 0 ? (
        <Card className="p-8 text-center text-text-muted">No modules published yet.</Card>
      ) : (
        <ol className="relative space-y-0 pl-2">
          {modules.map((mod, idx) => {
            const isExpanded = (expandedModuleId ?? modules[0]?.id) === mod.id;
            const panelId = `module-panel-${mod.id}`;
            return (
              <li key={mod.id} className="relative flex gap-4 pb-8 last:pb-0">
                {idx < modules.length - 1 && (
                  <span
                    className="absolute left-[1.15rem] top-10 bottom-0 w-0.5 bg-border"
                    aria-hidden="true"
                  />
                )}
                <div
                  className={`relative z-10 w-10 h-10 rounded-full flex items-center justify-center shrink-0 border-2 ${
                    isEnrolled
                      ? 'bg-primary border-primary text-on-primary'
                      : 'bg-surface border-border text-text-muted'
                  }`}
                >
                  {isEnrolled ? (
                    <span className="font-display font-bold text-sm">{idx + 1}</span>
                  ) : (
                    <Lock className="w-4 h-4" />
                  )}
                </div>
                <Card className="flex-1 p-5 space-y-4">
                  <button
                    type="button"
                    onClick={() => setExpandedModuleId(isExpanded ? -1 : mod.id)}
                    aria-expanded={isExpanded}
                    aria-controls={panelId}
                    className="w-full flex items-start justify-between gap-3 text-left cursor-pointer min-h-11"
                  >
                    <span>
                      <span className="block text-xs font-semibold text-text-muted">
                        Module {idx + 1}
                        {idx === 0 ? ' · Start here' : ''}
                      </span>
                      <span className="block font-display font-bold text-lg text-text">{mod.title}</span>
                      {mod.description && (
                        <span className="block text-sm text-text-muted mt-1">{mod.description}</span>
                      )}
                    </span>
                    <ChevronDown
                      className={`w-5 h-5 text-text-muted shrink-0 mt-1 transition-transform ${isExpanded ? 'rotate-180' : ''}`}
                      aria-hidden="true"
                    />
                  </button>

                  {isExpanded && (
                    <div id={panelId} className="space-y-3">
                      {(mod.contents || []).length === 0 && (
                        <p className="text-sm text-text-muted">No lessons in this module yet.</p>
                      )}
                      {(mod.contents || []).map((item) => (
                        <div
                          key={item.id}
                          className="flex items-center gap-3 rounded-2xl border border-border bg-bg px-3 py-2.5"
                        >
                          <span className="text-primary">{contentIcon(item.content_type)}</span>
                          <span className="flex-1 min-w-0">
                            <span className="block text-sm font-medium text-text">{item.title}</span>
                            <span className="block text-xs text-text-muted">
                              {contentTypeLabel(item.content_type)}
                            </span>
                          </span>
                          {isEnrolled ? (
                            <button
                              type="button"
                              onClick={() => handleOpenMaterial(item, mod)}
                              className="text-sm font-semibold text-primary min-h-11 px-2 cursor-pointer shrink-0"
                            >
                              Open
                            </button>
                          ) : (
                            <span className="inline-flex items-center gap-1 text-xs font-semibold text-text-muted shrink-0">
                              <Lock className="w-4 h-4" aria-hidden="true" /> Enrol to open
                            </span>
                          )}
                        </div>
                      ))}
                      {isEnrolled &&
                        (activeSession &&
                        (activeSession.module_id === mod.id || sessionModule?.id === mod.id) ? (
                          <Button
                            variant="danger"
                            onClick={handleStopSession}
                            className="w-full sm:w-auto"
                          >
                            <Square className="w-4 h-4 fill-current" />
                            Stop session
                          </Button>
                        ) : (
                          <Button
                            onClick={() => handleStartSession(mod)}
                            disabled={Boolean(activeSession)}
                            className="w-full sm:w-auto"
                          >
                            <Play className="w-4 h-4" />
                            Start focus session
                          </Button>
                        ))}
                    </div>
                  )}
                </Card>
              </li>
            );
          })}
        </ol>
      )}

      <ConfirmDialog
        open={dropConfirmOpen}
        onClose={() => setDropConfirmOpen(false)}
        onConfirm={handleDropEnrollment}
        title="Leave this subject?"
        description="You can enrol again later. Your XP and badges stay with you."
        confirmLabel={actionLoading ? 'Leaving…' : 'Leave subject'}
        busy={actionLoading}
      />
    </div>
  );
}
