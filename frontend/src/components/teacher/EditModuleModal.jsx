import { useState, useEffect } from 'react';
import { Edit3, X, AlertCircle, Save } from 'lucide-react';
import { courseService } from '../../services/courseService';

export const EditModuleModal = ({ isOpen, moduleData, onClose, onSuccess }) => {
  const [title, setTitle] = useState('');
  const [description, setDescription] = useState('');
  const [sequenceOrder, setSequenceOrder] = useState('1');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (isOpen && moduleData) {
      setTitle(moduleData.title || '');
      setDescription(moduleData.description || '');
      setSequenceOrder((moduleData.sequence_order || 1).toString());
    }
  }, [isOpen, moduleData]);

  if (!isOpen || !moduleData) return null;

  const handleResetAndClose = () => {
    setError(null);
    onClose();
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError(null);

    if (!title.trim()) {
      setError('Module title is required.');
      return;
    }

    setLoading(true);

    try {
      await courseService.updateModule(moduleData.id, {
        title: title.trim(),
        description: description.trim() || null,
        sequence_order: parseInt(sequenceOrder, 10),
      });
      onSuccess();
      handleResetAndClose();
    } catch (err) {
      const details = err.response?.data?.details;
      if (details && Array.isArray(details) && details.length > 0) {
        setError(details.map((d) => `${d.field}: ${d.message}`).join(' | '));
      } else {
        setError(err.response?.data?.error || 'Failed to update module. Please try again.');
      }
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 bg-bg/60 backdrop-blur-sm flex items-center justify-center p-4 z-50 overflow-y-auto font-sans">
      <div role="dialog" aria-modal="true" className="bg-surface rounded-2xl p-6 md:p-8 max-w-lg w-full shadow-2xl space-y-6 my-8">
        
        {/* Header */}
        <div className="flex items-center justify-between border-b border-border pb-4">
          <div className="flex items-center gap-3">
            <div className="p-2.5 bg-primary-soft text-primary rounded-xl border border-primary/30">
              <Edit3 className="w-5 h-5" />
            </div>
            <div>
              <h2 className="text-lg font-bold text-text leading-tight">
                Edit Syllabus Module
              </h2>
              <p className="text-xs text-text-muted font-medium">
                Update module title, sequence order, or description.
              </p>
            </div>
          </div>
          <button
            onClick={handleResetAndClose}
            className="p-1.5 text-text-muted hover:text-text-muted hover:bg-bg rounded-lg transition-colors cursor-pointer"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Error Banner */}
        {error && (
          <div className="p-3.5 rounded-xl bg-red-50 border border-red-200 text-red-700 text-xs font-medium flex items-center gap-2">
            <AlertCircle className="w-4 h-4 text-red-500 flex-shrink-0" />
            <span>{error}</span>
          </div>
        )}

        {/* Form */}
        <form onSubmit={handleSubmit} className="space-y-4 text-xs">
          <div>
            <label className="block font-bold text-text uppercase tracking-wider mb-1">
              Module Title *
            </label>
            <input
              type="text"
              required
              maxLength={150}
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              className="w-full bg-bg border border-border focus:border-primary focus:bg-surface focus:outline-none rounded-lg p-2.5 text-text font-semibold"
            />
          </div>

          <div>
            <label className="block font-bold text-text uppercase tracking-wider mb-1">
              Sequence Order *
            </label>
            <input
              type="number"
              required
              min={1}
              value={sequenceOrder}
              onChange={(e) => setSequenceOrder(e.target.value)}
              className="w-full bg-bg border border-border focus:border-primary focus:bg-surface focus:outline-none rounded-lg p-2.5 text-text font-bold"
            />
          </div>

          <div>
            <label className="block font-bold text-text uppercase tracking-wider mb-1">
              Module Description (Optional)
            </label>
            <textarea
              rows={3}
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              className="w-full bg-bg border border-border focus:border-primary focus:bg-surface focus:outline-none rounded-lg p-2.5 text-text resize-none"
            />
          </div>

          {/* Footer Actions */}
          <div className="pt-4 border-t border-border flex items-center justify-end gap-3">
            <button
              type="button"
              onClick={handleResetAndClose}
              className="px-4 py-2 text-xs font-semibold text-text-muted hover:bg-bg rounded-lg transition-colors cursor-pointer"
            >
              Cancel
            </button>

            <button
              type="submit"
              disabled={loading}
              className="bg-primary hover:bg-primary-hover text-on-primary text-xs font-bold px-5 py-2.5 rounded-lg shadow-xs transition-all flex items-center gap-2 cursor-pointer disabled:opacity-50"
            >
              <Save className="w-4 h-4" />
              <span>{loading ? 'Saving...' : 'Save Changes'}</span>
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};

export default EditModuleModal;
