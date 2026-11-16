import { useState, useEffect, useRef, useCallback } from 'react';
import {
  X,
  Play,
  Pause,
  AlertCircle,
  Square,
  RefreshCw,
  Video,
  Volume2,
  VolumeX,
  Eye,
  EyeOff,
  Coffee,
  Maximize,
  Minimize,
} from 'lucide-react';
import sessionService from '../../services/sessionService';
import FocusInterventionOverlay from './FocusInterventionOverlay';
import ScreenCalibrationOverlay from './ScreenCalibrationOverlay';
import GazeSelfTest from './GazeSelfTest';
import WebcamCapture from '../monitoring/WebcamCapture';
import FocusBuddy from './FocusBuddy';
import DemoPanel from './DemoPanel';
import InterventionTriggerSidebar from './InterventionTriggerSidebar';
import EvalTerminal from './EvalTerminal';
import { useEvalMode } from '../../hooks/useEvalMode';
import SessionSummary from './SessionSummary';
import { useMonitoringSession } from '../../hooks/useMonitoringSession';
import { useHeartbeatBus } from '../../hooks/useHeartbeatBus';
import { useFullscreen } from '../../hooks/useFullscreen';
import { usePreferences } from '../../context/PreferencesContext';
import { interventionShouldPauseVideo } from '../../utils/interventionPause';
import { buildLocalDemoIntervention } from '../../utils/demoInterventions';

const CONTROLS_HIDE_MS = 3000;

function formatClock(seconds) {
  if (!Number.isFinite(seconds) || seconds < 0) return '0:00';
  const total = Math.floor(seconds);
  const minutes = Math.floor(total / 60);
  const remain = total % 60;
  return `${minutes}:${String(remain).padStart(2, '0')}`;
}

function n1(value) {
  return typeof value === 'number' && Number.isFinite(value) ? value.toFixed(1) : '—';
}

function LiveFeedReadout({ feed, verdict, onHide }) {
  const label = String(feed?.verdict || verdict || 'WAITING').toUpperCase();
  const bar =
    label === 'DISTRACTED'
      ? 'bg-red-600'
      : label === 'FOCUSED'
        ? 'bg-green-600'
        : label === 'UNKNOWN'
          ? 'bg-amber-600'
          : 'bg-slate-600';
  const prob =
    typeof feed?.distract_prob === 'number'
      ? feed.distract_prob.toFixed(2)
      : typeof feed?.confidence === 'number'
        ? feed.confidence.toFixed(2)
        : '—';
  const probs = feed?.gaze_probs;
  const gazeText = probs
    ? `${feed.gaze_label || 'gaze'}  c${Number(probs.center).toFixed(2)} l${Number(probs.left).toFixed(2)} r${Number(probs.right).toFixed(2)} d${Number(probs.down).toFixed(2)}`
    : feed?.gaze_label
      ? feed.gaze_label
      : feed?.on_screen === true
        ? `on screen ${n1(feed.screen_x)}, ${n1(feed.screen_y)}`
        : feed?.on_screen === false
          ? `off screen ${n1(feed.screen_x)}, ${n1(feed.screen_y)}`
          : '—';
  return (
    <div className="mt-1.5 space-y-1 text-[11px] leading-tight">
      <div className={`${bar} rounded px-2 py-1 font-bold tracking-wide`}>
        {label}  p={prob}
        {feed?.ml_mode ? `  ${feed.ml_mode}` : ''}
      </div>
      <div>M1 gaze {gazeText}</div>
      <div>
        M2 yaw {n1(feed?.head_pose_yaw)} pitch {n1(feed?.head_pose_pitch)} roll {n1(feed?.head_pose_roll)}
      </div>
      <div>
        M3 eng {typeof feed?.engagement_score === 'number' ? feed.engagement_score.toFixed(2) : '—'}
        {feed?.face_detected === false ? '  no face' : ''}
      </div>
      <button
        type="button"
        onClick={onHide}
        className="inline-flex items-center gap-1 min-h-7 font-semibold text-white/80 cursor-pointer"
      >
        <EyeOff className="w-3.5 h-3.5" aria-hidden="true" /> Hide feed
      </button>
    </div>
  );
}

