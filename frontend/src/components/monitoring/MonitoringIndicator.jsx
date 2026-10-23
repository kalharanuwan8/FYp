import { Activity, Camera, Lightbulb } from 'lucide-react';

/**
 * Shows live ML verdict + lighting tip during monitored sessions.
 * Uses semantic theme tokens so colour tracks sage / warm / pale-blue / calm-dark.
 */
export default function MonitoringIndicator({
  cameraActive = false,
  lastVerdict = 'FOCUSED',
  mlMode = null,
  confidence = null,
  sessionId = null,
}) {
  const focused = lastVerdict === 'FOCUSED';
  const unknown = lastVerdict === 'UNKNOWN';

  return (
    <div className="rounded-2xl border border-border bg-surface p-4 shadow-soft space-y-3">
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2 text-xs font-bold text-text">
          <Activity className="w-4 h-4 text-primary" aria-hidden="true" />
          <span>Background ML Monitoring</span>
          {sessionId != null && (
            <span className="text-[10px] font-semibold text-text-muted">#{sessionId}</span>
          )}
        </div>
        <span
          className={`px-2.5 py-1 rounded-full text-[10px] font-extrabold tracking-wide border ${
            unknown
              ? 'bg-bg text-text-muted border-border'
              : focused
                ? 'bg-primary-soft text-success border-success/30'
                : 'bg-warning/15 text-warning border-warning/30'
          }`}
        >
          {lastVerdict}
        </span>
      </div>

      <div className="flex flex-wrap items-center gap-3 text-[11px] text-text-muted">
        <span className="inline-flex items-center gap-1.5 font-semibold">
          <span
            className={`w-2 h-2 rounded-full ${cameraActive ? 'bg-success' : 'bg-warning'}`}
            aria-hidden="true"
          />
          <Camera className="w-3.5 h-3.5" aria-hidden="true" />
          {cameraActive ? 'Camera on' : 'Camera off'}
        </span>
        {mlMode && (
          <span className="font-semibold">
            Model: <strong className="text-text">{mlMode}</strong>
          </span>
        )}
        {!unknown && typeof confidence === 'number' && (
          <span className="font-semibold">Conf: {(confidence * 100).toFixed(0)}%</span>
        )}
        {unknown && (
          <span className="font-semibold text-text-muted">No usable observation</span>
        )}
      </div>

      <p className="flex items-start gap-2 text-[11px] text-text-muted leading-relaxed">
        <Lightbulb className="w-3.5 h-3.5 text-warning shrink-0 mt-0.5" aria-hidden="true" />
        <span>
          Face the camera with light in front of you (not behind). Keep your face visible so the
          distraction model can run in the background.
        </span>
      </p>
    </div>
  );
}
