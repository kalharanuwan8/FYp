import { useEffect, useState } from 'react';
import { Camera, Square } from 'lucide-react';
import { sessionService } from '../../services/sessionService';
import { Button, Card } from '../common';

function formatRunning(seconds) {
  const mins = Math.floor((seconds || 0) / 60);
  if (mins < 1) return 'less than a minute';
  if (mins < 60) return `${mins} min`;
  const hours = Math.floor(mins / 60);
  return `${hours} h ${mins % 60} min`;
}

/**
 * Shows monitoring sessions that are still open (e.g. the lesson tab was
 * closed without ending the session) and lets the student stop them.
 */
export default function ActiveSessionBanner({ onStopped }) {
  const [sessions, setSessions] = useState([]);
  const [stopping, setStopping] = useState(false);
  const [message, setMessage] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const data = await sessionService.getActiveSessions();
        if (!cancelled) setSessions(data.sessions || []);
      } catch {
        /* banner is optional — stay hidden */
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const stopAll = async () => {
    setStopping(true);
    setError(null);
    try {
      const data = await sessionService.stopActiveSessions();
      setSessions([]);
      setMessage(
        data.stopped_count === 1
          ? 'Monitoring stopped. Your camera is no longer in use.'
          : `${data.stopped_count} monitoring sessions stopped.`
      );
      onStopped?.(data);
    } catch (err) {
      setError(err.response?.data?.error || 'Could not stop monitoring. Please try again.');
    } finally {
      setStopping(false);
    }
  };

  if (message && sessions.length === 0) {
    return (
      <p role="status" className="text-sm font-semibold text-success">
        {message}
      </p>
    );
  }
  if (sessions.length === 0) return null;

  const latest = sessions[0];
  const where = latest.module_title
    ? `${latest.module_title}${latest.subject_title ? ` · ${latest.subject_title}` : ''}`
    : 'a lesson';

  return (
    <Card className="p-4 md:p-5 border-attention/40" role="region" aria-label="Active monitoring session">
      <div className="flex flex-col sm:flex-row sm:items-center gap-4">
        <span
          className="w-11 h-11 rounded-2xl bg-attention/15 text-attention flex items-center justify-center shrink-0"
          aria-hidden="true"
        >
          <Camera className="w-5 h-5" />
        </span>
        <div className="flex-1 min-w-0">
          <p className="font-display font-bold text-text">
            {sessions.length === 1
              ? 'A monitoring session is still running'
              : `${sessions.length} monitoring sessions are still running`}
          </p>
          <p className="text-sm text-text-muted">
            Started on {where}, running for {formatRunning(latest.running_seconds)}.
            Stop it if you have finished studying.
          </p>
          {error && <p className="text-sm text-attention mt-1">{error}</p>}
        </div>
        <Button variant="attention" onClick={stopAll} disabled={stopping} className="shrink-0">
          <Square className="w-4 h-4" aria-hidden="true" />
          {stopping ? 'Stopping…' : 'Stop monitoring'}
        </Button>
      </div>
    </Card>
  );
}
