import { useState, useEffect } from 'react';
import { useNavigate, useOutletContext } from 'react-router-dom';
import {
  BookOpen,
  ArrowRight,
  FileText,
  Play,
  Sparkles,
} from 'lucide-react';
import { courseService } from '../../services/courseService';
import { analyticsService } from '../../services/analyticsService';
import {
  Button,
  Card,
  ProgressRing,
  StatusBadge,
  EmptyState,
  LoadingSpinner,
  ErrorBanner,
} from '../../components/common';
import { accentForId } from '../../utils/subjectAccents';
import ActiveSessionBanner from '../../components/student/ActiveSessionBanner';

const QUICK_TIMERS = [15, 20, 25];

export default function StudentDashboard() {
  const navigate = useNavigate();
  const { progress, refreshProgress } = useOutletContext() || {};

  const [enrollments, setEnrollments] = useState([]);
  const [subjectStats, setSubjectStats] = useState({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const goal = progress?.daily_goal_minutes || 20;
  const todayMins = progress?.today_focus_minutes || 0;
  const [selectedTimer, setSelectedTimer] = useState(goal);

  useEffect(() => {
    setSelectedTimer(goal);
  }, [goal]);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      setLoading(true);
      setError(null);
      try {
        const [data, analytics] = await Promise.all([
          courseService.listMyEnrollments(),
          analyticsService.getStudentAnalytics().catch(() => null),
        ]);
        if (cancelled) return;
        setEnrollments(data.enrollments || []);
        const byId = {};
        (analytics?.subject_progress || []).forEach((s) => {
          byId[s.subject_id] = s;
        });
        setSubjectStats(byId);
        refreshProgress?.();
      } catch (err) {
        if (!cancelled) {
          setError(err.response?.data?.error || 'Failed to load your subjects.');
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [refreshProgress]);

  const continueCourse = enrollments[0];
  const continueAccent = continueCourse ? accentForId(continueCourse.id) : null;
  const continueStats = continueCourse ? subjectStats[continueCourse.id] : null;
  const focusPct =
    continueStats?.avg_focus_percentage != null
      ? Math.round(continueStats.avg_focus_percentage)
      : null;
  const sessionsLeftHint = Math.max(0, goal - todayMins);

  const openContinue = () => {
    if (continueCourse) {
      navigate(`/student/subjects/${continueCourse.id}`);
    } else {
      navigate('/student/courses?tab=explore');
    }
  };

  return (
    <div className="space-y-6 max-w-5xl mx-auto animate-fade-in">
      <ActiveSessionBanner onStopped={() => refreshProgress?.()} />

      {/* Continue learning — primary next action */}
      <Card
        className="p-6 md:p-8 space-y-5 max-w-none overflow-hidden relative"
        style={
          continueAccent
            ? { borderTop: `3px solid ${continueAccent.color}` }
            : undefined
        }
      >
        <div className="space-y-5 max-w-2xl">
          <div className="flex flex-wrap items-center gap-2">
            <p className="text-sm font-semibold text-primary inline-flex items-center gap-2">
              <Sparkles className="w-4 h-4" aria-hidden="true" />
              Continue learning
            </p>
            {continueCourse?.grade_level_name && (
              <StatusBadge tone="muted">{continueCourse.grade_level_name}</StatusBadge>
            )}
          </div>

          {continueCourse ? (
            <>
              <div>
                <h2 className="font-display text-2xl md:text-3xl font-bold text-text">
                  {continueCourse.title}
                </h2>
                {continueCourse.description && (
                  <p className="text-text-muted mt-2 line-clamp-2 prose-narrow">
                    {continueCourse.description}
                  </p>
                )}
              </div>

              {focusPct != null && (
                <div className="space-y-2">
                  <div className="flex items-end justify-between gap-3">
                    <p className="text-sm text-text-muted">
                      Average focus across{' '}
                      {continueStats.sessions_count} session
                      {continueStats.sessions_count === 1 ? '' : 's'}
                    </p>
                    <p className="font-display text-xl font-bold text-primary tabular-nums">
                      {focusPct}%
                    </p>
                  </div>
                  <div
                    className="h-2.5 rounded-full bg-bg overflow-hidden"
                    role="progressbar"
                    aria-valuenow={focusPct}
                    aria-valuemin={0}
                    aria-valuemax={100}
                    aria-label="Average focus percentage"
                  >
                    <div
                      className="h-full rounded-full bg-primary transition-[width] duration-500"
                      style={{ width: `${focusPct}%` }}
                    />
                  </div>
                </div>
              )}

              <div className="flex flex-wrap items-center gap-3">
                <Button size="lg" onClick={openContinue}>
                  Continue lesson
                  <ArrowRight className="w-5 h-5" aria-hidden="true" />
                </Button>
                <Button
                  variant="secondary"
                  size="lg"
                  onClick={() => navigate(`/student/subjects/${continueCourse.id}`)}
                >
                  <FileText className="w-4 h-4" aria-hidden="true" />
                  Open subject
                </Button>
                <button
                  type="button"
                  onClick={() => navigate('/student/courses')}
                  className="text-sm font-semibold text-primary min-h-11 px-2 inline-flex items-center gap-1 cursor-pointer hover:underline"
                >
                  Browse all subjects
                  <ArrowRight className="w-4 h-4" aria-hidden="true" />
                </button>
              </div>

              <div className="flex flex-wrap gap-x-4 gap-y-1 text-sm text-text-muted">
                <span>
                  {continueStats?.sessions_count != null
                    ? `${continueStats.sessions_count} focus session${
                        continueStats.sessions_count === 1 ? '' : 's'
                      }`
                    : 'No focus sessions yet'}
                </span>
                {sessionsLeftHint > 0 && (
                  <span>Est. {sessionsLeftHint} min to today&apos;s goal</span>
                )}
              </div>
            </>
          ) : (
            <>
              <h2 className="font-display text-2xl md:text-3xl font-bold text-text">
                Find your first subject
              </h2>
              <p className="text-text-muted prose-narrow">
                Explore subjects for your grade and enrol — your next lesson will
                show up here.
              </p>
              <Button size="lg" onClick={() => navigate('/student/courses?tab=explore')}>
                Explore subjects
                <ArrowRight className="w-5 h-5" aria-hidden="true" />
              </Button>
            </>
          )}
        </div>
      </Card>

      {/* Today's focus goal + quick timers */}
      <Card className="p-5 md:p-6">
        <div className="flex flex-col sm:flex-row sm:items-center gap-5">
          <ProgressRing
            value={todayMins}
            max={goal}
            size={88}
            stroke={9}
            color="var(--primary)"
            label="Daily focus goal"
          >
            <span className="font-display font-bold text-sm text-text leading-tight">
              {todayMins}m
            </span>
            <span className="text-[10px] text-text-muted leading-tight">done</span>
          </ProgressRing>

          <div className="flex-1 min-w-0 space-y-3">
            <div>
              <h2 className="font-display font-bold text-text text-lg">
                Today&apos;s focus goal
              </h2>
              <p className="text-sm text-text-muted">
                Target {goal} min
                {todayMins >= goal
                  ? ' — goal reached. Nice work.'
                  : `. ${Math.max(0, goal - todayMins)} min left.`}
              </p>
            </div>

            <div
              className="flex flex-wrap items-center gap-2"
              role="group"
              aria-label="Quick focus timer"
            >
              {QUICK_TIMERS.map((mins) => {
                const isActive = selectedTimer === mins;
                const isGoal = mins === goal;
                return (
                  <button
                    key={mins}
                    type="button"
                    onClick={() => setSelectedTimer(mins)}
                    className={`min-h-10 px-3.5 rounded-2xl text-sm font-semibold border transition-all cursor-pointer ${
                      isActive
                        ? 'bg-primary text-on-primary border-transparent shadow-soft'
                        : 'bg-bg text-text-muted border-border hover:border-primary hover:text-primary'
                    }`}
                  >
                    {mins}m{isGoal ? ' (Goal)' : ''}
                  </button>
                );
              })}
            </div>
          </div>

          <Button
            size="lg"
            className="shrink-0 w-full sm:w-auto"
            onClick={openContinue}
          >
            <Play className="w-4 h-4" aria-hidden="true" />
            Start session
          </Button>
        </div>
      </Card>

      {/* Enrolled subjects */}
      <div className="space-y-4">
        <div className="flex items-center justify-between gap-3">
          <h2 className="font-display text-xl font-bold text-text">
            Your enrolled subjects
          </h2>
          <button
            type="button"
            onClick={() => navigate('/student/courses')}
            className="text-sm font-semibold text-primary min-h-11 px-2 cursor-pointer hover:underline"
          >
            See all
          </button>
        </div>

        {error && <ErrorBanner message={error} onDismiss={() => setError(null)} />}
        {loading ? (
          <LoadingSpinner label="Loading subjects…" />
        ) : enrollments.length === 0 ? (
          <Card>
            <EmptyState
              icon={BookOpen}
              title="No subjects yet"
              description="Explore courses for your grade and enrol with one tap."
              actionLabel="Explore subjects"
              onAction={() => navigate('/student/courses?tab=explore')}
            />
          </Card>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
            {enrollments.map((course) => {
              const accent = accentForId(course.id);
              const stats = subjectStats[course.id];
              const sessionCount = stats?.sessions_count ?? 0;
              return (
                <Card
                  as="button"
                  type="button"
                  key={course.id}
                  className="p-5 flex flex-col gap-3 hover:shadow-lift transition-shadow cursor-pointer text-left w-full group"
                  onClick={() => navigate(`/student/subjects/${course.id}`)}
                >
                  <div className="flex items-start justify-between gap-2">
                    <span
                      className="w-11 h-11 rounded-2xl flex items-center justify-center shrink-0"
                      style={{ background: accent.soft, color: accent.color }}
                      aria-hidden="true"
                    >
                      <BookOpen className="w-5 h-5" />
                    </span>
                    <StatusBadge tone="muted">
                      {sessionCount} session{sessionCount === 1 ? '' : 's'}
                    </StatusBadge>
                  </div>
                  <div className="min-w-0 space-y-1 flex-1">
                    <p className="font-display font-bold text-text group-hover:text-primary transition-colors line-clamp-2">
                      {course.title}
                    </p>
                    <p className="text-sm text-text-muted line-clamp-2">
                      {course.description ||
                        (stats?.avg_focus_percentage != null
                          ? `${Math.round(stats.avg_focus_percentage)}% average focus`
                          : course.grade_level_name || 'Open to see your lessons')}
                    </p>
                  </div>
                </Card>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
