import { useAuth } from '../../hooks/useAuth';

export default function Topbar() {
  const { user } = useAuth();
  const adminName = user
    ? `${user.first_name || ''} ${user.last_name || ''}`.trim() || 'Admin'
    : 'Admin';

  return (
    <header className="h-16 bg-surface border-b border-border/80 px-8 flex items-center justify-end">
      <div className="flex items-center gap-3">
        <div className="w-8 h-8 rounded-full bg-primary text-on-primary flex items-center justify-center font-bold text-xs shadow-sm">
          {adminName.charAt(0).toUpperCase()}
        </div>
        <span className="text-xs font-semibold text-text">{adminName}</span>
      </div>
    </header>
  );
}
