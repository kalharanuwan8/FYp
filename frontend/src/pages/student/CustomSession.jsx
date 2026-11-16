import { useCallback, useEffect, useRef, useState } from 'react';
import { useOutletContext } from 'react-router-dom';
import { FileUp, Pause, Play, Square, Trash2, Upload } from 'lucide-react';
import { sessionService } from '../../services/sessionService';
import { useMonitoringSession } from '../../hooks/useMonitoringSession';
import WebcamCapture from '../../components/monitoring/WebcamCapture';
import FocusInterventionOverlay from '../../components/student/FocusInterventionOverlay';
import SessionSummary from '../../components/student/SessionSummary';
import { Button, Card, EmptyState, ErrorBanner, LoadingSpinner } from '../../components/common';

const ACCEPT =
  '.pdf,.txt,.md,.csv,.doc,.docx,.ppt,.pptx,.mp4,.webm,.mov,.mkv,.png,.jpg,.jpeg,.gif,.webp,.mp3,.wav,.m4a,.ogg';

const KIND_LABEL = {
  video: 'Video',
  image: 'Image',
  audio: 'Audio',
  document: 'Document',
  other: 'File',
};

function fileSrc(upload) {
  const apiBase = import.meta.env.VITE_API_BASE_URL || 'http://localhost:5000/api';
  const token = localStorage.getItem('access_token') || '';
  return `${apiBase}/session/custom/uploads/${upload.id}/file?token=${encodeURIComponent(token)}`;
}

