import { useState } from 'react';
import { X, UserPlus, AlertCircle } from 'lucide-react';
import { adminService } from '../../services/adminService';

const INITIAL_FORM_STATE = {
  role: 'student',
  first_name: '',
  last_name: '',
  email: '',
  password: '',
  guardian_name: '',
  guardian_email: '',
};

export const CreateUserModal = ({ isOpen, onClose, onSuccess }) => {
  const [formData, setFormData] = useState(INITIAL_FORM_STATE);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  if (!isOpen) return null;

  const handleChange = (e) => {
    const { name, value } = e.target;
    setFormData((prev) => ({ ...prev, [name]: value }));
  };

  const handleResetAndClose = () => {
    setFormData(INITIAL_FORM_STATE);
    setError(null);
    setLoading(false);
    onClose();
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError(null);

    // Client-side validation matching Pydantic backend validation
    if (!formData.first_name.trim() || !formData.last_name.trim() || !formData.email.trim() || !formData.password) {
      setError('Please fill in all required fields.');
      return;
    }

    if (formData.password.length < 8) {
      setError('Password must be at least 8 characters long.');
      return;
    }

    if (formData.role === 'student') {
      if (!formData.guardian_name.trim() || !formData.guardian_email.trim()) {
        setError('Guardian name and guardian email are required for student registrations.');
        return;
      }
    }

    setLoading(true);

    const payload = {
      email: formData.email.trim(),
      password: formData.password,
      first_name: formData.first_name.trim(),
      last_name: formData.last_name.trim(),
      role: formData.role,
    };

    if (formData.role === 'student') {
      payload.guardian_name = formData.guardian_name.trim();
      payload.guardian_email = formData.guardian_email.trim();
    }

    try {
      await adminService.createUser(payload);
      onSuccess();
      handleResetAndClose();
    } catch (err) {
      const details = err.response?.data?.details;
      if (details && Array.isArray(details) && details.length > 0) {
        setError(
          details
            .map((d) => {
              const fieldName = d.field || (Array.isArray(d.loc) ? d.loc[d.loc.length - 1] : d.loc) || 'field';
              const msgText = d.message || d.msg || 'invalid value';
              return `${fieldName}: ${msgText}`;
            })
            .join(' | ')
        );
      } else {
        setError(err.response?.data?.error || 'Failed to create user. Please try again.');
      }
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 bg-bg/60 backdrop-blur-sm flex items-center justify-center p-4 z-50 overflow-y-auto">
      <div role="dialog" aria-modal="true" className="bg-surface rounded-2xl p-6 md:p-8 max-w-lg w-full shadow-2xl space-y-6 my-8">
        
        {/* Modal Header */}
        <div className="flex justify-between items-center border-b border-border pb-4">
          <div className="flex items-center gap-2.5">
            <div className="w-9 h-9 rounded-xl bg-primary/10 text-primary flex items-center justify-center font-bold">
              <UserPlus className="w-5 h-5" />
            </div>
            <div>
              <h3 className="font-bold text-text text-base">Register New User</h3>
              <p className="text-xs text-text-muted font-medium">Create a Teacher or Student account</p>
            </div>
          </div>
          <button
            type="button"
            onClick={handleResetAndClose}
            className="text-text-muted hover:text-text-muted transition-colors cursor-pointer"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Error Alert Banner */}
        {error && (
          <div className="p-3.5 rounded-xl bg-red-50 border border-red-200 text-red-700 text-xs font-medium flex items-center gap-2">
            <AlertCircle className="w-4 h-4 text-red-500 flex-shrink-0" />
            <span>{error}</span>
          </div>
        )}

        {/* User Registration Form */}
        <form onSubmit={handleSubmit} className="space-y-4 text-xs">
          
          {/* Role Selection Tabs */}
          <div>
            <label className="block font-bold text-text uppercase tracking-wider mb-1.5">
              Account Role
            </label>
            <div className="grid grid-cols-2 gap-2 p-1 bg-bg/80 rounded-xl font-semibold text-xs">
              <button
                type="button"
                onClick={() => setFormData((prev) => ({ ...prev, role: 'student' }))}
                className={`py-2 rounded-lg transition-all cursor-pointer ${
                  formData.role === 'student'
                    ? 'bg-surface text-primary shadow-sm font-bold'
                    : 'text-text-muted hover:text-text'
                }`}
              >
                Student
              </button>
              <button
                type="button"
                onClick={() => setFormData((prev) => ({ ...prev, role: 'teacher' }))}
                className={`py-2 rounded-lg transition-all cursor-pointer ${
                  formData.role === 'teacher'
                    ? 'bg-surface text-primary shadow-sm font-bold'
                    : 'text-text-muted hover:text-text'
                }`}
              >
                Teacher
              </button>
            </div>
          </div>

          {/* First & Last Name */}
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block font-bold text-text uppercase tracking-wider mb-1">
                First Name *
              </label>
              <input
                type="text"
                name="first_name"
                required
                value={formData.first_name}
                onChange={handleChange}
                placeholder="e.g. Alex"
                className="w-full bg-bg border border-border focus:border-primary focus:bg-surface focus:outline-none rounded-lg p-2.5 text-text"
              />
            </div>
            <div>
              <label className="block font-bold text-text uppercase tracking-wider mb-1">
                Last Name *
              </label>
              <input
                type="text"
                name="last_name"
                required
                value={formData.last_name}
                onChange={handleChange}
                placeholder="e.g. Smith"
                className="w-full bg-bg border border-border focus:border-primary focus:bg-surface focus:outline-none rounded-lg p-2.5 text-text"
              />
            </div>
          </div>

          {/* Email */}
          <div>
            <label className="block font-bold text-text uppercase tracking-wider mb-1">
              Email Address *
            </label>
            <input
              type="email"
              name="email"
              required
              value={formData.email}
              onChange={handleChange}
              placeholder="user@example.com"
              className="w-full bg-bg border border-border focus:border-primary focus:bg-surface focus:outline-none rounded-lg p-2.5 text-text"
            />
          </div>

          {/* Password */}
          <div>
            <label className="block font-bold text-text uppercase tracking-wider mb-1">
              Password *
            </label>
            <input
              type="password"
              name="password"
              required
              minLength={8}
              maxLength={72}
              value={formData.password}
              onChange={handleChange}
              placeholder="••••••••"
              className="w-full bg-bg border border-border focus:border-primary focus:bg-surface focus:outline-none rounded-lg p-2.5 text-text"
            />
            <span className="text-[11px] text-text-muted font-medium mt-1 block">
              Must be at least 8 characters long.
            </span>
          </div>

          {/* Conditional Guardian Fields for Student */}
          {formData.role === 'student' && (
            <div className="p-3.5 bg-primary-soft/60 border border-primary/30 rounded-xl space-y-3 mt-2">
              <div className="text-[11px] font-bold text-primary">
                Guardian Consent Information (Required for Students)
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block font-bold text-text uppercase tracking-wider mb-1">
                    Guardian Name *
                  </label>
                  <input
                    type="text"
                    name="guardian_name"
                    required={formData.role === 'student'}
                    value={formData.guardian_name}
                    onChange={handleChange}
                    placeholder="Parent / Guardian Name"
                    className="w-full bg-surface border border-border focus:border-primary focus:outline-none rounded-lg p-2 text-text"
                  />
                </div>
                <div>
                  <label className="block font-bold text-text uppercase tracking-wider mb-1">
                    Guardian Email *
                  </label>
                  <input
                    type="email"
                    name="guardian_email"
                    required={formData.role === 'student'}
                    value={formData.guardian_email}
                    onChange={handleChange}
                    placeholder="guardian@example.com"
                    className="w-full bg-surface border border-border focus:border-primary focus:outline-none rounded-lg p-2 text-text"
                  />
                </div>
              </div>
            </div>
          )}

          {/* Modal Actions */}
          <div className="flex justify-end gap-3 pt-4 border-t border-border">
            <button
              type="button"
              onClick={handleResetAndClose}
              className="px-4 py-2 font-semibold text-text-muted hover:bg-bg rounded-lg cursor-pointer transition-colors"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={loading}
              className="px-5 py-2 font-semibold text-on-primary bg-primary hover:bg-primary-hover rounded-lg cursor-pointer shadow-sm transition-all disabled:opacity-60 disabled:cursor-not-allowed"
            >
              {loading ? 'Creating...' : 'Create User'}
            </button>
          </div>
        </form>

      </div>
    </div>
  );
};

export default CreateUserModal;
