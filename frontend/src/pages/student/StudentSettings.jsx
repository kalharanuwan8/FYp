import { useState, useEffect } from 'react';
import studentService from '../../services/studentService';
import courseService from '../../services/courseService';
import { usePreferences, THEME_OPTIONS } from '../../context/PreferencesContext';
import {
  Button,
  Card,
  LoadingSpinner,
  ErrorBanner,
  Field,
  Input,
  Select,
  SegmentedControl,
} from '../../components/common';

function ToggleRow({ label, hint, checked, onChange }) {
  return (
    <label className="flex items-center justify-between gap-3 min-h-11 cursor-pointer">
      <span>
        <span className="block text-sm font-medium text-text">{label}</span>
        {hint && <span className="block text-xs text-text-muted">{hint}</span>}
      </span>
      <input
        type="checkbox"
        checked={checked}
        onChange={(e) => onChange(e.target.checked)}
        className="w-5 h-5 shrink-0"
      />
    </label>
  );
}

export default function StudentSettings() {
  const {
    theme,
    textSize,
    reduceMotion,
    sounds,
    showCameraPreview,
    breakIntervalMinutes,
    updatePreferences,
  } = usePreferences();

  const [profile, setProfile] = useState(null);
  const [gradeLevels, setGradeLevels] = useState([]);
  const [gradeLevel, setGradeLevel] = useState('');
  const [dailyGoal, setDailyGoal] = useState(20);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [savedAt, setSavedAt] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    (async () => {
      try {
        const [prof, grades, prog] = await Promise.all([
          studentService.getProfile(),
          courseService.getGradeLevels(),
          studentService.getProgress().catch(() => null),
        ]);
        setProfile(prof);
        setGradeLevels(grades || []);
        setGradeLevel(prof.grade_level || '');
        if (prog?.daily_goal_minutes) setDailyGoal(prog.daily_goal_minutes);
      } catch {
        setError('Failed to load settings.');
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  const markSaved = () => setSavedAt(Date.now());

  const savePrefs = async (partial) => {
    await updatePreferences(partial);
    markSaved();
  };

  const saveProfile = async (e) => {
    e.preventDefault();
    setError(null);
    try {
      setSaving(true);
      const updated = await studentService.updateProfile({
        grade_level: gradeLevel,
        daily_goal_minutes: Number(dailyGoal) || 20,
        ui_preferences: {
          theme,
          textSize,
          reduceMotion,
          sounds,
          showCameraPreview,
          breakIntervalMinutes,
        },
      });
      setProfile(updated);
      markSaved();
    } catch (err) {
      setError(err.response?.data?.error || 'Failed to save.');
    } finally {
      setSaving(false);
    }
  };

  if (loading) return <LoadingSpinner label="Loading settings…" />;

  return (
    <div className="max-w-2xl mx-auto space-y-6 animate-fade-in">
      <div>
        <h1 className="font-display text-2xl font-bold text-text">Settings</h1>
        <p className="text-sm text-text-muted mt-1">Make Luma feel right for you.</p>
      </div>

      {error && <ErrorBanner message={error} onDismiss={() => setError(null)} />}
      {savedAt && (
        <p className="text-sm text-success font-semibold" role="status" aria-live="polite">
          ✓ Saved — your changes are kept on this account.
        </p>
      )}

      <Card className="p-5 space-y-5">
        <h2 className="font-display font-bold text-text">Look &amp; feel</h2>

        <fieldset className="space-y-3">
          <legend className="text-sm font-semibold text-text">Theme</legend>
          <p className="text-xs text-text-muted -mt-1">
            Plain backgrounds only — learning screens stay still and uncluttered.
          </p>
          <div
            className="grid grid-cols-1 sm:grid-cols-2 gap-2"
            role="radiogroup"
            aria-label="Colour theme"
          >
            {THEME_OPTIONS.map((opt) => {
              const selected = theme === opt.value;
              return (
                <button
                  key={opt.value}
                  type="button"
                  role="radio"
                  aria-checked={selected}
                  onClick={() => savePrefs({ theme: opt.value })}
                  className={`flex items-start gap-3 min-h-14 px-3 py-3 rounded-2xl border text-left cursor-pointer transition-colors ${
                    selected
                      ? 'border-primary border-2 bg-primary-soft'
                      : 'border-border bg-surface hover:border-primary/40'
                  }`}
                >
                  <span
                    className="theme-swatch mt-0.5"
                    style={{
                      background:
                        opt.value === 'sage'
                          ? '#eef3ee'
                          : opt.value === 'warm'
                            ? '#f3efe8'
                            : opt.value === 'pale-blue'
                              ? '#e8eef4'
                              : '#161c28',
                    }}
                    aria-hidden="true"
                  />
                  <span>
                    <span className="block text-sm font-semibold text-text">{opt.label}</span>
                    <span className="block text-xs text-text-muted">{opt.hint}</span>
                  </span>
                </button>
              );
            })}
          </div>
        </fieldset>

        <SegmentedControl
          label="Text size"
          options={[
            { value: 's', label: 'Small' },
            { value: 'm', label: 'Medium' },
            { value: 'l', label: 'Large' },
          ]}
          value={textSize}
          onChange={(v) => savePrefs({ textSize: v })}
        />
        <ToggleRow
          label="Reduce motion"
          hint="Calms short transitions and turns off celebrations. Learning backgrounds stay still either way."
          checked={reduceMotion}
          onChange={(v) => savePrefs({ reduceMotion: v })}
        />
        <ToggleRow
          label="Sounds"
          hint="Soft sounds during break breathing exercises."
          checked={sounds}
          onChange={(v) => savePrefs({ sounds: v })}
        />
        <ToggleRow
          label="Show camera preview by default"
          hint="Hiding the preview never stops monitoring — it only hides the picture."
          checked={showCameraPreview}
          onChange={(v) => savePrefs({ showCameraPreview: v })}
        />
        <Field label="Suggested break every (minutes)" hint="Used to suggest a short break during long study sessions.">
          {(id) => (
            <Input
              id={id}
              type="number"
              min={10}
              max={40}
              value={breakIntervalMinutes}
              onChange={(e) =>
                savePrefs({ breakIntervalMinutes: Number(e.target.value) || 18 })
              }
            />
          )}
        </Field>
      </Card>

      <Card className="p-5 space-y-4">
        <h2 className="font-display font-bold text-text">Profile</h2>
        <p className="text-sm text-text-muted">
          {profile?.first_name} {profile?.last_name} · {profile?.email}
        </p>
        {profile?.consent_given ? (
          <p className="text-sm text-success font-medium">
            Guardian monitoring consent is on file (set by teacher / guardian).
          </p>
        ) : (
          <p className="text-sm text-text-muted">
            Monitoring consent is managed by your teacher or guardian — ask them if sessions won&apos;t start.
          </p>
        )}
        <form onSubmit={saveProfile} className="space-y-4">
          <Field label="Grade">
            {(id) => (
              <Select id={id} value={gradeLevel} onChange={(e) => setGradeLevel(e.target.value)}>
                <option value="">Select…</option>
                {gradeLevels.map((g) => (
                  <option key={g.id || g.name} value={g.name}>
                    {g.name}
                  </option>
                ))}
              </Select>
            )}
          </Field>
          <Field label="Daily focus goal (minutes)" hint="Shown on your dashboard. Pick something that feels doable.">
            {(id) => (
              <Input
                id={id}
                type="number"
                min={5}
                max={120}
                value={dailyGoal}
                onChange={(e) => setDailyGoal(e.target.value)}
              />
            )}
          </Field>
          <Button type="submit" disabled={saving}>
            {saving ? 'Saving…' : 'Save profile'}
          </Button>
        </form>
      </Card>
    </div>
  );
}
