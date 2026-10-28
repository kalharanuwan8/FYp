import { ShieldCheck } from 'lucide-react';

/**
 * Simple consent reminder shown before / during monitored sessions.
 * Guardian consent is enforced by the backend on session start.
 */
export default function ConsentGate({ children, acknowledged = true }) {
  if (!acknowledged) {
    return (
      <div className="rounded-2xl border border-warning/40 bg-warning/10 p-4 text-xs text-text space-y-2">
        <div className="flex items-center gap-2 font-bold text-text">
          <ShieldCheck className="w-4 h-4 text-warning" aria-hidden="true" />
          <span>Monitoring consent</span>
        </div>
        <p className="leading-relaxed text-text-muted">
          Camera monitoring requires guardian consent on your account. Ask an admin to enable
          consent before starting a monitored session.
        </p>
        <p className="leading-relaxed text-text-muted">
          Monitored sessions also measure how loud the room is, on this device. Only the loudness
          level is sent — the microphone is never recorded or uploaded.
        </p>
      </div>
    );
  }
  return children || null;
}
