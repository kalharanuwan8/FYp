import { useCallback, useEffect, useRef, useState } from 'react';
import sessionService from '../services/sessionService';
import studentService from '../services/studentService';

/**
 * Shared monitored-session hook: camera on + JPEG heartbeats to /session/{id}/heartbeat.
 * Frames are captured at ~3 fps (one every ~333 ms) and sent in batches with each
 * heartbeat; the backend computes the MediaPipe window features and screen-gaze
 * verdict. PLAN 5 adds the screen calibration (`calib_target` per frame,
 * `calibration_phase` start | collect | finish) and exposes `gazeDebug`.
 * Calibration-only mode posts to /student/gaze-calibration (no learning session).
 */
const CALIB_ONLY_SID = 'calib-only';
const CAPTURE_INTERVAL_MS = 333; // PLAN 5: a frame every ~333 ms
const MAX_BUFFERED_FRAMES = 9; // backend limit per heartbeat
const FRAME_TARGET_WIDTH = 640; // aspect preserved from video
const JPEG_QUALITY = 0.7;
const FINISH_WAIT_MS = 3000; // max wait for an in-flight heartbeat before the finish call

function screenSnapshot() {
  return {
    w: Math.max(1, Math.round(window.screen?.width || window.innerWidth || 1)),
    h: Math.max(1, Math.round(window.screen?.height || window.innerHeight || 1)),
    inner_w: Math.round(window.innerWidth || 0),
    inner_h: Math.round(window.innerHeight || 0),
    dpr: window.devicePixelRatio || 1,
  };
}

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

// PLAN 7 evaluation log: bounded ring buffer; thumbnails only on the newest lines.
const EVAL_LOG_MAX = 500;
const EVAL_THUMB_KEEP = 40;

