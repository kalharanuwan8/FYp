import { useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { ArrowLeft, ClipboardList } from 'lucide-react';
import { analyticsService } from '../../services/analyticsService';
import { Card, LoadingSpinner, ErrorBanner, Button } from '../../components/common';

/**
 * Teacher view: DSM-5 inattention behavioural proxies for one student.
 * Not a clinical diagnosis — per-indicator counts only.
 */
export default function StudentAnalytics() {
  const { studentId } = useParams();
  const navigate = useNavigate();
  const [students, setStudents] = useState([]);
  const [selectedId, setSelectedId] = useState(studentId ? Number(studentId) : null);
  const [profile, setProfile] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    (async () => {
      try {
        const data = await analyticsService.listTeacherStudents();
        setStudents(data.students || []);
        if (!selectedId && data.students?.length) {
          setSelectedId(data.students[0].student_id);
        }
      } catch (err) {
        setError(err.response?.data?.error || 'Failed to load students.');
      } finally {
        setLoading(false);
      }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (!selectedId) {
      setProfile(null);
      return;
    }
    let cancelled = false;
    (async () => {
      setError(null);
      try {
        const data = await analyticsService.getTeacherStudentDsmProfile(selectedId, 7);
        if (!cancelled) setProfile(data);
      } catch (err) {
        if (!cancelled) {
          setProfile(null);
          setError(err.response?.data?.error || 'Failed to load DSM profile.');
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [selectedId]);

  if (loading) return <LoadingSpinner label="Loading student indicators…" />;

  return (
    <div className="space-y-6 max-w-4xl mx-auto animate-fade-in">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <button
            type="button"
            onClick={() => navigate('/teacher/students')}
            className="text-sm font-semibold text-primary flex items-center gap-1.5 min-h-11 mb-1"
          >
            <ArrowLeft className="w-4 h-4" /> Students
          </button>
          <h1 className="font-display text-2xl font-bold text-text flex items-center gap-2">
            <ClipboardList className="w-6 h-6 text-primary" />
            DSM-5 inattention indicators
          </h1>
          <p className="text-sm text-text-muted mt-1">
            Behavioural proxies for the last 7 days — not a clinical diagnosis.
          </p>
        </div>
        <label className="text-sm text-text-muted">
          Student
          <select
            className="ml-2 rounded-xl border border-border bg-surface px-3 py-2 text-text font-semibold"
            value={selectedId || ''}
            onChange={(e) => {
              const id = Number(e.target.value);
              setSelectedId(id);
              navigate(`/teacher/students/${id}/analytics`, { replace: true });
            }}
          >
            {students.length === 0 && <option value="">No enrolled students</option>}
            {students.map((s) => (
              <option key={s.student_id} value={s.student_id}>
                {s.name}
              </option>
            ))}
          </select>
        </label>
      </div>

      {error && <ErrorBanner message={error} />}

      {profile && (
        <Card className="p-5 md:p-6 space-y-4">
          <div>
            <h2 className="font-display font-bold text-text">
              {profile.student_name || `Student #${profile.student_id}`}
            </h2>
            <p className="text-xs text-text-muted mt-1">{profile.disclaimer}</p>
          </div>
          <ul className="space-y-3">
            {(profile.indicators || []).map((ind) => (
              <li
                key={ind.id}
                className="rounded-2xl border border-border bg-bg px-4 py-3 flex flex-wrap items-start justify-between gap-2"
              >
                <div className="min-w-0 flex-1">
                  <p className="font-semibold text-text text-sm">{ind.label}</p>
                  <p className="text-xs text-text-muted mt-1">
                    {ind.id === 'dsm2_external' && ind.evidence
                      ? `Camera episodes: ${ind.evidence.camera_distracted_episodes ?? 0} · Noise notices: ${ind.evidence.noise_notices ?? 0}`
                      : Array.isArray(ind.evidence) && ind.evidence.length
                        ? `${ind.evidence.length} sample evidence row(s) in window`
                        : 'No events in this window'}
                  </p>
                </div>
                <span className="text-lg font-display font-bold text-primary tabular-nums">
                  {ind.count}
                </span>
              </li>
            ))}
          </ul>
        </Card>
      )}

      {!profile && !error && selectedId && (
        <Card className="p-6 text-sm text-text-muted">Loading profile…</Card>
      )}

      {!selectedId && (
        <Card className="p-6 text-sm text-text-muted space-y-3">
          <p>No students enrolled in your subjects yet.</p>
          <Button type="button" variant="secondary" onClick={() => navigate('/teacher/courses')}>
            Open courses
          </Button>
        </Card>
      )}
    </div>
  );
}
