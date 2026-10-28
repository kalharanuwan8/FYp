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
} from 'lucide-react';
import sessionService from '../../services/sessionService';
import FocusInterventionOverlay from './FocusInterventionOverlay';
import WebcamCapture from '../monitoring/WebcamCapture';
import FocusBuddy from './FocusBuddy';
import DemoPanel from './DemoPanel';
import SessionSummary from './SessionSummary';
import { useMonitoringSession } from '../../hooks/useMonitoringSession';
import { usePreferences } from '../../context/PreferencesContext';
import { interventionShouldPauseVideo } from '../../utils/interventionPause';

export const VideoLearningPlayer = ({ material, moduleTitle, onClose }) => {
  const videoRef = useRef(null);
  const { showCameraPreview, updatePreferences } = usePreferences();

  const [sessionSummary, setSessionSummary] = useState(null);
  const [activeIntervention, setActiveIntervention] = useState(null);
  const [isPlaying, setIsPlaying] = useState(false);
  const [isMuted, setIsMuted] = useState(false);
  const [bootError, setBootError] = useState(null);
  const [triggerError, setTriggerError] = useState(null);

  const handleInterventionFromMl = useCallback((intervention) => {
    setActiveIntervention(intervention);
    if (!videoRef.current) return;
    const factor = intervention?.payload?.pacing_factor;
    if (typeof factor === 'number' && factor > 0) {
      videoRef.current.playbackRate = factor;
    }
    // Ambient cues must not interrupt playback; other types pause the lesson.
    if (interventionShouldPauseVideo(intervention)) {
      videoRef.current.pause();
      setIsPlaying(false);
    }
  }, []);

  const {
    webcamRef,
    canvasRef,
    cameraActive,
    activeSession,
    lastVerdict,
    mlMode,
    loading,
    error: monitorError,
    startMonitoredSession,
    stopMonitoredSession,
    triggerManualIntervention,
  } = useMonitoringSession({
    intervalMs: 2000,
    onIntervention: handleInterventionFromMl,
    // While the lesson plays out loud, the mic hears the lesson, not the room.
    lessonAudioActive: isPlaying && !isMuted,
  });

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

  useEffect(() => {
    const gen = ++bootGenRef.current;
    let cancelled = false;
    (async () => {
      if (!material?.module_id) {
        setBootError('Missing module id for monitored video session.');
        return;
      }
      const result = await startMonitoredSession(material.module_id);
      // Ignore stale StrictMode / rapid remount results
      if (cancelled || gen !== bootGenRef.current) {
        return;
      }
      if (!result?.ok) {
        setBootError(result?.error || monitorError || 'Failed to start monitored session.');
      }
    })();
    return () => {
      cancelled = true;
    };
    // intentionally run once per material
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [material?.module_id]);

  // Stop session only when the player truly leaves (not StrictMode soft remount)
  useEffect(() => {
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
      videoRef.current.pause();
      setIsPlaying(false);
    }
  }, [activeIntervention]);

  const handleTogglePlay = () => {
    if (!videoRef.current) return;
    if (isPlaying) {
      videoRef.current.pause();
      setIsPlaying(false);
    } else {
      videoRef.current.play();
      setIsPlaying(true);
    }
  };

  const handleToggleMute = () => {
    if (!videoRef.current) return;
    videoRef.current.muted = !isMuted;
    setIsMuted(!isMuted);
  };

  const handleInterventionResponse = async (interventionId, userResponse, extra = {}) => {
    if (!activeSession) return null;
    if (extra.dismiss_only) {
      setActiveIntervention(null);
      if (videoRef.current) {
        videoRef.current.play().catch(() => {});
        setIsPlaying(true);
      }
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
        } else if (videoRef.current) {
          videoRef.current.play().catch(() => {});
          setIsPlaying(true);
        }
      }
      return res;
    } catch (err) {
      console.error('Failed to record intervention response:', err);
      setActiveIntervention(null);
      return null;
    }
  };

  const handleStopSession = async () => {
    try {
      if (videoRef.current) {
        videoRef.current.pause();
        setIsPlaying(false);
      }
      const summary = await stopMonitoredSession();
      if (summary) setSessionSummary(summary);
      setActiveIntervention(null);
    } catch (err) {
      console.error('Failed to stop video learning session:', err);
    }
  };

  const handleNeedBreak = () => {
    if (videoRef.current) {
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

        <DemoPanel
          sessionId={activeSession?.session_id}
          lastVerdict={lastVerdict}
          mlMode={mlMode}
          onTriggerTier={async (t) => {
            setTriggerError(null);
            try {
              await triggerManualIntervention(t, false);
            } catch (err) {
              setTriggerError(
                err.response?.data?.error || 'Failed to trigger intervention'
              );
            }
          }}
        />

        <div className="relative flex-1 bg-black flex items-center justify-center min-h-[320px] overflow-hidden">
          {/* Keep webcam mounted during loading so getUserMedia can attach to a real <video> */}
          {!sessionSummary && (
            <div
              className={
                showCameraPreview
                  ? 'absolute top-3 right-3 md:top-4 md:right-4 z-20 bg-surface border border-border rounded-2xl p-2 shadow-lift flex items-center gap-3 max-w-[calc(100%-1.5rem)]'
                  : 'absolute w-40 h-28 opacity-0 pointer-events-none -z-10 left-0 top-0 overflow-hidden'
              }
              aria-hidden={!showCameraPreview}
            >
              <WebcamCapture
                videoRef={webcamRef}
                canvasRef={canvasRef}
                cameraActive={cameraActive}
                compact
              />
              {showCameraPreview && (
                <div className="text-[11px] pr-2">
                  <div className="flex items-center gap-1.5 font-bold text-text">
                    <span className={`w-2 h-2 rounded-full ${cameraActive ? 'bg-success' : 'bg-warning'}`} aria-hidden="true" />
                    <span>{cameraActive ? 'Camera on' : loading ? 'Starting…' : 'Camera'}</span>
                  </div>
                  <span className="text-[10px] text-text-muted block mt-0.5">
                    Preview stays on this device
                  </span>
                  <button
                    type="button"
                    onClick={() => updatePreferences({ showCameraPreview: false })}
                    className="mt-1 inline-flex items-center gap-1 min-h-8 font-semibold text-primary cursor-pointer"
                  >
                    <EyeOff className="w-3.5 h-3.5" aria-hidden="true" /> Hide preview
                  </button>
                </div>
              )}
            </div>
          )}

          <FocusInterventionOverlay
            intervention={activeIntervention}
            onRespond={handleInterventionResponse}
            onPauseContent={() => {
              if (videoRef.current) {
                videoRef.current.pause();
                setIsPlaying(false);
              }
            }}
          />

          {loading ? (
            <div className="flex flex-col items-center gap-3 text-text-muted py-16" role="status">
              <RefreshCw className="w-8 h-8 animate-spin text-primary motion-reduce:animate-none" aria-hidden="true" />
              <span className="text-xs font-semibold">
                Starting camera &amp; background ML models…
              </span>
            </div>
          ) : displayError && !activeSession ? (
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
          ) : sessionSummary ? (
            <SessionSummary summary={sessionSummary} onClose={onClose} />
          ) : (
            <div className="relative w-full h-full flex items-center justify-center">
              <video
                ref={videoRef}
                src={videoSrc}
                controls={false}
                onPlay={() => setIsPlaying(true)}
                onPause={() => setIsPlaying(false)}
                onEnded={() => {
                  setIsPlaying(false);
                  handleStopSession();
                }}
                className="max-h-[60vh] w-full object-contain"
              />
            </div>
          )}
        </div>

        {!sessionSummary && activeSession && (
          <div className="p-4 md:px-6 focus-session-chrome space-y-3 text-text text-xs">
            {triggerError && (
              <p className="text-[11px] text-warning font-medium" role="alert">{triggerError}</p>
            )}
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div className="flex items-center gap-2 flex-wrap">
                <button
                  type="button"
                  onClick={handleTogglePlay}
                  aria-label={isPlaying ? 'Pause lesson' : 'Play lesson'}
                  className="px-3 min-h-11 bg-primary text-on-primary rounded-xl font-semibold flex items-center gap-2 cursor-pointer shadow-soft"
                >
                  {isPlaying ? (
                    <Pause className="w-4 h-4" aria-hidden="true" />
                  ) : (
                    <Play className="w-4 h-4 fill-current" aria-hidden="true" />
                  )}
                  <span>{isPlaying ? 'Pause' : 'Play'}</span>
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
                  onClick={() => updatePreferences({ showCameraPreview: !showCameraPreview })}
                  aria-pressed={showCameraPreview}
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
                  onClick={handleStopSession}
                  className="px-4 min-h-11 bg-danger/10 text-danger border border-danger/40 rounded-xl text-xs font-bold flex items-center gap-1.5 cursor-pointer"
                >
                  <Square className="w-3.5 h-3.5 fill-current" aria-hidden="true" />
                  <span>Complete session</span>
                </button>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

export default VideoLearningPlayer;
