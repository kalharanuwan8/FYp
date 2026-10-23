
export const SystemLogs = () => {
  return (
    <div className="space-y-4 max-w-7xl mx-auto">
      <h1 className="text-2xl font-bold text-text tracking-tight">System Logs</h1>
      <p className="text-xs text-text-muted font-medium">Audit logs and system activity history.</p>
      <div className="bg-surface border border-border/80 rounded-2xl p-8 text-center text-text-muted text-xs">
        System logs are not available in Luma yet. This page is kept so the route does not break; no log data is collected or shown here.
      </div>
    </div>
  );
};

export default SystemLogs;
