import { useEffect, useState } from 'react';
import { X, Pencil, AlertCircle } from 'lucide-react';
import { adminService } from '../../services/adminService';
import courseService from '../../services/courseService';

export default function EditUserModal({ user, isOpen, onClose, onSuccess }) {
  const [formData, setFormData] = useState(null);
  const [gradeLevels, setGradeLevels] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (!isOpen || !user) return;
    setFormData({
      first_name: user.first_name || '',
      last_name: user.last_name || '',
      email: user.email || '',
      password: '',
      grade_level: user.grade_level || '',
      guardian_name: user.guardian_name || '',
      guardian_email: user.guardian_email || '',
      consent_given: Boolean(user.guardian_consent_given),
    });
    setError(null);
    setLoading(false);
  }, [isOpen, user]);

  useEffect(() => {
    if (!isOpen || user?.role !== 'student') return;
    let cancelled = false;
    courseService
      .getGradeLevels()
      .then((levels) => {
        if (!cancelled) setGradeLevels(levels || []);
      })
      .catch(() => {
        if (!cancelled) setGradeLevels([]);
      });
    return () => {
      cancelled = true;
    };
  }, [isOpen, user?.role]);

  if (!isOpen || !user || !formData) return null;

  const isStudent = String(user.role).toLowerCase() === 'student';

  const handleChange = (e) => {
    const { name, value, type, checked } = e.target;
    setFormData((prev) => ({ ...prev, [name]: type === 'checkbox' ? checked : value }));
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError(null);

    if (!formData.first_name.trim() || !formData.last_name.trim() || !formData.email.trim()) {
      setError('Name and email are required.');
      return;
    }
    if (formData.password && formData.password.length < 8) {
      setError('A new password must be at least 8 characters, or leave it blank.');
      return;
    }
    if (isStudent && (!formData.guardian_name.trim() || !formData.guardian_email.trim())) {
      setError('Guardian name and email are required for a student.');
      return;
    }

    const payload = {
      first_name: formData.first_name.trim(),
      last_name: formData.last_name.trim(),
      email: formData.email.trim(),
    };
    if (formData.password) payload.password = formData.password;
    if (isStudent) {
      payload.grade_level = formData.grade_level;
      payload.guardian_name = formData.guardian_name.trim();
      payload.guardian_email = formData.guardian_email.trim();
      payload.consent_given = Boolean(formData.consent_given);
    }

    setLoading(true);
    try {
      await adminService.updateUser(user.id, payload);
      onSuccess?.();
      onClose?.();
    } catch (err) {
      setError(err.response?.data?.error || 'Could not save this user.');
    } finally {
      setLoading(false);
    }
  };

  const gradeNames = gradeLevels.map((g) => g.name);
  const gradeOptions =
    formData.grade_level && !gradeNames.includes(formData.grade_level)
      ? [formData.grade_level, ...gradeNames]
      : gradeNames;

  return (
    <div className="fixed inset-0 bg-bg/60 backdrop-blur-sm flex items-center justify-center p-4 z-50 overflow-y-auto">
      <div role="dialog" aria-modal="true" aria-labelledby="edit-user-title" className="bg-surface rounded-2xl p-6 md:p-8 max-w-lg w-full shadow-2xl space-y-6 my-8">
        <div className="flex justify-between items-center border-b border-border pb-4">
          <div className="flex items-center gap-2.5">
            <div className="w-9 h-9 rounded-xl bg-primary/10 text-primary flex items-center justify-center">
              <Pencil className="w-5 h-5" aria-hidden="true" />
            </div>
            <div>
              <h3 id="edit-user-title" className="font-bold text-text text-base">Edit user</h3>
              <p className="text-xs text-text-muted font-medium capitalize">{user.role} account</p>
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close"
            className="text-text-muted hover:text-text cursor-pointer"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {error && (
          <div className="p-3.5 rounded-xl bg-red-50 border border-red-200 text-red-700 text-xs font-medium flex items-center gap-2" role="alert">
            <AlertCircle className="w-4 h-4 text-red-500 shrink-0" aria-hidden="true" />
            <span>{error}</span>
          </div>
        )}

        <form onSubmit={handleSubmit} className="space-y-4 text-xs">
          <div className="grid grid-cols-2 gap-3">
            <label className="block">
              <span className="block font-bold text-text uppercase tracking-wider mb-1">First name</span>
              <input
                name="first_name"
                required
                value={formData.first_name}
                onChange={handleChange}
                className="w-full bg-bg border border-border focus:border-primary focus:bg-surface focus:outline-none rounded-lg p-2.5 text-text"
              />
            </label>
            <label className="block">
              <span className="block font-bold text-text uppercase tracking-wider mb-1">Last name</span>
              <input
                name="last_name"
                required
                value={formData.last_name}
                onChange={handleChange}
                className="w-full bg-bg border border-border focus:border-primary focus:bg-surface focus:outline-none rounded-lg p-2.5 text-text"
              />
            </label>
          </div>

          <label className="block">
            <span className="block font-bold text-text uppercase tracking-wider mb-1">Email</span>
            <input
              type="email"
              name="email"
              required
              value={formData.email}
              onChange={handleChange}
              className="w-full bg-bg border border-border focus:border-primary focus:bg-surface focus:outline-none rounded-lg p-2.5 text-text"
            />
          </label>

          <label className="block">
            <span className="block font-bold text-text uppercase tracking-wider mb-1">New password</span>
            <input
              type="password"
              name="password"
              value={formData.password}
              onChange={handleChange}
              autoComplete="new-password"
              placeholder="Leave blank to keep the current password"
              className="w-full bg-bg border border-border focus:border-primary focus:bg-surface focus:outline-none rounded-lg p-2.5 text-text"
            />
          </label>

          {isStudent && (
            <div className="space-y-4 rounded-xl border border-border bg-bg/50 p-4">
              <p className="font-bold text-text uppercase tracking-wider">Student &amp; guardian</p>
              <label className="block">
                <span className="block font-bold text-text uppercase tracking-wider mb-1">Grade</span>
                <select
                  name="grade_level"
                  value={formData.grade_level}
                  onChange={handleChange}
                  className="w-full bg-surface border border-border focus:border-primary focus:outline-none rounded-lg p-2.5 text-text"
                >
                  <option value="">Not set</option>
                  {gradeOptions.map((name) => (
                    <option key={name} value={name}>
                      {name}
                    </option>
                  ))}
                </select>
              </label>
              <label className="block">
                <span className="block font-bold text-text uppercase tracking-wider mb-1">Guardian name</span>
                <input
                  name="guardian_name"
                  required
                  value={formData.guardian_name}
                  onChange={handleChange}
                  className="w-full bg-surface border border-border focus:border-primary focus:outline-none rounded-lg p-2.5 text-text"
                />
              </label>
              <label className="block">
                <span className="block font-bold text-text uppercase tracking-wider mb-1">Guardian email</span>
                <input
                  type="email"
                  name="guardian_email"
                  required
                  value={formData.guardian_email}
                  onChange={handleChange}
                  className="w-full bg-surface border border-border focus:border-primary focus:outline-none rounded-lg p-2.5 text-text"
                />
              </label>
              <label className="flex items-start gap-2.5 cursor-pointer text-text">
                <input
                  type="checkbox"
                  name="consent_given"
                  checked={formData.consent_given}
                  onChange={handleChange}
                  className="mt-0.5 w-4 h-4"
                />
                <span>
                  <span className="block font-semibold">Guardian has agreed to monitoring</span>
                  <span className="block text-text-muted mt-0.5">
                    This is what lets the student start a monitored video lesson.
                  </span>
                </span>
              </label>
            </div>
          )}

          <div className="flex items-center justify-end gap-3 pt-2">
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-2 text-xs font-semibold text-text-muted hover:bg-bg rounded-lg cursor-pointer"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={loading}
              className="px-4 py-2 text-xs font-semibold text-on-primary bg-primary hover:bg-primary-hover rounded-lg cursor-pointer disabled:opacity-50"
            >
              {loading ? 'Saving…' : 'Save changes'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
