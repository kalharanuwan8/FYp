import { useCallback, useEffect, useRef, useState } from 'react';
import sessionService from '../services/sessionService';

/**
 * Shared monitored-session hook: camera on + JPEG heartbeats to /session/{id}/heartbeat.
 * Backend runs M1→M2→M4→M5 (or fallback) and returns the model verdict.
 */
export function useMonitoringSession({
  intervalMs = 2000,
  onIntervention = null,
  isQuizContext = false,
  lessonAudioActive = false,
} = {}) {
  const webcamRef = useRef(null);
  const canvasRef = useRef(null);
  const intervalRef = useRef(null);
  const streamRef = useRef(null);
  const sessionIdRef = useRef(null);
  const quizContextRef = useRef(isQuizContext);
  const lessonAudioActiveRef = useRef(lessonAudioActive);
  const audioContextRef = useRef(null);
  const analyserRef = useRef(null);
  const inFlightRef = useRef(false);
  const onInterventionRef = useRef(onIntervention);

  useEffect(() => {
    quizContextRef.current = isQuizContext;
  }, [isQuizContext]);

  useEffect(() => {
    lessonAudioActiveRef.current = lessonAudioActive;
  }, [lessonAudioActive]);

  useEffect(() => {
    onInterventionRef.current = onIntervention;
  }, [onIntervention]);

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
        width: 320,
        height: 240,
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
    const ctx = canvas.getContext('2d');
    canvas.width = 224;
    canvas.height = 224;
    // Draw un-mirrored for the model (CSS mirror is display-only)
    ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
    return canvas.toDataURL('image/jpeg', 0.5);
  }, []);

  const stopTelemetryLoop = useCallback(() => {
    if (intervalRef.current) {
      clearInterval(intervalRef.current);
      intervalRef.current = null;
    }
    inFlightRef.current = false;
  }, []);

  const startTelemetryLoop = useCallback(
    (sessionId) => {
      stopTelemetryLoop();
      sessionIdRef.current = sessionId;

      intervalRef.current = setInterval(async () => {
        if (!sessionIdRef.current || inFlightRef.current) return;
        // Ensure preview stays attached if the <video> remounted
        attachStreamToVideo(webcamRef.current);
        const frameBase64 = captureFrame();
        if (!frameBase64) return;

        inFlightRef.current = true;
        try {
          const lessonAudioActiveNow = Boolean(lessonAudioActiveRef.current);
          // Lesson speakers feed back into the mic — those samples are not room noise.
          const currentNoiseDbfs = lessonAudioActiveNow ? null : captureNoiseDbfs();
          if (currentNoiseDbfs !== null) setNoiseDbfs(currentNoiseDbfs);
          const response = await sessionService.sendHeartbeat(sessionIdRef.current, {
            image: frameBase64,
            is_quiz_context: Boolean(quizContextRef.current),
            noise_dbfs: currentNoiseDbfs,
            lesson_audio_active: lessonAudioActiveNow,
          });
          if (!sessionIdRef.current) return;
          if (response.verdict) setLastVerdict(response.verdict);
          if (response.ml_mode) setMlMode(response.ml_mode);
          if (response.verdict === 'UNKNOWN') {
            setConfidence(null);
          } else if (typeof response.confidence === 'number') {
            setConfidence(response.confidence);
          } else {
            setConfidence(null);
          }
          if (
            response.intervention_triggered &&
            response.intervention &&
            onInterventionRef.current
          ) {
            onInterventionRef.current(response.intervention);
          }
        } catch (err) {
          console.error('Background ML telemetry error:', err);
          const status = err.response?.status;
          const msg = err.response?.data?.error || err.message;
          if (status >= 500) {
            setError(`Monitoring server error (${status}): ${msg}`);
          }
        } finally {
          inFlightRef.current = false;
        }
      }, intervalMs);
    },
    [attachStreamToVideo, captureFrame, captureNoiseDbfs, intervalMs, stopTelemetryLoop]
  );

  const startMonitoredSession = useCallback(
    async (moduleId) => {
      setLoading(true);
      setError(null);
      setLastVerdict('FOCUSED');
      setMlMode(null);

      const camOk = await startCamera();
      if (!camOk) {
        const msg =
          'Camera is required to start a monitored session. Allow camera access and sit with light in front of you.';
        setError(msg);
        setLoading(false);
        return { ok: false, error: msg };
      }

      try {
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
    async (tier, isQuiz = false) => {
      const sid = activeSession?.session_id ?? sessionIdRef.current;
      if (!sid) {
        throw new Error('No active monitored session');
      }
      const response = await sessionService.triggerIntervention(sid, tier, isQuiz);
      if (response.intervention_triggered && response.intervention && onInterventionRef.current) {
        onInterventionRef.current(response.intervention);
      }
      return response;
    },
    [activeSession]
  );

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
    startCamera,
    stopCamera,
    startMonitoredSession,
    stopMonitoredSession,
    triggerManualIntervention,
    startTelemetryLoop,
    stopTelemetryLoop,
    setActiveSession,
    setLastVerdict,
  };
}

export default useMonitoringSession;
