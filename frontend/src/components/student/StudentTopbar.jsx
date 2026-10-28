import { useAuth } from '../../hooks/useAuth';
import XPChip from '../common/XPChip';
import StreakChip from '../common/StreakChip';
import StatusBadge from '../common/StatusBadge';

export default function StudentTopbar({ profile, progress }) {
  const { user } = useAuth();
  const firstName = profile?.first_name || user?.first_name || 'there';
  const hour = new Date().getHours();
  const greeting =
    hour < 12 ? 'Good morning' : hour < 17 ? 'Good afternoon' : 'Good evening';

  const initials = `${(profile?.first_name || user?.first_name || 'S')[0]}${(
    profile?.last_name ||
    user?.last_name ||
    ''
  )[0] || ''}`.toUpperCase();

  return (
    <header className="sticky top-0 z-30 bg-bg/90 backdrop-blur-sm border-b border-border px-4 md:px-8 py-3.5">
      <div className="flex items-center justify-between gap-4 flex-wrap">
        <div className="flex items-center gap-2.5 flex-wrap min-w-0">
          <p className="font-display text-lg md:text-xl font-bold text-text truncate">
            {greeting}, {firstName}
          </p>
          <StatusBadge tone="primary">Student</StatusBadge>
        </div>
        <div className="flex items-center gap-2 flex-wrap">
          {progress ? (
            <>
              <StreakChip streak={progress?.current_streak || 0} />
              <XPChip xp={progress?.xp || 0} />
            </>
          ) : (
            <span className="text-sm text-text-muted" role="status">
              Loading your progress…
            </span>
          )}
          <div
            className="w-11 h-11 rounded-full bg-primary text-on-primary font-display font-bold flex items-center justify-center text-sm shadow-soft ring-2 ring-primary-soft"
            aria-hidden="true"
          >
            {initials}
          </div>
        </div>
      </div>
    </header>
  );
}
