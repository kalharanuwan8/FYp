
export const StatCard = ({ label, value, subtext, icon: Icon, progress }) => {
  return (
    <div className="bg-surface border border-border/80 rounded-2xl p-5 shadow-sm hover:shadow-md transition-shadow">
      <div className="flex items-center justify-between mb-3">
        <span className="text-xs font-bold text-text-muted uppercase tracking-wider">
          {label}
        </span>
        {Icon && <Icon className="w-4 h-4 text-text-muted" />}
      </div>
      <div className="text-2xl md:text-3xl font-extrabold text-text tracking-tight mb-1">
        {value}
      </div>
      {progress !== undefined ? (
        <div className="w-full bg-bg rounded-full h-1.5 mt-3 overflow-hidden">
          <div
            className="bg-primary h-1.5 rounded-full transition-all duration-500"
            style={{ width: `${progress}%` }}
          ></div>
        </div>
      ) : (
        <div className="text-xs text-text-muted font-medium">
          {subtext}
        </div>
      )}
    </div>
  );
};

export default StatCard;