function CustomMonitor({ upload, onFinished }) {
  const { setFocusMode } = useOutletContext() || {};
  const mediaRef = useRef(null);
  const pauseCauseRef = useRef(null);
  const wasPlayingRef = useRef(false);
  const bootGenRef = useRef(0);
  const [activeIntervention, setActiveIntervention] = useState(null);
  const [sessionSummary, setSessionSummary] = useState(null);
  const [bootError, setBootError] = useState(null);
  const [isPlaying, setIsPlaying] = useState(false);

  const canPause = upload.content_kind === 'video' || upload.content_kind === 'audio';
  const startingMonitorRef = useRef(false);
  const [startingMonitor, setStartingMonitor] = useState(false);

  const {
    webcamRef,
    canvasRef,
    cameraActive,
    activeSession,
    loading,
    error: monitorError,
    startCustomSession,
    stopMonitoredSession,
    setContentState,
  } = useMonitoringSession({
    intervalMs: 1000,
    onIntervention: (intervention) => {
      const media = mediaRef.current;
      if (media && canPause && typeof media.pause === 'function') {
        wasPlayingRef.current = !media.paused;
        if (!media.paused) {
          pauseCauseRef.current = 'intervention';
          media.pause();
          setIsPlaying(false);
        }
      }
      setActiveIntervention(intervention);
    },
  });

  useEffect(() => {
    setFocusMode?.(true);
    return () => setFocusMode?.(false);
  }, [setFocusMode]);

  // Documents and images have no playhead — start monitoring immediately.
  // Video/audio wait for the first Play.
  useEffect(() => {
    if (canPause) {
      bootGenRef.current += 1;
      return () => {
        const genAtCleanup = bootGenRef.current;
        setTimeout(() => {
          if (bootGenRef.current === genAtCleanup) {
            stopMonitoredSession().catch(() => {});
          }
        }, 0);
      };
    }
    const gen = ++bootGenRef.current;
    let cancelled = false;
    (async () => {
      const result = await startCustomSession(upload.id);
      if (cancelled || gen !== bootGenRef.current) return;
      if (!result?.ok) {
        setBootError(result?.error || 'Could not start monitoring.');
        return;
      }
      setContentState('playing');
    })();
    return () => {
      cancelled = true;
      const genAtCleanup = gen;
      setTimeout(() => {
        if (bootGenRef.current === genAtCleanup) {
          stopMonitoredSession().catch(() => {});
        }
      }, 0);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [upload.id, canPause]);

  const ensureMonitoringStarted = useCallback(async () => {
    if (activeSession || startingMonitorRef.current) return Boolean(activeSession);
    startingMonitorRef.current = true;
    setStartingMonitor(true);
    setBootError(null);
    const gen = ++bootGenRef.current;
    try {
      const result = await startCustomSession(upload.id);
      if (gen !== bootGenRef.current) return false;
      if (!result?.ok) {
        setBootError(result?.error || 'Could not start monitoring.');
        return false;
      }
      return true;
    } finally {
      startingMonitorRef.current = false;
      setStartingMonitor(false);
    }
  }, [activeSession, startCustomSession, upload.id]);

  const resumeIfWasPlaying = useCallback(() => {
    const media = mediaRef.current;
    if (!media || !canPause) return;
    if (wasPlayingRef.current) {
      media.play?.().catch(() => {});
      setIsPlaying(true);
      setContentState('playing');
    }
    wasPlayingRef.current = false;
    pauseCauseRef.current = null;
  }, [canPause, setContentState]);

  const handleStop = useCallback(async () => {
    try {
      if (mediaRef.current?.pause) mediaRef.current.pause();
      if (activeSession) setContentState('ended');
      const summary = await stopMonitoredSession();
      setActiveIntervention(null);
      if (summary) setSessionSummary(summary);
      else onFinished?.();
    } catch (err) {
      setBootError(err.response?.data?.error || 'Could not stop the session.');
    }
  }, [activeSession, onFinished, setContentState, stopMonitoredSession]);

  const handleInterventionResponse = async (interventionId, userResponse, extra = {}) => {
    if (!interventionId || extra.dismiss_only) {
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
        if (userResponse === 'ended') handleStop();
        else resumeIfWasPlaying();
      }
      return res;
    } catch (err) {
      console.error('Failed to record intervention response:', err);
      setActiveIntervention(null);
      resumeIfWasPlaying();
      return null;
    }
  };

  const togglePlay = async () => {
    const media = mediaRef.current;
    if (!media) return;
    if (isPlaying) {
      pauseCauseRef.current = 'user';
      media.pause();
      setIsPlaying(false);
      setContentState('paused', 'user');
      return;
    }
    const ok = await ensureMonitoringStarted();
    if (!ok) return;
    pauseCauseRef.current = null;
    media.play?.().catch(() => {});
    setIsPlaying(true);
    setContentState('playing');
  };

  const src = fileSrc(upload);
  const displayError = bootError || monitorError;

  return (
    <div className="fixed inset-0 z-50 bg-bg flex flex-col">
      <header className="flex items-center justify-between gap-3 px-4 md:px-6 py-3 border-b border-border bg-surface">
        <div className="min-w-0">
          <h1 className="font-display font-bold text-text truncate">{upload.title}</h1>
          <p className="text-xs text-text-muted">
            {canPause && !activeSession
              ? 'Press Play to start the media and begin monitoring.'
              : 'Monitoring is on. Prompts are chosen for you — a reminder, a pause check, or a short break.'}
          </p>
        </div>
        <Button type="button" variant="secondary" size="sm" onClick={handleStop}>
          <Square className="w-4 h-4" aria-hidden="true" />
          End session
        </Button>
      </header>

      <div className="relative flex-1 bg-black flex items-center justify-center overflow-hidden">
        {!sessionSummary && (activeSession || startingMonitor || loading) && (
          <div className="absolute top-3 right-3 z-30 w-40">
            <WebcamCapture videoRef={webcamRef} canvasRef={canvasRef} cameraActive={cameraActive} compact />
          </div>
        )}

        {sessionSummary ? (
          <div className="bg-bg w-full h-full" />
        ) : !canPause && loading && !activeSession ? (
          <LoadingSpinner label="Starting camera and monitoring…" />
        ) : displayError && !activeSession && !(canPause && !startingMonitor) ? (
          <div className="p-6 text-center text-sm text-text max-w-md">
            <p className="font-semibold">{displayError}</p>
            <Button className="mt-4" variant="secondary" onClick={onFinished}>
              Back
            </Button>
          </div>
        ) : displayError && canPause && !activeSession ? (
          <div className="p-6 text-center text-sm text-text max-w-md space-y-3">
            <p className="font-semibold">{displayError}</p>
            <Button variant="secondary" onClick={onFinished}>
              Back
            </Button>
          </div>
        ) : upload.content_kind === 'video' ? (
          <>
            <video
              ref={mediaRef}
              src={src}
              className="w-full max-h-full object-contain"
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
            />
            {!activeSession && !startingMonitor && (
              <div className="absolute inset-x-0 bottom-6 z-20 flex justify-center px-4 pointer-events-none">
                <p className="rounded-xl bg-black/75 text-white text-xs md:text-sm font-semibold px-4 py-2.5 text-center max-w-md">
                  Press Play to start the video and begin monitoring
                </p>
              </div>
            )}
          </>
        ) : upload.content_kind === 'audio' ? (
          <div className="p-8 w-full max-w-lg">
            <audio
              ref={mediaRef}
              src={src}
              className="w-full"
              controls
              onPlay={async () => {
                const ok = activeSession || (await ensureMonitoringStarted());
                if (!ok) {
                  mediaRef.current?.pause?.();
                  return;
                }
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
            />
            {!activeSession && !startingMonitor && (
              <p className="mt-3 text-center text-xs text-white/80 font-semibold">
                Press play on the audio to begin monitoring
              </p>
            )}
          </div>
        ) : upload.content_kind === 'image' ? (
          <img src={src} alt={upload.title} className="max-w-full max-h-full object-contain" />
        ) : (
          <iframe title={upload.title} src={src} className="w-full h-full bg-surface" />
        )}

        {(loading || startingMonitor) && canPause && (
          <div className="absolute inset-0 z-25 flex items-center justify-center bg-black/40">
            <LoadingSpinner label="Starting camera and monitoring…" />
          </div>
        )}

        <FocusInterventionOverlay
          intervention={activeIntervention}
          onRespond={handleInterventionResponse}
          onPauseContent={() => {
            if (mediaRef.current?.pause) {
              pauseCauseRef.current = 'intervention';
              mediaRef.current.pause();
              setIsPlaying(false);
              setContentState('paused', 'intervention');
            }
          }}
        />
      </div>

      {canPause && !sessionSummary && (
        <div className="p-4 bg-surface border-t border-border">
          <button
            type="button"
            onClick={togglePlay}
            disabled={startingMonitor || loading}
            className="px-3 min-h-11 bg-primary text-on-primary rounded-xl font-semibold inline-flex items-center gap-2 cursor-pointer disabled:opacity-60"
          >
            {isPlaying ? <Pause className="w-4 h-4" /> : <Play className="w-4 h-4 fill-current" />}
            {startingMonitor || loading ? 'Starting…' : isPlaying ? 'Pause' : 'Play'}
          </button>
        </div>
      )}

      {sessionSummary && (
        <SessionSummary
          summary={sessionSummary}
          closeLabel="Done"
          onClose={() => {
            setSessionSummary(null);
            onFinished?.();
          }}
        />
      )}
    </div>
  );
}

export default function CustomSession() {
  const [uploads, setUploads] = useState([]);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState(null);
  const [activeUpload, setActiveUpload] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await sessionService.listCustomUploads();
      setUploads(data.uploads || []);
    } catch (err) {
      setError(err.response?.data?.error || 'Could not load your files.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const onFile = async (event) => {
    const file = event.target.files?.[0];
    event.target.value = '';
    if (!file) return;
    setUploading(true);
    setError(null);
    try {
      const created = await sessionService.uploadCustomFile(file);
      setUploads((prev) => [created, ...prev.filter((row) => row.id !== created.id)]);
    } catch (err) {
      setError(err.response?.data?.error || 'Upload failed.');
    } finally {
      setUploading(false);
    }
  };

  const removeUpload = async (upload) => {
    setError(null);
    try {
      await sessionService.deleteCustomUpload(upload.id);
      setUploads((prev) => prev.filter((row) => row.id !== upload.id));
    } catch (err) {
      setError(err.response?.data?.error || 'Could not delete that file.');
    }
  };

  if (activeUpload) {
    return <CustomMonitor upload={activeUpload} onFinished={() => setActiveUpload(null)} />;
  }

  return (
    <div className="space-y-6 max-w-3xl mx-auto animate-fade-in">
      <div>
        <h1 className="font-display text-2xl md:text-3xl font-bold text-text">Practice with your own file</h1>
        <p className="text-text-muted mt-2 prose-narrow">
          Upload a video, document, image, or audio file, then start monitoring yourself.
          Focus prompts are not something you pick. The session applies the best one for the moment:
          a gentle reminder, a pause check, or a short break.
        </p>
      </div>

      {error && <ErrorBanner message={error} onDismiss={() => setError(null)} />}

      <Card className="p-6">
        <label className="flex flex-col items-center gap-3 text-center cursor-pointer">
          <span className="w-12 h-12 rounded-2xl bg-primary-soft text-primary flex items-center justify-center">
            <FileUp className="w-6 h-6" aria-hidden="true" />
          </span>
          <span className="font-semibold text-text">
            {uploading ? 'Uploading…' : 'Choose a file'}
          </span>
          <span className="text-sm text-text-muted">
            PDF, slides, text, video, image, or audio
          </span>
          <input
            type="file"
            accept={ACCEPT}
            className="sr-only"
            disabled={uploading}
            onChange={onFile}
          />
        </label>
      </Card>

      {loading ? (
        <LoadingSpinner label="Loading your files…" />
      ) : uploads.length === 0 ? (
        <Card>
          <EmptyState
            icon={Upload}
            title="No files yet"
            description="Upload something you want to study. Monitoring starts when you press Start."
          />
        </Card>
      ) : (
        <ul className="space-y-3">
          {uploads.map((upload) => (
            <li key={upload.id}>
              <Card className="p-4 flex flex-wrap items-center justify-between gap-3">
                <div className="min-w-0">
                  <p className="font-semibold text-text truncate">{upload.title}</p>
                  <p className="text-xs text-text-muted">
                    {KIND_LABEL[upload.content_kind] || 'File'}
                    {upload.original_filename ? ` · ${upload.original_filename}` : ''}
                  </p>
                </div>
                <div className="flex items-center gap-2">
                  <Button size="sm" onClick={() => setActiveUpload(upload)}>
                    <Play className="w-4 h-4 fill-current" aria-hidden="true" />
                    Start monitoring
                  </Button>
                  <button
                    type="button"
                    onClick={() => removeUpload(upload)}
                    className="min-h-11 min-w-11 inline-flex items-center justify-center rounded-2xl text-text-muted hover:text-danger hover:bg-danger/10 cursor-pointer"
                    aria-label={`Delete ${upload.title}`}
                  >
                    <Trash2 className="w-4 h-4" />
                  </button>
                </div>
              </Card>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
