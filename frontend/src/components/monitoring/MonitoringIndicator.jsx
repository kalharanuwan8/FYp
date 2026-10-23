import { Activity, Camera, Lightbulb } from 'lucide-react';

/**
 * Shows live ML verdict + lighting tip during monitored sessions.
 */
export default function MonitoringIndicator({
  cameraActive = false,
  lastVerdict = 'FOCUSED',
  mlMode = null,
  confidence = null,
  sessionId = null,
}) {
  const focused = lastVerdict === 'FOCUSED';

  return (
    <div className="rounded-2xl border border-slate-200 bg-white/90 p-4 shadow-xs space-y-3">
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2 text-xs font-bold text-slate-800">
          <Activity className="w-4 h-4 text-[#3d7a9c]" />
          <span>Background ML Monitoring</span>
          {sessionId != null && (
            <span className="text-[10px] font-semibold text-slate-400">#{sessionId}</span>
          )}
        </div>
        <span
          className={`px-2.5 py-1 rounded-full text-[10px] font-extrabold tracking-wide ${
            focused
              ? 'bg-emerald-50 text-emerald-700 border border-emerald-200'
              : 'bg-amber-50 text-amber-800 border border-amber-200'
          }`}
        >
          {lastVerdict}
        </span>
      </div>

      <div className="flex flex-wrap items-center gap-3 text-[11px] text-slate-600">
        <span className="inline-flex items-center gap-1.5 font-semibold">
          <span
            className={`w-2 h-2 rounded-full ${
              cameraActive ? 'bg-emerald-500 animate-pulse' : 'bg-amber-500'
            }`}
          />
          <Camera className="w-3.5 h-3.5" />
          {cameraActive ? 'Camera on' : 'Camera off'}
        </span>
        {mlMode && (
          <span className="font-semibold text-slate-500">
            Model: <strong className="text-slate-700">{mlMode}</strong>
          </span>
        )}
        {typeof confidence === 'number' && (
          <span className="font-semibold text-slate-500">
            Conf: {(confidence * 100).toFixed(0)}%
          </span>
        )}
      </div>

      <p className="flex items-start gap-2 text-[11px] text-slate-500 leading-relaxed">
        <Lightbulb className="w-3.5 h-3.5 text-amber-500 shrink-0 mt-0.5" />
        <span>
          Face the camera with light in front of you (not behind). Keep your face
          visible so the distraction model can run in the background.
        </span>
      </p>
    </div>
  );
}
