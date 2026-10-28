import { useState, useEffect, useCallback } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { Search, BookOpen, Plus, ChevronLeft, ChevronRight } from 'lucide-react';
import { courseService } from '../../services/courseService';
import { Button, Card, EmptyState, LoadingSpinner, ErrorBanner } from '../../components/common';
import { accentForId } from '../../utils/subjectAccents';

export default function CourseBrowser() {
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const tab = searchParams.get('tab') === 'explore' ? 'explore' : 'mine';

  const [subjects, setSubjects] = useState([]);
  const [enrollments, setEnrollments] = useState([]);
  const [enrolledSubjectIds, setEnrolledSubjectIds] = useState(new Set());
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);
  const [error, setError] = useState(null);
  const [actionLoading, setActionLoading] = useState(null);

  const setTab = (next) => {
    setSearchParams(next === 'explore' ? { tab: 'explore' } : {});
  };

  const fetchEnrolled = async () => {
    try {
      const data = await courseService.listMyEnrollments();
      const list = data.enrollments || [];
      setEnrollments(list);
      setEnrolledSubjectIds(new Set(list.map((s) => s.id)));
    } catch (err) {
      console.error(err);
    }
  };

  const fetchSubjectsList = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await courseService.getSubjects({ search, page, per_page: 9 });
      setSubjects(data.subjects || []);
      setTotalPages(data.pages || 1);
    } catch (err) {
      setError(err.response?.data?.error || 'Failed to load subjects');
    } finally {
      setLoading(false);
    }
  }, [search, page]);

  useEffect(() => {
    fetchEnrolled();
  }, []);

  useEffect(() => {
    if (tab === 'explore') fetchSubjectsList();
    else {
      setLoading(true);
      fetchEnrolled().finally(() => setLoading(false));
    }
  }, [tab, fetchSubjectsList]);

  const handleEnroll = async (subjectId) => {
    setActionLoading(subjectId);
    setError(null);
    try {
      await courseService.enroll(subjectId);
      await fetchEnrolled();
      navigate(`/student/subjects/${subjectId}`);
    } catch (err) {
      setError(err.response?.data?.error || 'Could not enrol. Try again.');
    } finally {
      setActionLoading(null);
    }
  };

  const list = tab === 'mine' ? enrollments : subjects;

  return (
    <div className="space-y-6 max-w-5xl mx-auto animate-fade-in">
      <div>
        <h1 className="font-display text-2xl font-bold text-text">My Subjects</h1>
        <p className="text-text-muted text-sm mt-1">Your courses and new ones to explore.</p>
      </div>

      <div
        className="flex gap-1 p-1 rounded-2xl bg-surface border border-border w-fit"
        role="tablist"
        aria-label="Subject views"
      >
        {[
          { id: 'mine', label: 'Enrolled' },
          { id: 'explore', label: 'Explore' },
        ].map((t) => (
          <button
            key={t.id}
            type="button"
            role="tab"
            aria-selected={tab === t.id}
            onClick={() => setTab(t.id)}
            className={`min-h-11 px-5 rounded-xl text-sm font-semibold cursor-pointer transition-colors ${
              tab === t.id ? 'bg-primary text-on-primary' : 'text-text-muted hover:text-text'
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {tab === 'explore' && (
        <div className="relative max-w-md">
          <Search className="w-4 h-4 text-text-muted absolute left-3 top-1/2 -translate-y-1/2" />
          <input
            type="search"
            value={search}
            onChange={(e) => {
              setSearch(e.target.value);
              setPage(1);
            }}
            placeholder="Search subjects…"
            className="w-full min-h-11 bg-surface border border-border rounded-2xl pl-10 pr-4 text-sm text-text"
          />
        </div>
      )}

      {error && <ErrorBanner message={error} onDismiss={() => setError(null)} />}

      {loading ? (
        <LoadingSpinner />
      ) : list.length === 0 ? (
        <Card>
          <EmptyState
            icon={BookOpen}
            title={tab === 'mine' ? 'Nothing enrolled yet' : 'No matching subjects'}
            description={
              tab === 'mine'
                ? 'Switch to Explore to find a course for your grade.'
                : 'Try a different search, or check back later.'
            }
            actionLabel={tab === 'mine' ? 'Explore subjects' : undefined}
            onAction={tab === 'mine' ? () => setTab('explore') : undefined}
          />
        </Card>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {list.map((subject) => {
            const accent = accentForId(subject.id);
            const isEnrolled = enrolledSubjectIds.has(subject.id);
            return (
              <Card
                key={subject.id}
                className="p-5 flex flex-col gap-4"
                style={{ borderTop: `3px solid ${accent.color}` }}
              >
                <div className="space-y-2 flex-1">
                  <p className="text-xs font-semibold" style={{ color: accent.color }}>
                    {subject.grade_level_name || 'Subject'}
                  </p>
                  <h3 className="font-display font-bold text-text">{subject.title}</h3>
                  <p className="text-sm text-text-muted line-clamp-3">
                    {subject.description || 'Open to see the learning path.'}
                  </p>
                </div>
                <div className="flex gap-2">
                  <Button
                    variant="secondary"
                    className="flex-1"
                    onClick={() => navigate(`/student/subjects/${subject.id}`)}
                  >
                    Open
                  </Button>
                  {tab === 'explore' && !isEnrolled && (
                    <Button
                      className="flex-1"
                      disabled={actionLoading === subject.id}
                      onClick={() => handleEnroll(subject.id)}
                    >
                      <Plus className="w-4 h-4" />
                      {actionLoading === subject.id ? '…' : 'Enrol'}
                    </Button>
                  )}
                </div>
              </Card>
            );
          })}
        </div>
      )}

      {tab === 'explore' && totalPages > 1 && (
        <div className="flex items-center justify-between text-sm text-text-muted">
          <span>
            Page {page} of {totalPages}
          </span>
          <div className="flex gap-2">
            <Button
              variant="secondary"
              size="sm"
              disabled={page <= 1}
              onClick={() => setPage((p) => Math.max(1, p - 1))}
            >
              <ChevronLeft className="w-4 h-4" /> Previous
            </Button>
            <Button
              variant="secondary"
              size="sm"
              disabled={page >= totalPages}
              onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
            >
              Next <ChevronRight className="w-4 h-4" />
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
