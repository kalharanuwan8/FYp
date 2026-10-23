import { useEffect, useState } from 'react';
import { Shield, Save } from 'lucide-react';
import { courseService } from '../../services/courseService';

/**
 * Teacher per-course tier enable/disable for micro-interventions.
 */
export default function InterventionSettings({ subjectId }) {
  const [config, setConfig] = useState(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);
  const [savedMsg, setSavedMsg] = useState(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      setLoading(true);
      setError(null);
      try {
        const data = await courseService.getInterventionConfig(subjectId);
        if (!cancelled) setConfig(data);
      } catch (err) {
        if (!cancelled) {
          setError(err.response?.data?.error || 'Failed to load intervention settings');
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [subjectId]);

  const toggle = (key) => {
    setConfig((prev) => (prev ? { ...prev, [key]: !prev[key] } : prev));
    setSavedMsg(null);
  };

  const handleSave = async () => {
    if (!config) return;
    setSaving(true);
    setError(null);
    setSavedMsg(null);
    try {
      const updated = await courseService.updateInterventionConfig(subjectId, {
        tier1_enabled: config.tier1_enabled,
        tier2_enabled: config.tier2_enabled,
        tier3_enabled: config.tier3_enabled,
        tier4_enabled: config.tier4_enabled,
      });
      setConfig(updated);
      setSavedMsg('Intervention settings saved.');
    } catch (err) {
      setError(err.response?.data?.error || 'Failed to save settings');
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return (
      <div className="text-xs text-text-muted p-4 border border-border rounded-2xl">
        Loading intervention settings…
      </div>
    );
  }

  if (error && !config) {
    return (
      <div className="text-xs text-red-600 p-4 border border-red-200 bg-red-50 rounded-2xl">
        {error}
      </div>
    );
  }

  const tiers = [
    { key: 'tier1_enabled', label: 'Tier 1 — Ambient cue', hint: 'Subtle visual cue, no content pause' },
    { key: 'tier2_enabled', label: 'Tier 2 — Pacing pause', hint: 'Auto-pause + “still with me?” prompt' },
    { key: 'tier3_enabled', label: 'Tier 3 — Active break / hint', hint: 'Gamified break or quiz hint' },
    { key: 'tier4_enabled', label: 'Tier 4 — Structural', hint: 'Pacing reduction or suggest break' },
  ];

  return (
    <div className="bg-surface border border-border/80 rounded-2xl p-6 space-y-5 shadow-xs">
      <div className="flex items-start gap-3">
        <div className="w-10 h-10 rounded-xl bg-primary/10 text-primary flex items-center justify-center">
          <Shield className="w-5 h-5" />
        </div>
        <div>
          <h3 className="text-sm font-bold text-text">Intervention tiers</h3>
          <p className="text-[11px] text-text-muted mt-0.5 leading-relaxed">
            Disable tiers for this course. If a computed tier is off, the engine falls back one
            tier instead of skipping the intervention.
          </p>
        </div>
      </div>

      <div className="space-y-3">
        {tiers.map((t) => (
          <label
            key={t.key}
            className="flex items-start gap-3 p-3 rounded-xl border border-border hover:bg-bg cursor-pointer"
          >
            <input
              type="checkbox"
              checked={Boolean(config?.[t.key])}
              onChange={() => toggle(t.key)}
              className="mt-0.5 rounded border-border text-primary focus:ring-primary"
            />
            <span>
              <span className="text-xs font-bold text-text block">{t.label}</span>
              <span className="text-[11px] text-text-muted">{t.hint}</span>
            </span>
          </label>
        ))}
      </div>

      {error && (
        <p className="text-xs text-red-600 bg-red-50 border border-red-100 rounded-xl px-3 py-2">
          {error}
        </p>
      )}
      {savedMsg && (
        <p className="text-xs text-emerald-700 bg-emerald-50 border border-emerald-100 rounded-xl px-3 py-2">
          {savedMsg}
        </p>
      )}

      <button
        type="button"
        onClick={handleSave}
        disabled={saving}
        className="inline-flex items-center gap-2 px-4 py-2.5 rounded-xl bg-primary hover:bg-primary-hover text-on-primary text-xs font-bold disabled:opacity-50 cursor-pointer"
      >
        <Save className="w-3.5 h-3.5" />
        {saving ? 'Saving…' : 'Save settings'}
      </button>
    </div>
  );
}