function LessonTimeline({ currentTime, duration, onSeek, overlay = false }) {
  const max = Number.isFinite(duration) && duration > 0 ? duration : 0;
  const value = max > 0 ? Math.min(Math.max(0, currentTime), max) : 0;
  return (
    <div className={`flex items-center gap-3 w-full ${overlay ? 'text-white' : 'text-text'}`}>
      <span className="tabular-nums font-semibold shrink-0 w-10 text-right">{formatClock(value)}</span>
      <input
        type="range"
        min={0}
        max={max || 0}
        step={0.1}
        value={value}
        disabled={!max}
        aria-label="Lesson timeline"
        aria-valuemin={0}
        aria-valuemax={Math.round(max)}
        aria-valuenow={Math.round(value)}
        aria-valuetext={`${formatClock(value)} of ${formatClock(max)}`}
        onChange={(e) => onSeek(Number(e.target.value))}
        className="flex-1 h-2 cursor-pointer accent-primary disabled:opacity-40 disabled:cursor-not-allowed"
      />
      <span className={`tabular-nums shrink-0 w-10 ${overlay ? 'text-white/80' : 'text-text-muted'}`}>
        {formatClock(max)}
      </span>
    </div>
  );
}

export const VideoLearningPlayer = ({
  material,
  moduleTitle,
  onClose,
  gazeCalibrated = false,
  onCalibrationSaved,
  onLessonComplete,
}) => {
  const videoRef = useRef(null);
  const stageRef = useRef(null);
  const wasPlayingBeforePromptRef = useRef(false);
  // Who paused the video. Either reason stops new interventions on the server;
  // 'intervention' means a prompt is holding playback until the student answers.
  const pauseCauseRef = useRef(null);
  const activeInterventionRef = useRef(null);
  const controlsTimerRef = useRef(null);
  const lessonFinishedRef = useRef(false);
  const finishLessonRef = useRef(() => {});
  const { showCameraPreview, updatePreferences } = usePreferences();

  const [sessionSummary, setSessionSummary] = useState(null);
  const [activeIntervention, setActiveIntervention] = useState(null);
  const [isPlaying, setIsPlaying] = useState(false);
  const [isMuted, setIsMuted] = useState(false);
  const [currentTime, setCurrentTime] = useState(0);
  const [duration, setDuration] = useState(0);
  const [bootError, setBootError] = useState(null);
  const [triggerError, setTriggerError] = useState(null);
  const [calibratingOpen, setCalibratingOpen] = useState(false);
  const [calibKey, setCalibKey] = useState(0);
  const [selfTestOpen, setSelfTestOpen] = useState(false); // PLAN 8 guided gaze test
  const selfTestOpenRef = useRef(false);
  const { onHeartbeat, subscribeHeartbeat } = useHeartbeatBus();
  const [fsPreview, setFsPreview] = useState(false); // camera thumbnail in fullscreen: hidden by default
  const [liveFeedOpen, setLiveFeedOpen] = useState(true);
  const [controlsVisible, setControlsVisible] = useState(true);
  const [simulateIgnore, setSimulateIgnore] = useState(false);

  const { isFullscreen, toggle: toggleFullscreen, exit: exitFullscreen } = useFullscreen(stageRef);
  // PLAN 7: evaluation terminal (DEMO_MODE or ?eval=1).
  const evalMode = useEvalMode();

  // A newly arrived intervention REPLACES the one on screen (e.g. an unanswered T1
  // banner is superseded by the T2 pacing pause).
  const handleInterventionFromMl = useCallback((intervention) => {
    // The gaze self-test deliberately looks away; don't pop prompts over it.
    if (selfTestOpenRef.current) return;
    const video = videoRef.current;
    if (video) {
      if (!activeInterventionRef.current) {
        wasPlayingBeforePromptRef.current = !video.paused;
      }
      // Pace reduction is applied only after the child accepts (see response handler).
      if (interventionShouldPauseVideo(intervention)) {
        pauseCauseRef.current = 'intervention';
        video.pause();
        setIsPlaying(false);
      }
    }
    activeInterventionRef.current = intervention;
    setActiveIntervention(intervention);
  }, []);

  useEffect(() => {
    activeInterventionRef.current = activeIntervention;
  }, [activeIntervention]);

  const {
    webcamRef,
    canvasRef,
    cameraActive,
    activeSession,
    lastVerdict,
    mlMode,
    confidence,
    gazeDebug,
    liveFeed,
    loading,
    error: monitorError,
    startMonitoredSession,
    stopMonitoredSession,
    triggerManualIntervention,
    setContentState,
    setCalibrating,
    setCalibrationTarget,
    finishCalibration: finishScreenCalibration,
    faceDetected,
    evalLog,
    addEvalMark,
    clearEvalLog,
  } = useMonitoringSession({
    intervalMs: 1000, // PLAN 8: 1 s heartbeat so T1 lands ~3-4 s after looking away
    onIntervention: handleInterventionFromMl,
    onHeartbeat,
    // While the lesson plays out loud, the mic hears the lesson, not the room.
    lessonAudioActive: isPlaying && !isMuted,
    evalCapture: evalMode.enabled,
  });

  const beginCalibration = useCallback(() => {
    setCalibKey((k) => k + 1);
    setCalibratingOpen(true);
    setCalibrating(true);
  }, [setCalibrating]);

  /** Close the overlay (the overlay itself already flushed the 'finish' heartbeat). */
  const closeCalibration = useCallback(() => {
    setCalibratingOpen(false);
    setCalibrating(false);
  }, [setCalibrating]);

  const handleCalibrationDone = useCallback(
    async (result) => {
      closeCalibration();
      if (result?.ok) {
        await onCalibrationSaved?.();
      }
    },
    [closeCalibration, onCalibrationSaved]
  );

  useEffect(() => {
    selfTestOpenRef.current = selfTestOpen;
  }, [selfTestOpen]);

  const openSelfTest = useCallback(() => setSelfTestOpen(true), []);
  const closeSelfTest = useCallback(() => setSelfTestOpen(false), []);
  const recalibrateFromSelfTest = useCallback(() => {
    setSelfTestOpen(false);
    beginCalibration();
  }, [beginCalibration]);

  const previewVisible = isFullscreen ? fsPreview : showCameraPreview;
  const toggleCameraPreview = useCallback(() => {
    if (isFullscreen) setFsPreview((v) => !v);
    else updatePreferences({ showCameraPreview: !showCameraPreview });
  }, [isFullscreen, showCameraPreview, updatePreferences]);

  // Auto-hide the minimal fullscreen control bar after a few idle seconds.
  const wakeControls = useCallback(() => {
    setControlsVisible(true);
    if (controlsTimerRef.current) clearTimeout(controlsTimerRef.current);
    controlsTimerRef.current = setTimeout(() => setControlsVisible(false), CONTROLS_HIDE_MS);
  }, []);

  useEffect(() => {
    if (isFullscreen) {
      // Start the idle countdown when fullscreen begins (state is reset in handleToggleFullscreen).
      controlsTimerRef.current = setTimeout(() => setControlsVisible(false), CONTROLS_HIDE_MS);
    }
    return () => {
      if (controlsTimerRef.current) clearTimeout(controlsTimerRef.current);
    };
  }, [isFullscreen]);

  const handleToggleFullscreen = useCallback(() => {
    if (!isFullscreen) {
      setControlsVisible(true);
      setFsPreview(false); // camera thumbnail is hidden by default in fullscreen
    }
    return toggleFullscreen();
  }, [isFullscreen, toggleFullscreen]);

  // F toggles fullscreen (ignored while typing or with modifiers).
  useEffect(() => {
    const onKey = (e) => {
      if (e.key !== 'f' && e.key !== 'F') return;
      if (e.ctrlKey || e.metaKey || e.altKey) return;
      const tag = e.target?.tagName;
      if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT' || e.target?.isContentEditable) {
        return;
      }
      if (!activeSession || calibratingOpen) return;
      e.preventDefault();
      handleToggleFullscreen();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [activeSession, calibratingOpen, handleToggleFullscreen]);

  const resolveMediaUrl = (mat) => {
    if (!mat) return '';
    // Authenticated route (JWT via query string for <video src>).
    if (mat.id) {
      const apiBase = import.meta.env.VITE_API_BASE_URL || 'http://localhost:5000/api';
      const token = localStorage.getItem('access_token') || '';
      return `${apiBase}/courses/materials/${mat.id}/file?token=${encodeURIComponent(token)}`;
    }
    const fileUrl = mat.file_url;
    if (!fileUrl) return '';
    if (fileUrl.startsWith('http://') || fileUrl.startsWith('https://')) {
      return fileUrl;
    }
    const apiBase = import.meta.env.VITE_API_BASE_URL || 'http://localhost:5000/api';
    const origin = apiBase.replace(/\/api\/?$/, '');
    return `${origin}${fileUrl.startsWith('/') ? '' : '/'}${fileUrl}`;
  };

  const videoSrc = resolveMediaUrl(material);

  const bootGenRef = useRef(0);
  const startingMonitorRef = useRef(false);
  const [startingMonitor, setStartingMonitor] = useState(false);

  // Stop session only when the player truly leaves (not StrictMode soft remount)
  useEffect(() => {
    bootGenRef.current += 1;
    return () => {
      // Defer so StrictMode's immediate remount can reuse; hard unmount still stops.
      const genAtCleanup = bootGenRef.current;
      setTimeout(() => {
        if (bootGenRef.current === genAtCleanup) {
          stopMonitoredSession().catch(() => {});
        }
      }, 0);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (
      activeIntervention &&
      videoRef.current &&
      interventionShouldPauseVideo(activeIntervention)
    ) {
      pauseCauseRef.current = 'intervention';
      videoRef.current.pause();
      setIsPlaying(false);
    }
  }, [activeIntervention]);

  /** Camera + ML session begin on the first Play, not when the player opens. */
  const ensureMonitoringStarted = useCallback(async () => {
    if (activeSession || startingMonitorRef.current) return { ok: Boolean(activeSession) };
    if (!material?.module_id) {
      setBootError('Missing module id for monitored video session.');
      return { ok: false };
    }
    startingMonitorRef.current = true;
    setStartingMonitor(true);
    setBootError(null);
    const gen = ++bootGenRef.current;
    try {
      const result = await startMonitoredSession(material.module_id);
      if (gen !== bootGenRef.current) return { ok: false };
      if (!result?.ok) {
        setBootError(result?.error || monitorError || 'Failed to start monitored session.');
        return { ok: false };
      }
      if (!gazeCalibrated) {
        beginCalibration();
        return { ok: true, calibrating: true };
      }
      return { ok: true };
    } finally {
      startingMonitorRef.current = false;
      setStartingMonitor(false);
    }
  }, [
    activeSession,
    beginCalibration,
    gazeCalibrated,
    material?.module_id,
    monitorError,
    startMonitoredSession,
  ]);

  const handleTogglePlay = async () => {
    if (!videoRef.current) return;
    if (isPlaying) {
      pauseCauseRef.current = 'user';
      videoRef.current.pause();
      setIsPlaying(false);
      setContentState('paused', 'user');
      return;
    }
    const started = await ensureMonitoringStarted();
    if (!started?.ok) return;
    // Wait for screen calibration before counting play as monitoring time.
    if (started.calibrating || calibratingOpen) return;
    pauseCauseRef.current = null;
    videoRef.current.play()?.catch?.(() => {});
    setIsPlaying(true);
    setContentState('playing');
  };

  const handleToggleMute = () => {
    if (!videoRef.current) return;
    videoRef.current.muted = !isMuted;
    setIsMuted(!isMuted);
  };

  const syncTimeline = () => {
    const video = videoRef.current;
    if (!video) return;
    setCurrentTime(video.currentTime || 0);
    if (Number.isFinite(video.duration)) setDuration(video.duration);
  };

  const handleSeek = (seconds) => {
    const video = videoRef.current;
    if (!video || !Number.isFinite(seconds)) return;
    const knownDuration = Number.isFinite(video.duration) && video.duration > 0;
    const max = knownDuration ? video.duration : seconds;
    const next = Math.max(0, Math.min(seconds, max));
    // Dragging the demo timeline to the end must finish the lesson. A paused
    // video seeked to its duration often never fires `ended`.
    const atEnd =
      knownDuration &&
      (next >= video.duration - 1 || next / video.duration >= 0.98);
    video.currentTime = atEnd ? max : next;
    setCurrentTime(atEnd ? max : next);
    if (isFullscreen) wakeControls();
    if (atEnd) {
      video.pause();
      finishLessonRef.current();
    }
  };

  const resumeIfWasPlaying = useCallback(() => {
    if (!videoRef.current) return;
    if (wasPlayingBeforePromptRef.current) {
      videoRef.current.play().catch(() => {});
      setIsPlaying(true);
      setContentState('playing');
    } else {
      // The student had it paused before the prompt — still their pause.
      pauseCauseRef.current = 'user';
      setContentState('paused', 'user');
    }
  }, [setContentState]);

  const handleInterventionResponse = async (interventionId, userResponse, extra = {}) => {
    if (!activeSession) {
      // Local break (null id) — clear overlay only
      if (!interventionId) {
        setActiveIntervention(null);
        resumeIfWasPlaying();
      }
      return null;
    }
    if (extra.dismiss_only) {
      setActiveIntervention(null);
      resumeIfWasPlaying();
      return null;
    }
    // Null-id local break: no backend round-trip
    if (!interventionId) {
      setActiveIntervention(null);
      resumeIfWasPlaying();
      return null;
    }
    try {
      const res = await sessionService.recordInterventionResponse(
        activeSession.session_id,
        interventionId,
        userResponse,
        extra
      );
      if (!extra.defer_clear) {
        setActiveIntervention(null);
        if (userResponse === 'ended') {
          handleStopSession();
        } else {
          // Apply pace reduction only after the child accepts.
          const factor = activeIntervention?.payload?.pacing_factor;
          if (
            userResponse === 'reengaged' &&
            typeof factor === 'number' &&
            factor > 0 &&
            videoRef.current
          ) {
            videoRef.current.playbackRate = factor;
          }
          resumeIfWasPlaying();
        }
      }
      return res;
    } catch (err) {
      console.error('Failed to record intervention response:', err);
      setActiveIntervention(null);
      resumeIfWasPlaying();
      return null;
    }
  };

  const handleStopSession = async () => {
    try {
      closeCalibration();
      exitFullscreen();
      if (videoRef.current) {
        videoRef.current.pause();
        videoRef.current.playbackRate = 1.0; // revert pace reduction at session end
        setIsPlaying(false);
        setContentState('ended');
      }
      const summary = await stopMonitoredSession();
      if (summary) setSessionSummary(summary);
      setActiveIntervention(null);
    } catch (err) {
      console.error('Failed to stop video learning session:', err);
    }
  };

  const finishLesson = () => {
    if (lessonFinishedRef.current) return;
    lessonFinishedRef.current = true;
    setIsPlaying(false);
    setContentState('ended');
    if (material?.quiz_id && onLessonComplete) {
      exitFullscreen();
      onLessonComplete();
      stopMonitoredSession().catch(() => {});
      onClose?.();
      return;
    }
    handleStopSession();
  };
  finishLessonRef.current = finishLesson;

  const handleNeedBreak = () => {
    if (videoRef.current) {
      pauseCauseRef.current = 'intervention'; // student-requested break: held, not nudged
      videoRef.current.pause();
      setIsPlaying(false);
    }
    setActiveIntervention({
      intervention_id: null,
      tier: 4,
      intervention_type: 'suggest_break',
      message: 'Take a moment — stretch or breathe.',
      payload: { break_seconds: 60 },
    });
  };

  const displayError = bootError || monitorError;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-3 md:p-6 bg-bg font-sans">
      <div className="learning-panel max-w-5xl w-full overflow-hidden flex flex-col max-h-[92vh] bg-learning">

        <div className="focus-session-chrome p-4 md:px-6 flex items-center justify-between gap-4">
          <div className="flex items-center gap-3 min-w-0">
            <div className="w-10 h-10 bg-primary-soft text-primary rounded-xl flex items-center justify-center border border-border shrink-0">
              <Video className="w-5 h-5" aria-hidden="true" />
            </div>
            <div className="min-w-0">
              <span className="text-xs font-semibold text-text-muted block truncate">
                {moduleTitle || 'Video learning session'}
              </span>
              <h2 className="text-sm md:text-base font-display font-bold text-text truncate">
                {material?.title || 'Course video material'}
              </h2>
            </div>
          </div>

          <div className="flex items-center gap-2 shrink-0 flex-wrap justify-end">
            {activeSession && (
              <FocusBuddy
                onTrack={!lastVerdict || String(lastVerdict).toUpperCase() === 'FOCUSED'}
                unknown={String(lastVerdict || '').toUpperCase() === 'UNKNOWN'}
                className="px-2"
              />
            )}
            <button
              type="button"
              onClick={async () => {
                if (activeSession) await handleStopSession();
                onClose();
              }}
              className="min-h-11 min-w-11 inline-flex items-center justify-center text-text-muted hover:text-text bg-bg hover:bg-surface-raised rounded-xl border border-border cursor-pointer"
              aria-label="Close player and end session"
            >
              <X className="w-5 h-5" />
            </button>
          </div>
        </div>

        {/*
          Video stage: this container (not the native <video>) is what goes fullscreen,
          so intervention overlays, the camera thumbnail, minimal controls and the demo
          sidebar all stay visible.
        */}
        <div
          ref={stageRef}
          onMouseMove={isFullscreen ? wakeControls : undefined}
          onTouchStart={isFullscreen ? wakeControls : undefined}
          className={`relative flex-1 bg-black flex items-center justify-center overflow-hidden ${
            isFullscreen ? 'w-full h-full' : 'min-h-[320px]'
          }`}
        >
          {/* Keep webcam mounted during loading so getUserMedia can attach to a real <video> */}
          {!sessionSummary && (
            <div
              className={
                liveFeedOpen
                  ? 'absolute top-3 right-3 z-30 w-56 bg-black/80 text-white border border-white/20 rounded-xl p-2 shadow-lift'
                  : 'absolute w-40 h-28 opacity-0 pointer-events-none -z-10 left-0 top-0 overflow-hidden'
              }
              aria-hidden={!liveFeedOpen}
            >
              <WebcamCapture
                videoRef={webcamRef}
                canvasRef={canvasRef}
                cameraActive={cameraActive}
                className="w-full max-w-none aspect-video"
              />
              {liveFeedOpen && (
                <LiveFeedReadout
                  feed={liveFeed}
                  verdict={lastVerdict}
                  onHide={() => setLiveFeedOpen(false)}
                />
              )}
            </div>
          )}
          {!sessionSummary && !liveFeedOpen && (
            <button
              type="button"
              onClick={() => setLiveFeedOpen(true)}
              className="absolute top-3 right-3 z-30 min-h-9 px-3 rounded-lg bg-black/75 text-white text-xs font-semibold cursor-pointer"
            >
              Show live feed
            </button>
          )}

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
              onPauseContent={() => {
                if (videoRef.current) {
                  wasPlayingBeforePromptRef.current = !videoRef.current.paused;
                  pauseCauseRef.current = 'intervention';
                  videoRef.current.pause();
                  setIsPlaying(false);
                  setContentState('paused', 'intervention');
                }
              }}
            />
          </div>

          {!sessionSummary && !calibratingOpen && !selfTestOpen && (
            <InterventionTriggerSidebar
              sessionReady={Boolean(activeSession)}
              onShowLocal={(kind) => handleInterventionFromMl(buildLocalDemoIntervention(kind))}
              onSimulateIgnoreChange={setSimulateIgnore}
              onTriggerTier={(tier) => triggerManualIntervention(tier, false, { force: true })}
            />
          )}

          <DemoPanel
            position="absolute"
            sessionId={activeSession?.session_id}
            lastVerdict={lastVerdict}
            mlMode={mlMode}
            confidence={confidence}
            gazeDebug={gazeDebug}
            onSimulateIgnoreChange={setSimulateIgnore}
            onTriggerLocal={(kind) => handleInterventionFromMl(buildLocalDemoIntervention(kind))}
            onTriggerTier={async (tier, options) => {
              setTriggerError(null);
              try {
                await triggerManualIntervention(tier, false, options);
              } catch (err) {
                const msg = err.response?.data?.error || err.message || 'Failed to trigger intervention';
                setTriggerError(msg);
                throw err;
              }
            }}
          />

          {activeSession && !sessionSummary && (
            <EvalTerminal
              enabled={evalMode.enabled}
              autoOpen={evalMode.autoOpen}
              entries={evalLog}
              onMark={addEvalMark}
              onClear={clearEvalLog}
              onGazeTest={openSelfTest}
            />
          )}

          {/* Minimal auto-hiding controls — fullscreen only (the normal bar lives below the stage). */}
          {isFullscreen && activeSession && !sessionSummary && !calibratingOpen && (
            <div
              className={`absolute bottom-4 left-1/2 -translate-x-1/2 z-30 w-[min(42rem,92vw)] flex flex-col gap-2 rounded-2xl bg-black/70 px-3 py-2 text-white transition-opacity duration-300 ${
                controlsVisible ? 'opacity-100' : 'opacity-0 pointer-events-none'
              }`}
            >
              <LessonTimeline overlay currentTime={currentTime} duration={duration} onSeek={handleSeek} />
              <div className="flex items-center justify-center gap-2">
              <button
                type="button"
                onClick={handleTogglePlay}
                aria-label={isPlaying ? 'Pause lesson' : 'Play lesson'}
                className="min-h-11 min-w-11 inline-flex items-center justify-center rounded-xl hover:bg-white/15 cursor-pointer"
              >
                {isPlaying ? <Pause className="w-5 h-5" aria-hidden="true" /> : <Play className="w-5 h-5 fill-current" aria-hidden="true" />}
              </button>
              <button
                type="button"
                onClick={handleToggleMute}
                aria-pressed={isMuted}
                aria-label={isMuted ? 'Unmute lesson' : 'Mute lesson'}
                className="min-h-11 min-w-11 inline-flex items-center justify-center rounded-xl hover:bg-white/15 cursor-pointer"
              >
                {isMuted ? <VolumeX className="w-5 h-5" aria-hidden="true" /> : <Volume2 className="w-5 h-5" aria-hidden="true" />}
              </button>
              <button
                type="button"
                onClick={toggleCameraPreview}
                aria-pressed={fsPreview}
                aria-label={fsPreview ? 'Hide camera preview' : 'Show camera preview'}
                className="min-h-11 min-w-11 inline-flex items-center justify-center rounded-xl hover:bg-white/15 cursor-pointer"
              >
                {fsPreview ? <EyeOff className="w-5 h-5" aria-hidden="true" /> : <Eye className="w-5 h-5" aria-hidden="true" />}
              </button>
              <button
                type="button"
                onClick={handleToggleFullscreen}
                aria-label="Exit fullscreen"
                className="min-h-11 min-w-11 inline-flex items-center justify-center rounded-xl hover:bg-white/15 cursor-pointer"
              >
                <Minimize className="w-5 h-5" aria-hidden="true" />
              </button>
              </div>
            </div>
          )}

          {sessionSummary ? (
            <SessionSummary summary={sessionSummary} onClose={onClose} />
          ) : displayError && !activeSession && !startingMonitor && !loading ? (
            <div className="p-6 bg-danger/10 border border-danger rounded-2xl max-w-md text-center text-text space-y-3" role="alert">
              <AlertCircle className="w-8 h-8 text-danger mx-auto" aria-hidden="true" />
              <p className="text-sm font-semibold">{displayError}</p>
              <button
                type="button"
                onClick={onClose}
                className="px-4 py-2 min-h-11 bg-surface hover:bg-bg text-text border border-border rounded-xl text-sm font-bold cursor-pointer"
              >
                Close window
              </button>
            </div>
          ) : (
            <div className="relative w-full h-full flex items-center justify-center">
              <video
                ref={videoRef}
                src={videoSrc}
                controls={false}
                onPlay={() => {
                  if (!activeSession) return;
                  pauseCauseRef.current = null;
                  setIsPlaying(true);
                  setContentState('playing');
                }}
                onPause={() => {
                  setIsPlaying(false);
                  if (activeSession) {
                    setContentState('paused', pauseCauseRef.current || 'user');
                  }
                }}
                onTimeUpdate={syncTimeline}
                onLoadedMetadata={syncTimeline}
                onDurationChange={syncTimeline}
                onSeeked={syncTimeline}
                onEnded={() => finishLessonRef.current()}
                className={`w-full object-contain ${isFullscreen ? 'h-full' : 'max-h-[60vh]'}`}
              />
              {!activeSession && !calibratingOpen && (
                <div className="absolute inset-x-0 bottom-6 z-20 flex justify-center px-4 pointer-events-none">
                  <p className="rounded-xl bg-black/75 text-white text-xs md:text-sm font-semibold px-4 py-2.5 text-center max-w-md">
                    Press Play to start the video and begin monitoring
                  </p>
                </div>
              )}
              {(loading || startingMonitor) && (
                <div
                  className="absolute inset-0 z-25 flex flex-col items-center justify-center gap-3 bg-black/50 text-white"
                  role="status"
                >
                  <RefreshCw className="w-8 h-8 animate-spin text-primary motion-reduce:animate-none" aria-hidden="true" />
                  <span className="text-xs font-semibold">
                    Starting camera &amp; monitoring…
                  </span>
                </div>
              )}
            </div>
          )}
        </div>

        {!sessionSummary && (
          <div className="p-4 md:px-6 focus-session-chrome space-y-3 text-text text-xs">
            {triggerError && (
              <p className="text-[11px] text-warning font-medium" role="alert">{triggerError}</p>
            )}
            <LessonTimeline currentTime={currentTime} duration={duration} onSeek={handleSeek} />
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div className="flex items-center gap-2 flex-wrap">
                <button
                  type="button"
                  onClick={handleTogglePlay}
                  disabled={startingMonitor || loading}
                  aria-label={isPlaying ? 'Pause lesson' : 'Play lesson'}
                  className="px-3 min-h-11 bg-primary text-on-primary rounded-xl font-semibold flex items-center gap-2 cursor-pointer shadow-soft disabled:opacity-60"
                >
                  {isPlaying ? (
                    <Pause className="w-4 h-4" aria-hidden="true" />
                  ) : (
                    <Play className="w-4 h-4 fill-current" aria-hidden="true" />
                  )}
                  <span>
                    {startingMonitor || loading ? 'Starting…' : isPlaying ? 'Pause' : 'Play'}
                  </span>
                </button>

                <button
                  type="button"
                  onClick={handleToggleMute}
                  aria-pressed={isMuted}
                  aria-label={isMuted ? 'Unmute lesson' : 'Mute lesson'}
                  className="min-h-11 min-w-11 inline-flex items-center justify-center bg-bg text-text rounded-xl cursor-pointer border border-border"
                >
                  {isMuted ? (
                    <VolumeX className="w-4 h-4" aria-hidden="true" />
                  ) : (
                    <Volume2 className="w-4 h-4" aria-hidden="true" />
                  )}
                </button>

                <button
                  type="button"
                  onClick={toggleCameraPreview}
                  aria-pressed={previewVisible}
                  className="min-h-11 inline-flex items-center gap-1.5 px-2 font-semibold text-text-muted hover:text-text cursor-pointer"
                >
                  {showCameraPreview ? (
                    <EyeOff className="w-4 h-4" aria-hidden="true" />
                  ) : (
                    <Eye className="w-4 h-4" aria-hidden="true" />
                  )}
                  <span className="hidden sm:inline">
                    {showCameraPreview ? 'Hide camera preview' : 'Show camera preview'}
                  </span>
                </button>
              </div>

              <div className="flex items-center gap-3 flex-wrap justify-end">
                <button
                  type="button"
                  onClick={handleToggleFullscreen}
                  aria-label="Enter fullscreen (F)"
                  title="Fullscreen (F)"
                  className="inline-flex items-center gap-1.5 min-h-11 px-3 rounded-xl border border-border bg-bg text-text text-xs font-semibold cursor-pointer"
                >
                  <Maximize className="w-3.5 h-3.5" aria-hidden="true" />
                  Fullscreen
                </button>
                {activeSession && (
                  <>
                    <button
                      type="button"
                      onClick={handleNeedBreak}
                      className="inline-flex items-center gap-1.5 min-h-11 px-3 rounded-xl border border-border bg-bg text-text text-xs font-semibold cursor-pointer"
                    >
                      <Coffee className="w-3.5 h-3.5" aria-hidden="true" />
                      I need a break
                    </button>
                    <span className="hidden md:inline text-text-muted max-w-xs">
                      Hiding the preview does not stop monitoring.
                    </span>
                    <button
                      type="button"
                      onClick={() => finishLessonRef.current()}
                      className="px-4 min-h-11 bg-danger/10 text-danger border border-danger/40 rounded-xl text-xs font-bold flex items-center gap-1.5 cursor-pointer"
                    >
                      <Square className="w-3.5 h-3.5 fill-current" aria-hidden="true" />
                      <span>Complete session</span>
                    </button>
                  </>
                )}
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

export default VideoLearningPlayer;
