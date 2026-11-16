import { useState, useEffect, useCallback, useRef } from 'react';
import { Outlet, useLocation } from 'react-router-dom';
import StudentSidebar from './StudentSidebar';
import StudentTopbar from './StudentTopbar';
import FirstTimeOnboardingModal from './FirstTimeOnboardingModal';
import ScreenCalibrationOverlay from './ScreenCalibrationOverlay';
import WebcamCapture from '../monitoring/WebcamCapture';
import studentService from '../../services/studentService';
import { useMonitoringSession } from '../../hooks/useMonitoringSession';

const GAZE_SKIP_KEY = 'luma_gaze_calib_skipped';

export default function StudentLayout() {
  const [profile, setProfile] = useState(null);
  const [progress, setProgress] = useState(null);
  const [showOnboarding, setShowOnboarding] = useState(false);
  const [showGazeCalib, setShowGazeCalib] = useState(false);
  const [calibKey, setCalibKey] = useState(0);
  const [focusMode, setFocusMode] = useState(false);
  const location = useLocation();
  const gazeStartedRef = useRef(false);

  const {
    webcamRef,
    canvasRef,
    cameraActive,
    faceDetected,
    setCalibrating,
    setCalibrationTarget,
    finishCalibration,
    startCalibrationOnly,
    stopCalibrationOnly,
  } = useMonitoringSession({ intervalMs: 1000 });

  const refreshProfile = useCallback(async () => {
    try {
      const data = await studentService.getProfile();
      setProfile(data);
      if (!data.onboarding_completed) {
        setShowOnboarding(true);
      }
      return data;
    } catch (err) {
      console.error('Failed to check student profile:', err);
      return null;
    }
  }, []);

  const refreshProgress = useCallback(async () => {
    try {
      const data = await studentService.getProgress();
      setProgress(data);
    } catch {
      /* progress optional on first load */
    }
  }, []);

  useEffect(() => {
    refreshProfile();
    refreshProgress();
  }, [refreshProfile, refreshProgress]);

  useEffect(() => {
    setFocusMode(false);
  }, [location.pathname]);

  const maybeStartGazeCalib = useCallback(
    async (prof) => {
      if (!prof?.onboarding_completed || prof.gaze_calibrated) return;
      if (typeof sessionStorage !== 'undefined' && sessionStorage.getItem(GAZE_SKIP_KEY)) {
        return;
      }
      if (gazeStartedRef.current) return;
      gazeStartedRef.current = true;
      const result = await startCalibrationOnly();
      if (!result?.ok) {
        gazeStartedRef.current = false;
        // Missing camera must not trap the account — treat as skip for this visit.
        try {
          sessionStorage.setItem(GAZE_SKIP_KEY, '1');
        } catch {
          /* ignore */
        }
        return;
      }
      setCalibKey((k) => k + 1);
      setShowGazeCalib(true);
      setCalibrating(true);
    },
    [setCalibrating, startCalibrationOnly]
  );

  useEffect(() => {
    if (!profile || showOnboarding) return;
    maybeStartGazeCalib(profile);
  }, [profile, showOnboarding, maybeStartGazeCalib]);

  const handleOnboardingComplete = (updatedProfile) => {
    setProfile(updatedProfile);
    setShowOnboarding(false);
    maybeStartGazeCalib(updatedProfile);
  };

  const closeGazeCalib = useCallback(() => {
    setShowGazeCalib(false);
    setCalibrating(false);
    stopCalibrationOnly();
    gazeStartedRef.current = false;
  }, [setCalibrating, stopCalibrationOnly]);

  const handleGazeDone = useCallback(
    async (result) => {
      closeGazeCalib();
      if (result?.ok) {
        await refreshProfile();
      } else if (result?.skipped) {
        try {
          sessionStorage.setItem(GAZE_SKIP_KEY, '1');
        } catch {
          /* ignore */
        }
      }
    },
    [closeGazeCalib, refreshProfile]
  );

  const handleGazeRetry = useCallback(() => {
    setCalibKey((k) => k + 1);
    setCalibrating(true);
  }, [setCalibrating]);

  return (
    <div className="flex min-h-screen bg-bg font-sans relative">
      <a
        href="#main-content"
        className="sr-only focus:not-sr-only focus:absolute focus:top-3 focus:left-3 focus:z-[80] focus:bg-primary focus:text-on-primary focus:px-4 focus:py-2 focus:rounded-2xl focus:font-semibold"
      >
        Skip to main content
      </a>
      <StudentSidebar focusMode={focusMode} />
      <div className="flex-1 flex flex-col min-w-0">
        {!focusMode && <StudentTopbar profile={profile} progress={progress} />}
        <main
          id="main-content"
          tabIndex={-1}
          className={`flex-1 overflow-y-auto outline-none ${focusMode ? 'p-0' : 'p-4 pb-24 md:p-8'}`}
        >
          <Outlet
            context={{
              profile,
              progress,
              refreshProfile,
              refreshProgress,
              focusMode,
              setFocusMode,
            }}
          />
        </main>
      </div>

      {/* Hidden capture surface for account-level screen calibration */}
      <div
        className="fixed w-40 h-28 opacity-0 pointer-events-none -z-10 left-0 top-0 overflow-hidden"
        aria-hidden
      >
        <WebcamCapture
          videoRef={webcamRef}
          canvasRef={canvasRef}
          cameraActive={cameraActive}
          compact
        />
      </div>

      <FirstTimeOnboardingModal
        isOpen={showOnboarding}
        initialProfile={profile}
        onComplete={handleOnboardingComplete}
      />

      <ScreenCalibrationOverlay
        key={calibKey}
        open={showGazeCalib}
        faceFound={faceDetected !== false}
        setCalibrationTarget={setCalibrationTarget}
        finishCalibration={finishCalibration}
        onDone={handleGazeDone}
        onRetry={handleGazeRetry}
      />
    </div>
  );
}