export function useMonitoringSession({
  intervalMs = 2000,
  onIntervention = null,
  // PLAN 8: optional subscriber, called with the full heartbeat response and
  // `{ loopStartMs }` (performance.now() origin of `frames_debug[].t`).
  onHeartbeat = null,
  isQuizContext = false,
  lessonAudioActive = false,
  evalCapture = false,
} = {}) {
  const webcamRef = useRef(null);
  const canvasRef = useRef(null);
  const intervalRef = useRef(null);
  const captureIntervalRef = useRef(null);
  const frameBufferRef = useRef([]);
  const loopStartRef = useRef(0);
  const streamRef = useRef(null);
  const sessionIdRef = useRef(null);
  const quizContextRef = useRef(isQuizContext);
  const lessonAudioActiveRef = useRef(lessonAudioActive);
  const audioContextRef = useRef(null);
  const analyserRef = useRef(null);
  const inFlightRef = useRef(false);
  const onInterventionRef = useRef(onIntervention);
  const onHeartbeatRef = useRef(onHeartbeat);
  const pageVisibleRef = useRef(true);
  const windowFocusedRef = useRef(true);
  const hiddenSinceRef = useRef(null);
  const blurredSinceRef = useRef(null);
  const contentStateRef = useRef('none');
  const pauseReasonRef = useRef(null); // 'user' | 'intervention' | 'ended' (PLAN 7)
  const startPromiseRef = useRef(null); // {moduleId, promise}: de-dup StrictMode double start
  const evalCaptureRef = useRef(evalCapture);
  const [evalLog, setEvalLog] = useState([]);
  const calibratingRef = useRef(false);
  const calibOnlyRef = useRef(false); // posts to /student/gaze-calibration instead of session heartbeat
  const calibTargetRef = useRef(null); // {x, y} normalised, while a dot is being looked at
  const pendingPhaseRef = useRef(null); // one-shot calibration_phase ('start') for next heartbeat
  const [calibrating, setCalibrating] = useState(false);
  const [gazeDebug, setGazeDebug] = useState(null);
  const [calibrationStatus, setCalibrationStatus] = useState(null);
  const [pageVisible, setPageVisible] = useState(true);
  const [faceDetected, setFaceDetected] = useState(null);

  useEffect(() => {
    quizContextRef.current = isQuizContext;
  }, [isQuizContext]);

  useEffect(() => {
    lessonAudioActiveRef.current = lessonAudioActive;
  }, [lessonAudioActive]);

  useEffect(() => {
    onInterventionRef.current = onIntervention;
  }, [onIntervention]);

  useEffect(() => {
    onHeartbeatRef.current = onHeartbeat;
  }, [onHeartbeat]);

  useEffect(() => {
    evalCaptureRef.current = evalCapture;
  }, [evalCapture]);

  /** Append one entry to the evaluation log (bounded; old thumbnails dropped). */
  const pushEvalEntry = useCallback((entry) => {
    setEvalLog((prev) => {
      const next = prev.length >= EVAL_LOG_MAX ? prev.slice(prev.length - EVAL_LOG_MAX + 1) : prev.slice();
      next.push({ id: `${entry.ts}-${Math.random().toString(36).slice(2, 7)}`, ...entry });
      const cut = next.length - EVAL_THUMB_KEEP;
      if (cut > 0 && next[cut - 1]?.thumb) {
        for (let i = 0; i < cut; i += 1) {
          if (next[i].thumb) next[i] = { ...next[i], thumb: undefined };
        }
      }
      return next;
    });
  }, []);

  const addEvalMark = useCallback(
    (text = 'evaluator: distracted now') => pushEvalEntry({ kind: 'mark', ts: Date.now(), text }),
    [pushEvalEntry]
  );
  const clearEvalLog = useCallback(() => setEvalLog([]), []);

  const [cameraActive, setCameraActive] = useState(false);
  const [cameraError, setCameraError] = useState(null);
  const [activeSession, setActiveSession] = useState(null);
  const [lastVerdict, setLastVerdict] = useState('FOCUSED');
  const [mlMode, setMlMode] = useState(null);
  const [confidence, setConfidence] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [micActive, setMicActive] = useState(false);
  const [noiseDbfs, setNoiseDbfs] = useState(null);

  const attachStreamToVideo = useCallback((videoEl) => {
    if (!videoEl || !streamRef.current) return;
    if (videoEl.srcObject !== streamRef.current) {
      videoEl.srcObject = streamRef.current;
    }
    videoEl.play().catch(() => {});
  }, []);

  /** Callback ref so the stream attaches as soon as <video> mounts. */
  const setWebcamNode = useCallback(
    (node) => {
      webcamRef.current = node;
      attachStreamToVideo(node);
    },
    [attachStreamToVideo]
  );

  const setCanvasNode = useCallback((node) => {
    canvasRef.current = node;
  }, []);

  const stopNoiseMeter = useCallback(() => {
    analyserRef.current = null;
    const ctx = audioContextRef.current;
    audioContextRef.current = null;
    if (ctx && ctx.state !== 'closed') {
      ctx.close().catch(() => {});
    }
    setMicActive(false);
    setNoiseDbfs(null);
  }, []);

  const startNoiseMeter = useCallback((stream) => {
    if (!stream?.getAudioTracks?.().length || analyserRef.current) {
      if (stream?.getAudioTracks?.().length) setMicActive(true);
      return;
    }
    try {
      const AudioCtx = window.AudioContext || window.webkitAudioContext;
      if (!AudioCtx) return;
      const ctx = new AudioCtx();
      const source = ctx.createMediaStreamSource(stream);
      const analyser = ctx.createAnalyser();
      analyser.fftSize = 2048;
      source.connect(analyser);
      audioContextRef.current = ctx;
      analyserRef.current = analyser;
      setMicActive(true);
      if (ctx.state === 'suspended') ctx.resume().catch(() => {});
    } catch (err) {
      // Mic metering is optional — camera monitoring must continue without it.
      console.warn('Microphone level metering unavailable:', err);
      setMicActive(false);
    }
  }, []);

  /** RMS loudness in dBFS (-100..0), computed on-device; no audio is uploaded. */
  const captureNoiseDbfs = useCallback(() => {
    const analyser = analyserRef.current;
    if (!analyser) return null;
    try {
      const buffer = new Float32Array(analyser.fftSize);
      analyser.getFloatTimeDomainData(buffer);
      let sumSquares = 0;
      for (let i = 0; i < buffer.length; i += 1) sumSquares += buffer[i] * buffer[i];
      const rms = Math.sqrt(sumSquares / buffer.length);
      if (!rms) return -100;
      return Math.max(-100, Math.min(0, 20 * Math.log10(rms)));
    } catch {
      return null;
    }
  }, []);

  const stopCamera = useCallback(() => {
    stopNoiseMeter();
    if (streamRef.current) {
      streamRef.current.getTracks().forEach((t) => t.stop());
      streamRef.current = null;
    }
    if (webcamRef.current) {
      webcamRef.current.srcObject = null;
    }
    setCameraActive(false);
  }, [stopNoiseMeter]);

  const startCamera = useCallback(async () => {
    setCameraError(null);
    try {
      if (!navigator.mediaDevices?.getUserMedia) {
        throw new Error('Camera API not available in this browser');
      }
      // Reuse an existing live stream (avoids StrictMode double-permission flicker)
      if (streamRef.current?.active) {
        attachStreamToVideo(webcamRef.current);
        startNoiseMeter(streamRef.current);
        setCameraActive(true);
        return true;
      }
      const videoConstraints = {
        width: 640,
        height: 480,
        frameRate: 15,
        facingMode: 'user',
      };
      let stream;
      try {
        // Raw mic (no suppression / gain) so loudness reflects the room.
        // Only the computed level is sent — never the audio itself.
        stream = await navigator.mediaDevices.getUserMedia({
          video: videoConstraints,
          audio: {
            echoCancellation: false,
            noiseSuppression: false,
            autoGainControl: false,
          },
        });
      } catch (micErr) {
        // Mic denied/unavailable must not block a camera-monitored session.
        console.warn('Microphone unavailable, continuing with camera only:', micErr);
        stream = await navigator.mediaDevices.getUserMedia({
          video: videoConstraints,
          audio: false,
        });
      }
      streamRef.current = stream;
      attachStreamToVideo(webcamRef.current);
      startNoiseMeter(stream);
      setCameraActive(true);
      return true;
    } catch (err) {
      console.warn('Webcam unavailable:', err);
      setCameraError(
        'Camera access is required for distraction monitoring. Allow the camera and face it with light in front of you.'
      );
      setCameraActive(false);
      return false;
    }
  }, [attachStreamToVideo, startNoiseMeter]);

  const captureFrame = useCallback(() => {
    const video = webcamRef.current;
    const canvas = canvasRef.current;
    if (!video || !canvas) return null;
    if (video.readyState < 2) return null;
    const vw = video.videoWidth || FRAME_TARGET_WIDTH;
    const vh = video.videoHeight || Math.round((FRAME_TARGET_WIDTH * 3) / 4);
    const width = FRAME_TARGET_WIDTH;
    const height = Math.max(1, Math.round((width * vh) / vw));
    const ctx = canvas.getContext('2d');
    canvas.width = width;
    canvas.height = height;
    // Draw un-mirrored for the model (CSS mirror is display-only)
    ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
    return canvas.toDataURL('image/jpeg', JPEG_QUALITY);
  }, []);

  const browserSignalSnapshot = useCallback(() => {
    const now = performance.now();
    const hiddenMs =
      !pageVisibleRef.current && hiddenSinceRef.current != null
        ? Math.round(now - hiddenSinceRef.current)
        : 0;
    const blurredMs =
      !windowFocusedRef.current && blurredSinceRef.current != null
        ? Math.round(now - blurredSinceRef.current)
        : 0;
    return {
      page_visible: pageVisibleRef.current,
      window_focused: windowFocusedRef.current,
      hidden_ms: hiddenMs,
      blurred_ms: blurredMs,
      content_state: contentStateRef.current,
      pause_reason: pauseReasonRef.current,
      calibrating: Boolean(calibratingRef.current),
    };
  }, []);

  useEffect(() => {
    const onVis = () => {
      const visible = document.visibilityState === 'visible';
      pageVisibleRef.current = visible;
      setPageVisible(visible);
      if (!visible) {
        if (hiddenSinceRef.current == null) hiddenSinceRef.current = performance.now();
      } else {
        hiddenSinceRef.current = null;
      }
    };
    const onBlur = () => {
      windowFocusedRef.current = false;
      if (blurredSinceRef.current == null) blurredSinceRef.current = performance.now();
    };
    const onFocus = () => {
      windowFocusedRef.current = true;
      blurredSinceRef.current = null;
    };
    document.addEventListener('visibilitychange', onVis);
    window.addEventListener('blur', onBlur);
    window.addEventListener('focus', onFocus);
    onVis();
    return () => {
      document.removeEventListener('visibilitychange', onVis);
      window.removeEventListener('blur', onBlur);
      window.removeEventListener('focus', onFocus);
    };
  }, []);

  const stopTelemetryLoop = useCallback(() => {
    if (intervalRef.current) {
      clearInterval(intervalRef.current);
      intervalRef.current = null;
    }
    if (captureIntervalRef.current) {
      clearInterval(captureIntervalRef.current);
      captureIntervalRef.current = null;
    }
    frameBufferRef.current = [];
    inFlightRef.current = false;
  }, []);

  /** 'start' once (queued by setCalibrating(true)), then 'collect' while calibrating. */
  const nextCalibrationPhase = useCallback(() => {
    if (pendingPhaseRef.current) {
      const phase = pendingPhaseRef.current;
      pendingPhaseRef.current = null;
      return phase;
    }
    return calibratingRef.current ? 'collect' : null;
  }, []);

  /**
   * Send one heartbeat. Owns the in-flight flag, applies the response to hook state
   * and forwards any new intervention to the consumer (which replaces the open one).
   * Returns the response, or null on failure / no active session.
   */
  const sendHeartbeat = useCallback(
    async (frames, signals, phase) => {
      const sid = sessionIdRef.current;
      if (!sid) return null;
      inFlightRef.current = true;
      try {
        const calibOnly = calibOnlyRef.current;
        const lessonAudioActiveNow = Boolean(lessonAudioActiveRef.current);
        // Lesson speakers feed back into the mic — those samples are not room noise.
        const currentNoiseDbfs =
          calibOnly || lessonAudioActiveNow ? null : captureNoiseDbfs();
        if (currentNoiseDbfs !== null) setNoiseDbfs(currentNoiseDbfs);
        const payload = calibOnly
          ? {
              frames,
              screen: screenSnapshot(),
              calibrating: true,
            }
          : {
              frames,
              is_quiz_context: Boolean(quizContextRef.current),
              noise_dbfs: currentNoiseDbfs,
              lesson_audio_active: lessonAudioActiveNow,
              screen: screenSnapshot(),
              ...signals,
            };
        if (phase) payload.calibration_phase = phase;
        const response = calibOnly
          ? await studentService.postGazeCalibration(payload)
          : await sessionService.sendHeartbeat(sid, payload);
        if (!sessionIdRef.current) return null;
        if (response.verdict) setLastVerdict(response.verdict);
        if (response.ml_mode) setMlMode(response.ml_mode);
        if (typeof response.face_detected === 'boolean') {
          setFaceDetected(response.face_detected);
        } else if (response.reason === 'calibrating' || calibOnly) {
          // keep last faceDetected during calibration heartbeats without a clear flag
        } else {
          setFaceDetected(null);
        }
        if (response.verdict === 'UNKNOWN') {
          setConfidence(null);
        } else if (typeof response.confidence === 'number') {
          setConfidence(response.confidence);
        } else {
          setConfidence(null);
        }
        setGazeDebug(response.gaze_debug || null);
        if (response.calibration) setCalibrationStatus(response.calibration);
        if (onHeartbeatRef.current) {
          try {
            onHeartbeatRef.current(response, { loopStartMs: loopStartRef.current });
          } catch (cbErr) {
            console.warn('onHeartbeat subscriber failed:', cbErr);
          }
        }
        if (
          !calibOnly &&
          response.intervention_triggered &&
          response.intervention &&
          onInterventionRef.current
        ) {
          onInterventionRef.current(response.intervention);
        }
        if (!calibOnly) {
          const resForLog = { ...response };
          delete resForLog.calibration;
          pushEvalEntry({
            kind: 'beat',
            ts: Date.now(),
            sent: {
              n_frames: frames.length,
              content_state: payload.content_state,
              pause_reason: payload.pause_reason,
              hidden_ms: payload.hidden_ms,
              blurred_ms: payload.blurred_ms,
              noise_dbfs: payload.noise_dbfs,
              phase: phase || null,
            },
            res: resForLog,
            // Local-only evidence for the evaluator; never uploaded again or stored.
            thumb:
              evalCaptureRef.current && response.verdict === 'DISTRACTED' && frames.length
                ? frames[frames.length - 1].image
                : undefined,
          });
        }
        return response;
      } catch (err) {
        console.error('Background ML telemetry error:', err);
        if (phase === 'start') pendingPhaseRef.current = 'start'; // retry next beat
        const status = err.response?.status;
        const msg = err.response?.data?.error || err.message;
        pushEvalEntry({
          kind: 'error',
          ts: Date.now(),
          text: `heartbeat failed${status ? ` (${status})` : ''}: ${msg}`,
        });
        if (status >= 500) {
          setError(`Monitoring server error (${status}): ${msg}`);
        }
        return null;
      } finally {
        inFlightRef.current = false;
      }
    },
    [captureNoiseDbfs, pushEvalEntry]
  );

  const startTelemetryLoop = useCallback(
    (sessionId) => {
      stopTelemetryLoop();
      sessionIdRef.current = sessionId;
      loopStartRef.current = performance.now();

      // Capture keeps running while a heartbeat is in flight, so no frames are
      // lost; the next heartbeat carries them (bounded to the newest few).
      captureIntervalRef.current = setInterval(() => {
        if (!sessionIdRef.current) return;
        const image = captureFrame();
        if (!image) return;
        const buf = frameBufferRef.current;
        const frame = { t_ms: Math.round(performance.now() - loopStartRef.current), image };
        const target = calibTargetRef.current;
        if (target) frame.calib_target = { x: target.x, y: target.y };
        buf.push(frame);
        if (buf.length > MAX_BUFFERED_FRAMES) buf.splice(0, buf.length - MAX_BUFFERED_FRAMES);
      }, CAPTURE_INTERVAL_MS);

      intervalRef.current = setInterval(async () => {
        if (!sessionIdRef.current || inFlightRef.current) return;
        // Ensure preview stays attached if the <video> remounted
        attachStreamToVideo(webcamRef.current);
        const frames = frameBufferRef.current;
        const signals = browserSignalSnapshot();
        const phase = nextCalibrationPhase();
        // While hidden, still send a lightweight heartbeat (server uses hidden_ms).
        // A pending calibration phase is always sent, even without frames.
        if (frames.length === 0 && signals.page_visible && !phase) return;
        frameBufferRef.current = [];
        await sendHeartbeat(frames, signals, phase);
      }, intervalMs);
    },
    [
      attachStreamToVideo,
      browserSignalSnapshot,
      captureFrame,
      intervalMs,
      nextCalibrationPhase,
      sendHeartbeat,
      stopTelemetryLoop,
    ]
  );

  const doStartMonitoredSession = useCallback(
    async (moduleId) => {
      setLoading(true);
      setError(null);
      setLastVerdict('FOCUSED');
      setMlMode(null);
      setGazeDebug(null);
      setCalibrationStatus(null);

      const camOk = await startCamera();
      if (!camOk) {
        const msg =
          'Camera is required to start a monitored session. Allow camera access and sit with light in front of you.';
        setError(msg);
        setLoading(false);
        return { ok: false, error: msg };
      }

      try {
        calibOnlyRef.current = false;
        const sessionData = await sessionService.startSession(moduleId, true);
        setActiveSession(sessionData);
        startTelemetryLoop(sessionData.session_id);
        // Re-attach after React paints the session UI / PiP
        requestAnimationFrame(() => attachStreamToVideo(webcamRef.current));
        return { ok: true, session: sessionData };
      } catch (err) {
        const msg =
          err.response?.data?.error ||
          err.response?.data?.details ||
          'Failed to start monitored learning session.';
        setError(msg);
        stopCamera();
        return { ok: false, error: msg };
      } finally {
        setLoading(false);
      }
    },
    [attachStreamToVideo, startCamera, startTelemetryLoop, stopCamera]
  );

  /**
   * StrictMode runs the player's boot effect twice; without this both runs
   * POST /session/start and one session is orphaned (PLAN 7, bug 3). A second
   * call for the same module while the first is in flight shares its result.
   */
  const startMonitoredSession = useCallback(
    async (moduleId) => {
      const inflight = startPromiseRef.current;
      if (inflight && inflight.moduleId === moduleId) return inflight.promise;
      const promise = doStartMonitoredSession(moduleId);
      startPromiseRef.current = { moduleId, promise };
      try {
        return await promise;
      } finally {
        if (startPromiseRef.current?.promise === promise) startPromiseRef.current = null;
      }
    },
    [doStartMonitoredSession]
  );

  const stopMonitoredSession = useCallback(async () => {
    stopTelemetryLoop();
    const sid = activeSession?.session_id ?? sessionIdRef.current;
    sessionIdRef.current = null;
    stopCamera();

    if (!sid) {
      setActiveSession(null);
      return null;
    }

    try {
      const summary = await sessionService.stopSession(sid);
      setActiveSession(null);
      return summary;
    } catch (err) {
      console.error('Failed to stop session:', err);
      setActiveSession(null);
      throw err;
    }
  }, [activeSession, stopCamera, stopTelemetryLoop]);

  // Cleanup on unmount — defer slightly so React StrictMode remount can start a fresh camera
  useEffect(() => {
    return () => {
      stopTelemetryLoop();
      stopNoiseMeter();
      const sid = sessionIdRef.current;
      sessionIdRef.current = null;
      const stream = streamRef.current;
      streamRef.current = null;
      if (webcamRef.current) {
        webcamRef.current.srcObject = null;
      }
      // Stop tracks after a tick; a remounting instance will open a new stream
      setTimeout(() => {
        if (stream) {
          stream.getTracks().forEach((t) => t.stop());
        }
        if (sid) {
          sessionService.stopSession(sid).catch(() => {});
        }
      }, 50);
      setCameraActive(false);
    };
  }, [stopTelemetryLoop, stopNoiseMeter]);

  const triggerManualIntervention = useCallback(
    async (tier, isQuiz = false, options = {}) => {
      const sid = activeSession?.session_id ?? sessionIdRef.current;
      if (!sid) {
        throw new Error('No active monitored session');
      }
      const response = await sessionService.triggerIntervention(sid, tier, isQuiz, options);
      if (response.intervention_triggered && response.intervention && onInterventionRef.current) {
        onInterventionRef.current(response.intervention);
      }
      return response;
    },
    [activeSession]
  );

  /**
   * Lesson media state. `reason` matters only for 'paused': 'user' (student
   * paused — server gives a grace period, then a gentle nudge) or
   * 'intervention' (a prompt paused it — held while the prompt is open).
   */
  const setContentState = useCallback((state, reason) => {
    const s = state || 'none';
    contentStateRef.current = s;
    if (s === 'paused') pauseReasonRef.current = reason === 'intervention' ? 'intervention' : 'user';
    else if (s === 'ended') pauseReasonRef.current = 'ended';
    else pauseReasonRef.current = null;
  }, []);

  /** Turning calibration on queues a one-shot `calibration_phase: "start"`. */
  const setCalibratingFlag = useCallback((on) => {
    const next = Boolean(on);
    if (next && !calibratingRef.current) {
      pendingPhaseRef.current = 'start';
      setCalibrationStatus(null);
    }
    if (!next) {
      calibTargetRef.current = null;
      pendingPhaseRef.current = null;
    }
    calibratingRef.current = next;
    setCalibrating(next);
  }, []);

  /** Tag subsequent frames with a normalised {x, y} calibration dot (or null to stop). */
  const setCalibrationTarget = useCallback((target) => {
    calibTargetRef.current =
      target && Number.isFinite(target.x) && Number.isFinite(target.y)
        ? { x: target.x, y: target.y }
        : null;
  }, []);

  /**
   * End calibration: flush buffered frames with `calibration_phase: "finish"` and
   * resolve with the backend `calibration` result ({ ok, ... }) or null if unreachable.
   */
  const finishCalibration = useCallback(async () => {
    calibTargetRef.current = null;
    pendingPhaseRef.current = null;
    const wasCalibrating = calibratingRef.current;
    calibratingRef.current = false;
    setCalibrating(false);
    if (!wasCalibrating || !sessionIdRef.current) return null;
    const waitStart = Date.now();
    while (inFlightRef.current && Date.now() - waitStart < FINISH_WAIT_MS) {
      await sleep(50);
    }
    const frames = frameBufferRef.current;
    frameBufferRef.current = [];
    const response = await sendHeartbeat(frames, browserSignalSnapshot(), 'finish');
    return response?.calibration ?? null;
  }, [browserSignalSnapshot, sendHeartbeat]);

  /**
   * Camera + telemetry for account-level screen calibration (no learning session).
   * Posts frames to /student/gaze-calibration.
   */
  const startCalibrationOnly = useCallback(async () => {
    setError(null);
    setCalibrationStatus(null);
    const camOk = await startCamera();
    if (!camOk) {
      const msg =
        'Camera is required to map your screen. Allow camera access and sit with light in front of you.';
      setError(msg);
      return { ok: false, error: msg };
    }
    calibOnlyRef.current = true;
    sessionIdRef.current = CALIB_ONLY_SID;
    startTelemetryLoop(CALIB_ONLY_SID);
    requestAnimationFrame(() => attachStreamToVideo(webcamRef.current));
    return { ok: true };
  }, [attachStreamToVideo, startCamera, startTelemetryLoop]);

  const stopCalibrationOnly = useCallback(() => {
    stopTelemetryLoop();
    sessionIdRef.current = null;
    calibOnlyRef.current = false;
    calibratingRef.current = false;
    calibTargetRef.current = null;
    pendingPhaseRef.current = null;
    setCalibrating(false);
    stopCamera();
  }, [stopCamera, stopTelemetryLoop]);

  return {
    // Prefer these callback refs so stream attaches on mount
    webcamRef: setWebcamNode,
    canvasRef: setCanvasNode,
    webcamElementRef: webcamRef,
    cameraActive,
    cameraError,
    micActive,
    noiseDbfs,
    activeSession,
    lastVerdict,
    mlMode,
    confidence,
    loading,
    error,
    setError,
    calibrating,
    faceDetected,
    pageVisible,
    setContentState,
    setCalibrating: setCalibratingFlag,
    setCalibrationTarget,
    finishCalibration,
    calibrationStatus,
    gazeDebug,
    startCamera,
    stopCamera,
    startCalibrationOnly,
    stopCalibrationOnly,
    startMonitoredSession,
    stopMonitoredSession,
    triggerManualIntervention,
    startTelemetryLoop,
    stopTelemetryLoop,
    setActiveSession,
    setLastVerdict,
    evalLog,
    addEvalMark,
    clearEvalLog,
  };
}

export default useMonitoringSession;
