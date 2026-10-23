import { useState, useEffect, useCallback } from 'react';
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
  Coffee,
  Eye,
  EyeOff,
} from 'lucide-react';
import { courseService } from '../../services/courseService';
import { sessionService } from '../../services/sessionService';
import FocusInterventionOverlay from '../../components/student/FocusInterventionOverlay';
import VideoLearningPlayer from '../../components/student/VideoLearningPlayer';
import WebcamCapture from '../../components/monitoring/WebcamCapture';
import FocusBuddy from '../../components/student/FocusBuddy';
import DemoPanel from '../../components/student/DemoPanel';
import SessionSummary from '../../components/student/SessionSummary';
import { useMonitoringSession } from '../../hooks/useMonitoringSession';
import { usePreferences } from '../../context/PreferencesContext';
import { Button, Card, LoadingSpinner, ErrorBanner, ConfirmDialog } from '../../components/common';
import { accentForId } from '../../utils/subjectAccents';

export default function SubjectDetail() {
  const { id } = useParams();
  const navigate = useNavigate();
  const { setFocusMode, refreshProgress } = useOutletContext() || {};
  const { showCameraPreview, breakIntervalMinutes, updatePreferences } = usePreferences();

  const [subject, setSubject] = useState(null);
  const [isEnrolled, setIsEnrolled] = useState(false);
  const [loading, setLoading] = useState(true);
  const [actionLoading, setActionLoading] = useState(false);
  const [pageError, setPageError] = useState(null);
  const [actionError, setActionError] = useState(null);
  const [dropConfirmOpen, setDropConfirmOpen] = useState(false);
  const [activeVideoMaterial, setActiveVideoMaterial] = useState(null);
  const [activeModuleTitle, setActiveModuleTitle] = useState('');
  const [sessionModule, setSessionModule] = useState(null);
  const [sessionStep, setSessionStep] = useState(null);
  const [activeIntervention, setActiveIntervention] = useState(null);
  const [sessionSummary, setSessionSummary] = useState(null);
  const [elapsedSec, setElapsedSec] = useState(0);
  const showCam = showCameraPreview;
  const [expandedModuleId, setExpandedModuleId] = useState(null);

  const handleInterventionFromMl = useCallback((intervention) => {
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
    error: monitorError,
    startMonitoredSession,
    stopMonitoredSession,
    triggerManualIntervention,
  } = useMonitoringSession({
    intervalMs: 2000,
    onIntervention: handleInterventionFromMl,
  });

  const getBackendOrigin = () => {
    const apiBase = import.meta.env.VITE_API_BASE_URL || 'http://localhost:5000/api';
    return apiBase.replace(/\/api\/?$/, '');
  };

  const resolveMediaUrl = (fileUrl) => {
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

  // Suggested break every N minutes
  useEffect(() => {
    if (!activeSession || activeIntervention) return undefined;
    const interval = (breakIntervalMinutes || 18) * 60;
    if (elapsedSec > 0 && elapsedSec % interval === 0) {
      setActiveIntervention({
        intervention_id: null,
        tier: 4,
        intervention_type: 'suggest_break',
        message: "You've been focusing for a while — nice work. Take a short stretch?",
        payload: { break_seconds: 60 },
      });
    }
    return undefined;
  }, [elapsedSec, activeSession, activeIntervention, breakIntervalMinutes]);

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

  const handleStartSession = async (mod, step = null) => {
    setActionError(null);
    setSessionSummary(null);
    setActiveIntervention(null);
    const result = await startMonitoredSession(mod.id);
    if (result?.ok) {
      setSessionModule(mod);
      setSessionStep(step);
    } else {
      setActionError(result?.error || monitorError || 'Failed to start focus session');
    }
  };

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
      setActiveVideoMaterial({ ...item, module_id: mod.id });
      setActiveModuleTitle(mod.title);
    } else if (item.content_type === 'quiz' && item.quiz_id) {
      navigate(`/student/quizzes/${item.quiz_id}`);
    } else {
      window.open(resolveMediaUrl(item.file_url), '_blank');
    }
  };

  const accent = accentForId(id);
  const onTrack = !lastVerdict || String(lastVerdict).toUpperCase() === 'FOCUSED';
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

  // ——— Focus mode shell ———
  if (activeSession && sessionModule) {
    return (
      <div
        className="min-h-screen flex flex-col"
        style={{
          boxShadow: `inset 0 0 0 4px ${accent.color}`,
        }}
      >
        <div
          className={
            showCam
              ? 'fixed bottom-4 right-4 z-40 shadow-lift rounded-2xl overflow-hidden border border-border'
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
        </div>

        <FocusInterventionOverlay
          intervention={activeIntervention}
          onRespond={handleInterventionResponse}
        />
        <DemoPanel
          sessionId={activeSession.session_id}
          lastVerdict={lastVerdict}
          mlMode={mlMode}
          confidence={confidence}
          onTriggerTier={(t) => triggerManualIntervention(t, false)}
        />

        <header className="flex items-center justify-between gap-3 px-4 md:px-8 py-4 border-b border-border bg-surface/90">
          <div className="min-w-0">
            <p className="text-xs font-semibold text-text-muted">Focus session</p>
            <h1 className="font-display font-bold text-text truncate">
              {sessionStep?.title || sessionModule.title}
            </h1>
          </div>
          <div className="flex items-center gap-3 flex-wrap justify-end">
            <FocusBuddy onTrack={onTrack} />
            <span className="font-display font-bold text-text tabular-nums min-h-11 flex items-center">
              {formatTimer(elapsedSec)}
            </span>
            <button
              type="button"
              onClick={handleNeedBreak}
              className="inline-flex items-center gap-1.5 min-h-11 px-3 rounded-2xl bg-peach/20 text-text text-sm font-semibold cursor-pointer"
            >
              <Coffee className="w-4 h-4" aria-hidden="true" />
              I need a break
            </button>
            <Button variant="secondary" onClick={handleStopSession}>
              End session
            </Button>
          </div>
        </header>

        <main className="flex-1 flex flex-col items-center justify-center p-6 md:p-10 max-w-2xl mx-auto w-full space-y-6">
          <Card className="w-full p-6 md:p-8 space-y-4 text-center">
            <p className="text-sm text-text-muted">
              Stay with this step. Your focus buddy is quietly cheering you on.
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
                        className="w-9 h-9 rounded-xl flex items-center justify-center text-white"
                        style={{ background: accent.color }}
                      >
                        {contentIcon(item.content_type)}
                      </span>
                      <span className="font-medium text-text flex-1">{item.title}</span>
                      <Play className="w-4 h-4 text-text-muted" aria-hidden="true" />
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </Card>

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
            onClose={() => setActiveVideoMaterial(null)}
          />
        )}
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
          onClose={() => setActiveVideoMaterial(null)}
        />
      )}

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
                      {isEnrolled && (
                        <Button
                          onClick={() => handleStartSession(mod)}
                          disabled={Boolean(activeSession)}
                          className="w-full sm:w-auto"
                        >
                          <Play className="w-4 h-4" />
                          Start focus session
                        </Button>
                      )}
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
