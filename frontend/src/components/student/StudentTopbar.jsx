import { useAuth } from '../../hooks/useAuth';
import XPChip from '../common/XPChip';
import StreakChip from '../common/StreakChip';

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
    <header className="sticky top-0 z-30 bg-bg/90 backdrop-blur-md border-b border-border px-4 md:px-8 py-3">
      <div className="flex items-center justify-between gap-4 flex-wrap">
        <div>
          <p className="font-display text-lg md:text-xl font-bold text-text">
            {greeting}, {firstName}
          </p>
          <p className="text-sm text-text-muted">Ready for a calm focus session?</p>
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
            className="w-11 h-11 rounded-full bg-primary text-on-primary font-display font-bold flex items-center justify-center text-sm"
            aria-hidden="true"
          >
            {initials}
          </div>
        </div>
      </div>
    </header>
  );
}
