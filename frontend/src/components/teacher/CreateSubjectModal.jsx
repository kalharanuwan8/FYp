import { useState, useEffect } from 'react';
import { BookOpen, X, AlertCircle, Sparkles } from 'lucide-react';
import { courseService } from '../../services/courseService';

export const CreateSubjectModal = ({ isOpen, onClose, onSuccess }) => {
  const [title, setTitle] = useState('');
  const [description, setDescription] = useState('');
  const [gradeLevelId, setGradeLevelId] = useState('');

  const [gradeLevels, setGradeLevels] = useState([]);
  const [loading, setLoading] = useState(false);
  const [fetchingLevels, setFetchingLevels] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (isOpen) {
      const fetchLevels = async () => {
        setFetchingLevels(true);
        setError(null);
        try {
          const levels = await courseService.getGradeLevels();
          setGradeLevels(levels);
          if (levels.length > 0) {
            setGradeLevelId(levels[0].id.toString());
          }
        } catch (err) {
          setError('Failed to load grade levels.');
        } finally {
          setFetchingLevels(false);
        }
      };
      fetchLevels();
    }
  }, [isOpen]);

  if (!isOpen) return null;

  const handleResetAndClose = () => {
    setTitle('');
    setDescription('');
    setGradeLevelId('');
    setError(null);
    onClose();
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError(null);

    if (!title.trim()) {
      setError('Course title is required.');
      return;
    }

    if (!gradeLevelId) {
      setError('Please select a valid Grade Level.');
      return;
    }

    setLoading(true);

    try {
      await courseService.createSubject({
        title: title.trim(),
        description: description.trim() || null,
        grade_level_id: parseInt(gradeLevelId, 10),
      });
      onSuccess();
      handleResetAndClose();
    } catch (err) {
      const details = err.response?.data?.details;
      if (details && Array.isArray(details) && details.length > 0) {
        setError(details.map((d) => `${d.field}: ${d.message}`).join(' | '));
      } else {
        setError(err.response?.data?.error || 'Failed to create course. Please try again.');
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
              <BookOpen className="w-5 h-5" />
            </div>
            <div>
              <h2 className="text-lg font-bold text-text leading-tight">
                Create New Subject Course
              </h2>
              <p className="text-xs text-text-muted font-medium">
                Add a new subject to your teaching curriculum.
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
              Course Title *
            </label>
            <input
              type="text"
              required
              maxLength={150}
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="e.g. Science & Nature Exploration"
              className="w-full bg-bg border border-border focus:border-primary focus:bg-surface focus:outline-none rounded-lg p-2.5 text-text"
            />
          </div>

          <div>
            <label className="block font-bold text-text uppercase tracking-wider mb-1">
              Target Grade Level *
            </label>
            {fetchingLevels ? (
              <div className="p-2.5 bg-bg border border-border rounded-lg text-text-muted font-medium">
                Loading grade levels...
              </div>
            ) : (
              <select
                required
                value={gradeLevelId}
                onChange={(e) => setGradeLevelId(e.target.value)}
                className="w-full bg-bg border border-border focus:border-primary focus:bg-surface focus:outline-none rounded-lg p-2.5 text-text font-semibold"
              >
                {gradeLevels.map((gl) => (
                  <option key={gl.id} value={gl.id}>
                    {gl.name}
                  </option>
                ))}
              </select>
            )}
          </div>

          <div>
            <label className="block font-bold text-text uppercase tracking-wider mb-1">
              Course Description (Optional)
            </label>
            <textarea
              rows={3}
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="Provide a brief overview of course objectives and syllabus topics..."
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
              disabled={loading || fetchingLevels}
              className="bg-primary hover:bg-primary-hover text-on-primary text-xs font-bold px-5 py-2.5 rounded-lg shadow-xs transition-all flex items-center gap-2 cursor-pointer disabled:opacity-50"
            >
              <Sparkles className="w-4 h-4" />
              <span>{loading ? 'Creating...' : 'Create Course'}</span>
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};

export default CreateSubjectModal;
