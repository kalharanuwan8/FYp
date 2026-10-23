import { useState, useEffect, useCallback } from 'react';
import { Outlet, useLocation } from 'react-router-dom';
import StudentSidebar from './StudentSidebar';
import StudentTopbar from './StudentTopbar';
import FirstTimeOnboardingModal from './FirstTimeOnboardingModal';
import studentService from '../../services/studentService';

export default function StudentLayout() {
  const [profile, setProfile] = useState(null);
  const [progress, setProgress] = useState(null);
  const [showOnboarding, setShowOnboarding] = useState(false);
  const [focusMode, setFocusMode] = useState(false);
  const location = useLocation();

  const refreshProfile = useCallback(async () => {
    try {
      const data = await studentService.getProfile();
      setProfile(data);
      if (!data.onboarding_completed) {
        setShowOnboarding(true);
      }
    } catch (err) {
      console.error('Failed to check student profile:', err);
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

  const handleOnboardingComplete = (updatedProfile) => {
    setProfile(updatedProfile);
    setShowOnboarding(false);
  };

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

      <FirstTimeOnboardingModal
        isOpen={showOnboarding}
        initialProfile={profile}
        onComplete={handleOnboardingComplete}
      />
    </div>
  );
}
