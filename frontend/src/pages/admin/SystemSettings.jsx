import { useState, useEffect } from 'react';
import { Settings, Save, CheckCircle2, AlertCircle, ShieldAlert, Clock, Database, RefreshCw } from 'lucide-react';
import { adminService } from '../../services/adminService';

export const SystemSettings = () => {
  const [formData, setFormData] = useState({
    intervention_min_cooldown_seconds: '30',
    intervention_max_cooldown_seconds: '120',
    data_retention_days: '90',
  });
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [successMsg, setSuccessMsg] = useState(null);
  const [errorMsg, setErrorMsg] = useState(null);
  const [detailsErrors, setDetailsErrors] = useState([]);

  const fetchSettings = async () => {
    setLoading(true);
    setErrorMsg(null);
    try {
      const data = await adminService.getSettings();
      setFormData({
        intervention_min_cooldown_seconds: data.intervention_min_cooldown_seconds || '30',
        intervention_max_cooldown_seconds: data.intervention_max_cooldown_seconds || '120',
        data_retention_days: data.data_retention_days || '90',
      });
    } catch (err) {
      setErrorMsg(err.response?.data?.error || 'Failed to load system settings');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchSettings();
  }, []);

  const handleChange = (e) => {
    const { name, value } = e.target;
    setFormData((prev) => ({ ...prev, [name]: value }));
    setSuccessMsg(null);
    setErrorMsg(null);
    setDetailsErrors([]);
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setSaving(true);
    setSuccessMsg(null);
    setErrorMsg(null);
    setDetailsErrors([]);

    try {
      const updated = await adminService.updateSettings(formData);
      setFormData({
        intervention_min_cooldown_seconds: updated.intervention_min_cooldown_seconds || '30',
        intervention_max_cooldown_seconds: updated.intervention_max_cooldown_seconds || '120',
        data_retention_days: updated.data_retention_days || '90',
      });
      setSuccessMsg('System settings updated successfully.');
    } catch (err) {
      const resp = err.response?.data;
      setErrorMsg(resp?.error || 'Failed to update system settings.');
      if (resp?.details && Array.isArray(resp.details)) {
        setDetailsErrors(resp.details);
      }
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return (
      <div className="max-w-4xl mx-auto p-12 text-center text-text-muted text-xs font-medium font-sans">
        Loading system configuration...
      </div>
    );
  }

  return (
    <div className="max-w-4xl mx-auto space-y-6 font-sans">
      {/* Header */}
      <div className="flex items-center gap-3 pb-4 border-b border-border">
        <div className="p-3 bg-primary-soft text-primary rounded-2xl border border-primary/30">
          <Settings className="w-6 h-6" />
        </div>
        <div>
          <h1 className="text-2xl font-bold text-text tracking-tight">System Settings</h1>
          <p className="text-xs text-text-muted font-medium mt-0.5">
            Configure global platform parameters, intervention engine bounds, and data retention policies.
          </p>
        </div>
      </div>

      {/* Success Notification Banner */}
      {successMsg && (
        <div className="p-4 rounded-xl bg-emerald-50 border border-emerald-200 text-emerald-800 text-xs font-semibold flex items-center gap-2.5 shadow-xs">
          <CheckCircle2 className="w-4 h-4 text-emerald-600 flex-shrink-0" />
          <span>{successMsg}</span>
        </div>
      )}

      {/* Error Notification Banner */}
      {errorMsg && (
        <div className="p-4 rounded-xl bg-red-50 border border-red-200 text-red-800 text-xs font-medium space-y-1 shadow-xs">
          <div className="flex items-center gap-2.5 font-bold">
            <AlertCircle className="w-4 h-4 text-red-600 flex-shrink-0" />
            <span>{errorMsg}</span>
          </div>
          {detailsErrors.length > 0 && (
            <ul className="list-disc list-inside pl-6 text-[11px] text-red-700 space-y-0.5 font-medium">
              {detailsErrors.map((item, idx) => (
                <li key={idx}>{item}</li>
              ))}
            </ul>
          )}
        </div>
      )}

      <form onSubmit={handleSubmit} className="space-y-6">
        {/* Section 1: Intervention Engine Cooldown Bounds */}
        <div className="bg-surface border border-border/80 rounded-2xl p-6 shadow-sm space-y-5">
          <div className="flex items-center gap-2.5 border-b border-border pb-3">
            <Clock className="w-4 h-4 text-primary" />
            <h2 className="text-sm font-bold text-text uppercase tracking-wider">
              Intervention Engine Cooldown Bounds (FR-ADM-05)
            </h2>
          </div>
          <p className="text-xs text-text-muted">
            Set the minimum and maximum cooldown windows applied between real-time distraction interventions during student learning sessions.
          </p>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
            <div className="space-y-1.5">
              <label className="text-xs font-bold text-text block">
                Minimum Cooldown (Seconds)
              </label>
              <input
                type="number"
                name="intervention_min_cooldown_seconds"
                value={formData.intervention_min_cooldown_seconds}
                onChange={handleChange}
                min="1"
                max="600"
                className="w-full px-3.5 py-2.5 bg-bg border border-border rounded-xl text-xs text-text font-mono font-semibold focus:outline-none focus:border-primary focus:bg-surface transition-all"
                required
              />
              <span className="text-[11px] text-text-muted block">
                Minimum interval required before triggering a new prompt (default: 30s)
              </span>
            </div>

            <div className="space-y-1.5">
              <label className="text-xs font-bold text-text block">
                Maximum Cooldown (Seconds)
              </label>
              <input
                type="number"
                name="intervention_max_cooldown_seconds"
                value={formData.intervention_max_cooldown_seconds}
                onChange={handleChange}
                min="1"
                max="3600"
                className="w-full px-3.5 py-2.5 bg-bg border border-border rounded-xl text-xs text-text font-mono font-semibold focus:outline-none focus:border-primary focus:bg-surface transition-all"
                required
              />
              <span className="text-[11px] text-text-muted block">
                Upper bound for progressive debounce backoff (default: 120s)
              </span>
            </div>
          </div>
        </div>

        {/* Section 2: Data Retention Policy */}
        <div className="bg-surface border border-border/80 rounded-2xl p-6 shadow-sm space-y-5">
          <div className="flex items-center gap-2.5 border-b border-border pb-3">
            <Database className="w-4 h-4 text-primary" />
            <h2 className="text-sm font-bold text-text uppercase tracking-wider">
              Data Retention & Archival Policy
            </h2>
          </div>

          <div className="space-y-1.5 max-w-md">
            <label className="text-xs font-bold text-text block">
              Data Retention Period (Days)
            </label>
            <input
              type="number"
              name="data_retention_days"
              value={formData.data_retention_days}
              onChange={handleChange}
              min="1"
              max="3650"
              className="w-full px-3.5 py-2.5 bg-bg border border-border rounded-xl text-xs text-text font-mono font-semibold focus:outline-none focus:border-primary focus:bg-surface transition-all"
              required
            />
            <span className="text-[11px] text-text-muted block">
              Historical telemetry and distraction event retention window in days (default: 90 days)
            </span>
          </div>
        </div>

        {/* Submit Actions */}
        <div className="flex items-center justify-end gap-3 pt-2">
          <button
            type="submit"
            disabled={saving}
            className="bg-primary hover:bg-primary-hover text-on-primary text-xs font-bold px-6 py-2.5 rounded-xl shadow-xs transition-all flex items-center gap-2 cursor-pointer disabled:opacity-50"
          >
            {saving ? (
              <>
                <RefreshCw className="w-4 h-4 animate-spin" />
                <span>Saving Changes...</span>
              </>
            ) : (
              <>
                <Save className="w-4 h-4" />
                <span>Save System Settings</span>
              </>
            )}
          </button>
        </div>
      </form>
    </div>
  );
};

export default SystemSettings;
