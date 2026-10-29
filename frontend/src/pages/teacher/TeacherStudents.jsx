import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Users, ClipboardList } from 'lucide-react';
import { analyticsService } from '../../services/analyticsService';
import { Card, LoadingSpinner, ErrorBanner, Button } from '../../components/common';

export const TeacherStudents = () => {
  const navigate = useNavigate();
  const [students, setStudents] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    (async () => {
      try {
        const data = await analyticsService.listTeacherStudents();
        setStudents(data.students || []);
      } catch (err) {
        setError(err.response?.data?.error || 'Failed to load roster.');
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  if (loading) return <LoadingSpinner label="Loading roster…" />;

  return (
    <div className="space-y-6 max-w-4xl mx-auto font-sans">
      <div>
        <h1 className="text-2xl font-bold text-text tracking-tight flex items-center gap-2">
          <Users className="w-6 h-6 text-primary" />
          Student roster
        </h1>
        <p className="text-xs text-text-muted font-medium mt-1">
          Students enrolled in your subjects. Open DSM-5 indicators for a behavioural profile.
        </p>
      </div>

      {error && <ErrorBanner message={error} />}

      {students.length === 0 ? (
        <Card className="p-8 text-center text-text-muted text-sm space-y-2">
          <p>No enrolled students yet.</p>
          <Button type="button" variant="secondary" onClick={() => navigate('/teacher/courses')}>
            Open courses
          </Button>
        </Card>
      ) : (
        <ul className="space-y-2">
          {students.map((s) => (
            <li key={s.student_id}>
              <Card className="p-4 flex flex-wrap items-center justify-between gap-3">
                <div>
                  <p className="font-semibold text-text">{s.name}</p>
                  <p className="text-xs text-text-muted">{s.email}</p>
                </div>
                <Button
                  type="button"
                  size="sm"
                  onClick={() => navigate(`/teacher/students/${s.student_id}/analytics`)}
                >
                  <ClipboardList className="w-4 h-4 inline mr-1" />
                  DSM-5 indicators
                </Button>
              </Card>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
};

export default TeacherStudents;
