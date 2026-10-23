import { useState, useEffect } from 'react';
import studentService from '../../services/studentService';
import courseService from '../../services/courseService';
import { usePreferences } from '../../context/PreferencesContext';
import { Button, Dialog, Field, Select, SegmentedControl } from '../common';

const STEP_TITLES = ['Welcome to Luma', 'How your focus buddy works', 'Make it comfy'];

export default function FirstTimeOnboardingModal({ isOpen, onComplete, initialProfile }) {
  const { updatePreferences, theme, textSize } = usePreferences();
  const [step, setStep] = useState(0);
  const [gradeLevels, setGradeLevels] = useState([]);
  const [gradeLevel, setGradeLevel] = useState(initialProfile?.grade_level || '');
  const [assent, setAssent] = useState(false);
  const [localTheme, setLocalTheme] = useState(theme || 'light');
  const [localText, setLocalText] = useState(textSize || 'm');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (!isOpen) return;
    setStep(0);
    setGradeLevel(initialProfile?.grade_level || '');
    courseService
      .getGradeLevels()
      .then((data) => setGradeLevels(data || []))
      .catch(() => {});
  }, [isOpen, initialProfile]);

  if (!isOpen) return null;

  const finish = async () => {
    setError(null);
    if (!gradeLevel.trim()) {
      setError('Please pick your year / grade.');
      return;
    }
    if (!assent) {
      setError('Tick the box to show you understand how Focus buddy works.');
      return;
    }
    try {
      setSubmitting(true);
      await updatePreferences({ theme: localTheme, textSize: localText }, { persist: false });
      const updated = await studentService.updateProfile({
        grade_level: gradeLevel,
        student_assent: true,
        onboarding_completed: true,
        ui_preferences: {
          theme: localTheme,
          textSize: localText,
        },
      });
      onComplete?.(updated);
    } catch (err) {
      setError(err.response?.data?.error || 'Could not save. Try again.');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Dialog
      title={STEP_TITLES[step]}
      description={`Step ${step + 1} of 3`}
      allowEscape={false}
      panelClassName="max-w-lg"
    >
      <div className="flex justify-center gap-2" aria-hidden="true">
        {STEP_TITLES.map((_, i) => (
          <span
            key={i}
            className={`h-2 w-8 rounded-full ${i === step ? 'bg-primary' : 'bg-border'}`}
          />
        ))}
      </div>

      {step === 0 && (
        <div className="space-y-4">
          <p className="text-4xl text-center" aria-hidden="true">
            👋
          </p>
          <p className="text-text-muted prose-narrow mx-auto text-center">
            Calm, colourful learning with a focus buddy that helps you stay on track — never judges you.
          </p>
          <Field label="Your year / grade">
            {(id) => (
              <Select
                id={id}
                value={gradeLevel}
                onChange={(e) => setGradeLevel(e.target.value)}
              >
                <option value="">Select…</option>
                {gradeLevels.map((g) => (
                  <option key={g.id || g.name} value={g.name}>
                    {g.name}
                  </option>
                ))}
              </Select>
            )}
          </Field>
          <Button size="lg" className="w-full" onClick={() => setStep(1)} disabled={!gradeLevel}>
            Next
          </Button>
        </div>
      )}

      {step === 1 && (
        <div className="space-y-4">
          <ul className="space-y-3 text-sm text-text-muted">
            <li className="flex gap-2">
              <span aria-hidden="true">📷</span>
              <span>Optional camera helps sense when you might be drifting — it never records video to the cloud.</span>
            </li>
            <li className="flex gap-2">
              <span aria-hidden="true">🔊</span>
              <span>Your device also checks how loud the room is so we can suggest headphones or a quieter spot. Only the loudness level is sent — sound is never recorded or uploaded.</span>
            </li>
            <li className="flex gap-2">
              <span aria-hidden="true">🔒</span>
              <span>Your focus data stays private and is used only to help you learn.</span>
            </li>
            <li className="flex gap-2">
              <span aria-hidden="true">⏸️</span>
              <span>You can pause anytime with &quot;I need a break&quot;.</span>
            </li>
          </ul>
          <p className="text-sm text-text-muted rounded-2xl bg-primary-soft p-3">
            A parent or guardian (or your teacher) records monitoring consent. You just confirm you understand.
          </p>
          <label className="flex items-start gap-3 text-sm text-text cursor-pointer min-h-11">
            <input
              type="checkbox"
              checked={assent}
              onChange={(e) => setAssent(e.target.checked)}
              className="mt-1 w-5 h-5 rounded shrink-0"
            />
            <span>I understand how Focus buddy works and I&apos;m okay using it while I learn.</span>
          </label>
          <div className="flex gap-2">
            <Button variant="secondary" className="flex-1" onClick={() => setStep(0)}>
              Back
            </Button>
            <Button className="flex-1" onClick={() => setStep(2)} disabled={!assent}>
              Next
            </Button>
          </div>
        </div>
      )}

      {step === 2 && (
        <div className="space-y-4">
          <SegmentedControl
            label="Theme"
            options={[
              { value: 'light', label: 'Light' },
              { value: 'calm-dark', label: 'Calm dark' },
            ]}
            value={localTheme}
            onChange={setLocalTheme}
          />
          <SegmentedControl
            label="Text size"
            options={[
              { value: 's', label: 'Small' },
              { value: 'm', label: 'Medium' },
              { value: 'l', label: 'Large' },
            ]}
            value={localText}
            onChange={setLocalText}
          />
          {error && (
            <p className="text-sm text-danger font-medium" role="alert">
              {error}
            </p>
          )}
          <div className="flex gap-2">
            <Button variant="secondary" className="flex-1" onClick={() => setStep(1)}>
              Back
            </Button>
            <Button className="flex-1" onClick={finish} disabled={submitting}>
              {submitting ? 'Saving…' : "Let's go"}
            </Button>
          </div>
        </div>
      )}
    </Dialog>
  );
}
