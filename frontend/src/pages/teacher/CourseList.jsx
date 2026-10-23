import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { 
  BookOpen, 
  Plus, 
  Search, 
  Archive, 
  ChevronLeft, 
  ChevronRight, 
  AlertTriangle, 
  X,
  Layers
} from 'lucide-react';
import { courseService } from '../../services/courseService';
import CreateSubjectModal from '../../components/teacher/CreateSubjectModal';

export const CourseList = () => {
  const navigate = useNavigate();
  const [subjects, setSubjects] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const [search, setSearch] = useState('');
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);

  const [createModalOpen, setCreateModalOpen] = useState(false);
  const [selectedSubject, setSelectedSubject] = useState(null);
  const [archiveModalOpen, setArchiveModalOpen] = useState(false);
  const [archiving, setArchiving] = useState(false);

  const fetchSubjects = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await courseService.getSubjects({
        search,
        page,
        per_page: 9,
      });
      setSubjects(data.subjects || []);
      setTotalPages(data.pages || 1);
    } catch (err) {
      setError(err.response?.data?.error || 'Failed to fetch courses');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchSubjects();
  }, [page]);

  const handleSearchSubmit = (e) => {
    e.preventDefault();
    setPage(1);
    fetchSubjects();
  };

  const openArchiveConfirm = (subj) => {
    setSelectedSubject(subj);
    setArchiveModalOpen(true);
  };

  const handleToggleArchive = async () => {
    if (!selectedSubject) return;
    setArchiving(true);
    try {
      await courseService.archiveSubject(selectedSubject.id, !selectedSubject.is_archived);
      setArchiveModalOpen(false);
      setSelectedSubject(null);
      fetchSubjects();
    } catch (err) {
      setError(err.response?.data?.error || 'Failed to toggle course archive status');
    } finally {
      setArchiving(false);
    }
  };

  return (
    <div className="space-y-6 max-w-7xl mx-auto font-sans">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-text tracking-tight">My Courses & Subjects</h1>
          <p className="text-xs text-text-muted font-medium mt-1">
            Manage your assigned subjects, edit modules, and organize learning materials.
          </p>
        </div>
        <button
          onClick={() => setCreateModalOpen(true)}
          className="bg-primary hover:bg-primary-hover text-on-primary text-xs font-medium py-2.5 px-4 rounded-xl flex items-center gap-2 shadow-xs transition-all cursor-pointer self-start sm:self-auto"
        >
          <Plus className="w-4 h-4" />
          <span>Create Course</span>
        </button>
      </div>

      {/* Search Bar */}
      <div className="bg-surface border border-border/80 rounded-2xl p-4 shadow-xs flex items-center justify-between gap-4">
        <form onSubmit={handleSearchSubmit} className="relative w-full max-w-md">
          <Search className="w-4 h-4 text-text-muted absolute left-3.5 top-1/2 -translate-y-1/2" />
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search courses by title or description..."
            className="w-full bg-bg/80 border border-border focus:border-primary focus:bg-surface focus:outline-none rounded-xl py-2.5 pl-10 pr-4 text-xs text-text placeholder:text-text-muted transition-all"
          />
        </form>
      </div>

      {error && (
        <div className="bg-red-50 border border-red-200 text-red-700 text-xs p-4 rounded-xl">
          {error}
        </div>
      )}

      {/* Subjects Grid */}
      {loading ? (
        <div className="bg-surface border border-border/80 rounded-2xl p-12 text-center text-xs text-text-muted">
          Loading courses...
        </div>
      ) : subjects.length === 0 ? (
        <div className="bg-surface border border-border/80 rounded-2xl p-12 text-center text-xs text-text-muted space-y-3">
          <BookOpen className="w-8 h-8 text-text-muted mx-auto" />
          <p>No courses found matching your criteria.</p>
          <button
            onClick={() => setCreateModalOpen(true)}
            className="text-xs font-bold text-primary hover:underline"
          >
            + Create your first course
          </button>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          {subjects.map((subj) => (
            <div
              key={subj.id}
              className={`bg-surface border border-border/80 rounded-2xl p-6 shadow-xs hover:shadow-md transition-all flex flex-col justify-between ${
                subj.is_archived ? 'opacity-65' : ''
              }`}
            >
              <div>
                <div className="flex items-center justify-between mb-3">
                  <span className="text-[11px] font-bold text-primary bg-primary-soft px-2.5 py-0.5 rounded-full border border-primary/30">
                    {subj.grade_level_name || 'Standard'}
                  </span>
                  <button
                    onClick={() => openArchiveConfirm(subj)}
                    title={subj.is_archived ? 'Unarchive Course' : 'Archive Course'}
                    className="text-text-muted hover:text-text transition-colors cursor-pointer p-1"
                  >
                    <Archive className="w-4 h-4" />
                  </button>
                </div>

                <h3 className="font-bold text-text text-lg mb-1 leading-snug line-clamp-1">
                  {subj.title}
                </h3>
                <p className="text-xs text-text-muted font-medium mb-6 line-clamp-2 leading-relaxed">
                  {subj.description || 'No description provided.'}
                </p>
              </div>

              <div className="pt-4 border-t border-border flex items-center justify-between">
                <span className="text-[11px] font-semibold text-text-muted">
                  {subj.is_archived ? 'Archived' : 'Active'}
                </span>
                <button
                  onClick={() => navigate(`/teacher/courses/${subj.id}`)}
                  className="bg-primary hover:bg-primary-hover text-on-primary font-semibold py-2 px-4 rounded-xl text-xs transition-all cursor-pointer"
                >
                  Edit & Modules
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Pagination Footer */}
      <div className="p-4 bg-surface border border-border/80 rounded-2xl flex items-center justify-between text-xs text-text-muted shadow-xs">
        <div>
          Showing page <span className="font-bold text-text">{page}</span> of{' '}
          <span className="font-bold text-text">{totalPages}</span>
        </div>
        <div className="flex items-center gap-2">
          <button
            disabled={page <= 1}
            onClick={() => setPage(page - 1)}
            className="p-1.5 rounded-lg border border-border bg-surface hover:bg-bg disabled:opacity-40 disabled:cursor-not-allowed cursor-pointer"
          >
            <ChevronLeft className="w-4 h-4" />
          </button>
          <button
            disabled={page >= totalPages}
            onClick={() => setPage(page + 1)}
            className="p-1.5 rounded-lg border border-border bg-surface hover:bg-bg disabled:opacity-40 disabled:cursor-not-allowed cursor-pointer"
          >
            <ChevronRight className="w-4 h-4" />
          </button>
        </div>
      </div>

      {/* Create Subject Modal */}
      <CreateSubjectModal
        isOpen={createModalOpen}
        onClose={() => setCreateModalOpen(false)}
        onSuccess={fetchSubjects}
      />

      {/* Archive Confirmation Modal */}
      {archiveModalOpen && selectedSubject && (
        <div className="fixed inset-0 bg-surface/50 backdrop-blur-xs flex items-center justify-center p-4 z-50">
          <div className="bg-surface rounded-2xl p-6 max-w-md w-full shadow-2xl space-y-4">
            <div className="flex justify-between items-center border-b border-border pb-3">
              <h3 className="font-bold text-text text-sm flex items-center gap-2">
                <AlertTriangle className="w-4 h-4 text-amber-500" />
                <span>Confirm Archive Status</span>
              </h3>
              <button
                onClick={() => setArchiveModalOpen(false)}
                className="text-text-muted hover:text-text-muted cursor-pointer"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            <p className="text-xs text-text-muted leading-relaxed">
              Are you sure you want to{' '}
              <span className="font-bold">
                {selectedSubject.is_archived ? 'unarchive' : 'archive'}
              </span>{' '}
              the course <span className="font-bold text-text">"{selectedSubject.title}"</span>?
            </p>

            <div className="flex justify-end gap-3 pt-2">
              <button
                onClick={() => setArchiveModalOpen(false)}
                className="px-4 py-2 text-xs font-semibold text-text-muted hover:bg-bg rounded-lg cursor-pointer"
              >
                Cancel
              </button>
              <button
                disabled={archiving}
                onClick={handleToggleArchive}
                className="px-4 py-2 text-xs font-semibold text-on-primary bg-primary hover:bg-primary-hover rounded-lg cursor-pointer transition-all"
              >
                {archiving ? 'Updating...' : 'Confirm'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default CourseList;
