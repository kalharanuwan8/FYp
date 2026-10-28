import { createContext, useContext, useEffect, useRef, useState } from 'react';
import { useAuth } from '../hooks/useAuth';
import studentService from '../services/studentService';

const STORAGE_KEY = 'luma_ui_preferences';

/** Plain themes available in Settings. 'light' is migrated to 'sage'. */
export const THEME_OPTIONS = [
  { value: 'sage', label: 'Sage', hint: 'Soft green page (default)' },
  { value: 'warm', label: 'Warm neutral', hint: 'Parchment page' },
  { value: 'pale-blue', label: 'Pale blue', hint: 'Cool mist page' },
  { value: 'calm-dark', label: 'Calm dark', hint: 'Low-light surfaces' },
];

export const VALID_THEMES = new Set(THEME_OPTIONS.map((t) => t.value));

const DEFAULTS = {
  theme: 'sage',
  textSize: 'm',
  reduceMotion: false,
  sounds: true,
  showCameraPreview: false,
  breakIntervalMinutes: 18,
};

const PreferencesContext = createContext(null);

/** Normalize legacy theme ids and unknown values. */
export function normalizeTheme(theme) {
  if (theme === 'light') return 'sage';
  if (VALID_THEMES.has(theme)) return theme;
  return DEFAULTS.theme;
}

function readLocal() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return { ...DEFAULTS };
    const parsed = { ...DEFAULTS, ...JSON.parse(raw) };
    parsed.theme = normalizeTheme(parsed.theme);
    return parsed;
  } catch {
    return { ...DEFAULTS };
  }
}

function applyDomPrefs(prefs) {
  const root = document.documentElement;
  const theme = normalizeTheme(prefs.theme);
  root.setAttribute('data-theme', theme);
  root.classList.remove('text-size-s', 'text-size-m', 'text-size-l');
  root.classList.add(`text-size-${prefs.textSize || 'm'}`);
  root.classList.toggle('reduce-motion', Boolean(prefs.reduceMotion));
}

export function PreferencesProvider({ children }) {
  const { user, token } = useAuth();
  const [prefs, setPrefs] = useState(readLocal);
  const prefsRef = useRef(prefs);
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    prefsRef.current = prefs;
  }, [prefs]);

  useEffect(() => {
    applyDomPrefs(prefs);
    localStorage.setItem(STORAGE_KEY, JSON.stringify(prefs));
  }, [prefs]);

  useEffect(() => {
    let cancelled = false;
    async function hydrate() {
      if (!token || !user || (user.role || '').toLowerCase() !== 'student') {
        setLoaded(true);
        return;
      }
      try {
        const profile = await studentService.getProfile();
        if (cancelled) return;
        if (profile?.ui_preferences && typeof profile.ui_preferences === 'object') {
          setPrefs((prev) => {
            const merged = { ...prev, ...profile.ui_preferences };
            merged.theme = normalizeTheme(merged.theme);
            return merged;
          });
        }
      } catch {
        /* local prefs still apply */
      } finally {
        if (!cancelled) setLoaded(true);
      }
    }
    hydrate();
    return () => {
      cancelled = true;
    };
  }, [token, user]);

  const updatePreferences = async (partial, { persist = true } = {}) => {
    const next = { ...prefsRef.current, ...partial };
    if (partial.theme !== undefined) {
      next.theme = normalizeTheme(partial.theme);
    }
    prefsRef.current = next;
    setPrefs(next);
    if (
      persist &&
      token &&
      user &&
      (user.role || '').toLowerCase() === 'student'
    ) {
      try {
        await studentService.updateProfile({ ui_preferences: next });
      } catch {
        /* local already saved */
      }
    }
    return next;
  };

  return (
    <PreferencesContext.Provider
      value={{
        ...prefs,
        loaded,
        updatePreferences,
        setTheme: (theme) => updatePreferences({ theme }),
        setTextSize: (textSize) => updatePreferences({ textSize }),
        setReduceMotion: (reduceMotion) => updatePreferences({ reduceMotion }),
        setSounds: (sounds) => updatePreferences({ sounds }),
      }}
    >
      {loaded ? (
        children
      ) : (
        <div className="min-h-screen bg-bg" aria-busy="true" aria-label="Loading your preferences" />
      )}
    </PreferencesContext.Provider>
  );
}

export function usePreferences() {
  const ctx = useContext(PreferencesContext);
  if (!ctx) {
    throw new Error('usePreferences must be used within PreferencesProvider');
  }
  return ctx;
}

export default PreferencesContext;
