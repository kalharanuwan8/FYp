import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  describeDecision,
  describeNumbers,
  describeObservation,
  explainFrame,
  frameStrip,
  toCsv,
  toJsonl,
} from '../../utils/evalExplain';

/**
 * PLAN 7 — evaluation terminal overlay.
 *
 * Available when the backend runs with DEMO_MODE or the page URL has `?eval=1`.
 * Toggle with the backtick key (`) or the >_ button; `M` inserts a ground-truth
 * marker. Shows, per heartbeat, what the model saw, how it decided and what the
 * intervention engine did — in plain language, with numbers on a second line.
 */

const VERDICT_STYLE = {
  FOCUSED: { color: '#4ade80', label: 'FOCUSED   ' },
  DISTRACTED: { color: '#fbbf24', label: 'DISTRACTED' },
  UNKNOWN: { color: '#94a3b8', label: 'UNKNOWN   ' },
};

const hhmmss = (ts) => {
  const d = new Date(ts);
  const p = (n, w = 2) => String(n).padStart(w, '0');
  return `${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}.${String(
    Math.floor(d.getMilliseconds() / 100)
  )}`;
};

function download(name, text, type) {
  const blob = new Blob([text], { type });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = name;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

function BeatLine({ entry, expanded, onToggle }) {
  const res = entry.res || {};
  const vs = VERDICT_STYLE[String(res.verdict || 'UNKNOWN').toUpperCase()] || VERDICT_STYLE.UNKNOWN;
  const obs = describeObservation(res);
  const numbers = describeNumbers(res);
  const decision = describeDecision(res);
  const fired = res.intervention_debug?.action === 'fired' || res.intervention_triggered;
  const strip = frameStrip(res.frames_debug);
  const sent = entry.sent || {};
  const t0 = res.frames_debug?.[0]?.t;

  return (
    <div className="py-0.5 border-b border-white/5">
      <button
        type="button"
        onClick={onToggle}
        className="w-full text-left cursor-pointer hover:bg-white/5 rounded px-1"
        aria-expanded={expanded}
      >
        <div className="whitespace-pre-wrap break-words">
          <span className="text-slate-500">{hhmmss(entry.ts)} </span>
          <span style={{ color: vs.color }} className="font-bold">
            {vs.label}
          </span>
          {strip && (
            <span className="text-slate-400" title="frames: ● off-screen ○ on-screen · unknown">
              {' '}
              [{strip}]
            </span>
          )}
          <span className="text-slate-100"> {obs.length ? obs.join(' · ') : '—'}</span>
        </div>
        {numbers && <div className="pl-[11ch] text-slate-500 whitespace-pre-wrap break-words">{numbers}</div>}
        <div
          className={`pl-[11ch] whitespace-pre-wrap break-words ${
            fired ? 'text-cyan-300 font-bold' : 'text-slate-400'
          }`}
        >
          → {decision}
          {sent.content_state && sent.content_state !== 'none' && (
            <span className="text-slate-500">
              {' '}
              · video {sent.content_state}
              {sent.pause_reason && sent.content_state === 'paused' ? ` (${sent.pause_reason})` : ''}
            </span>
          )}
        </div>
      </button>
      {expanded && (
        <div className="pl-[11ch] pr-1 py-1 text-slate-300 flex gap-3 items-start">
          <div className="flex-1 min-w-0">
            {(res.frames_debug || []).length === 0 && (
              <div className="text-slate-500">no per-frame data (tab hidden, calibration, or legacy path)</div>
            )}
            {(res.frames_debug || []).map((f, i) => (
              <div key={i} className={f.on_screen === false ? 'text-amber-300' : ''}>
                frame {i + 1}: {explainFrame(f, t0)}
                {(typeof f.look_h === 'number' || typeof f.look_v === 'number') && (
                  <span className="text-slate-400">
                    {' · '}
                    {typeof f.look_h === 'number' ? `look_h ${f.look_h.toFixed(2)}` : ''}
                    {typeof f.look_h === 'number' && typeof f.look_v === 'number' ? ' ' : ''}
                    {typeof f.look_v === 'number' ? `look_v ${f.look_v.toFixed(2)}` : ''}
                  </span>
                )}
              </div>
            ))}
            <div className="text-slate-500 mt-1">
              sent {sent.n_frames ?? 0} frames · noise{' '}
              {typeof sent.noise_dbfs === 'number' ? `${sent.noise_dbfs.toFixed(1)} dBFS` : '—'}
              {sent.hidden_ms ? ` · hidden ${Math.round(sent.hidden_ms / 100) / 10}s` : ''}
              {sent.blurred_ms ? ` · blurred ${Math.round(sent.blurred_ms / 100) / 10}s` : ''}
            </div>
          </div>
          {entry.thumb && (
            <img
              src={entry.thumb}
              alt="Last frame sent with this distracted heartbeat"
              className="w-28 rounded border border-white/20 shrink-0"
            />
          )}
        </div>
      )}
    </div>
  );
}

export default function EvalTerminal({
  enabled,
  autoOpen = false,
  entries = [],
  onMark,
  onClear,
  onGazeTest,
}) {
  const [open, setOpen] = useState(autoOpen);
  const [follow, setFollow] = useState(true);
  const [expanded, setExpanded] = useState(() => new Set());
  const scrollRef = useRef(null);

  const mark = useCallback(() => onMark?.('evaluator: distracted now'), [onMark]);

  useEffect(() => {
    if (!enabled) return undefined;
    const onKey = (e) => {
      const tag = (e.target?.tagName || '').toLowerCase();
      if (tag === 'input' || tag === 'textarea' || e.target?.isContentEditable) return;
      if (e.key === '`') {
        e.preventDefault();
        setOpen((v) => !v);
      } else if ((e.key === 'm' || e.key === 'M') && open && !e.ctrlKey && !e.metaKey) {
        mark();
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [enabled, open, mark]);

  useEffect(() => {
    if (follow && open && scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [entries, follow, open]);

  const stats = useMemo(() => {
    const beats = entries.filter((e) => e.kind === 'beat');
    const dist = beats.filter((e) => e.res?.verdict === 'DISTRACTED').length;
    const unk = beats.filter((e) => e.res?.verdict === 'UNKNOWN').length;
    const fired = beats.filter(
      (e) => e.res?.intervention_debug?.action === 'fired' || e.res?.intervention_triggered
    ).length;
    const errors = entries.filter((e) => e.kind === 'error').length;
    return { beats: beats.length, dist, unk, fired, errors };
  }, [entries]);

  if (!enabled) return null;

  const stamp = new Date().toISOString().replace(/[:.]/g, '-');

  if (!open) {
    return (
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="absolute bottom-3 left-3 z-[60] px-2 py-1 rounded-md bg-black/75 text-emerald-300 font-mono text-xs border border-white/20 cursor-pointer hover:bg-black/90"
        title="Open evaluation terminal (`)"
        aria-label="Open evaluation terminal"
      >
        &gt;_ eval
      </button>
    );
  }

  return (
    <section
      className="absolute bottom-3 left-3 z-[60] flex flex-col rounded-lg border border-white/20 bg-black/80 text-slate-200 font-mono text-[11px] leading-snug shadow-xl"
      style={{ width: 'min(760px, calc(100% - 24px))', height: 'min(46%, 420px)', minHeight: 160 }}
      aria-label="Evaluation terminal"
    >
      <header className="flex items-center gap-2 px-2 py-1 border-b border-white/15 flex-wrap">
        <span className="text-emerald-300 font-bold">&gt;_ eval</span>
        <span className="text-slate-400">
          {stats.beats} beats · <span className="text-amber-300">{stats.dist} distracted</span> ·{' '}
          {stats.unk} unknown · <span className="text-cyan-300">{stats.fired} fired</span>
          {stats.errors > 0 && <span className="text-red-400"> · {stats.errors} errors</span>}
        </span>
        <span className="flex-1" />
        {[
          { label: follow ? 'pause' : 'follow', onClick: () => setFollow((v) => !v), title: 'Auto-scroll' },
          { label: 'mark (M)', onClick: mark, title: 'Insert a ground-truth marker' },
          ...(onGazeTest
            ? [{ label: 'gaze test', onClick: () => onGazeTest(), title: 'Run the guided gaze self-test' }]
            : []),
          { label: 'clear', onClick: () => { onClear?.(); setExpanded(new Set()); }, title: 'Clear log' },
          {
            label: 'csv',
            onClick: () => download(`eval_${stamp}.csv`, toCsv(entries), 'text/csv'),
            title: 'Download CSV',
          },
          {
            label: 'jsonl',
            onClick: () => download(`eval_${stamp}.jsonl`, toJsonl(entries), 'application/x-ndjson'),
            title: 'Download raw JSONL',
          },
          { label: '×', onClick: () => setOpen(false), title: 'Close (`)' },
        ].map((b) => (
          <button
            key={b.label}
            type="button"
            onClick={b.onClick}
            title={b.title}
            className="px-1.5 py-0.5 rounded border border-white/20 hover:bg-white/10 cursor-pointer text-slate-200"
          >
            {b.label}
          </button>
        ))}
      </header>
      <div
        ref={scrollRef}
        className="flex-1 overflow-y-auto px-1 py-1"
        onWheel={() => setFollow(false)}
        role="log"
        aria-live="off"
      >
        {entries.length === 0 && (
          <div className="text-slate-500 p-2">
            waiting for heartbeats… (one every ~1 s once the session is running)
          </div>
        )}
        {entries.map((e) => {
          if (e.kind === 'mark') {
            return (
              <div key={e.id} className="text-fuchsia-300 font-bold px-1 py-0.5">
                {hhmmss(e.ts)} [MARK] {e.text}
              </div>
            );
          }
          if (e.kind === 'error') {
            return (
              <div key={e.id} className="text-red-400 px-1 py-0.5 whitespace-pre-wrap break-words">
                {hhmmss(e.ts)} ERROR {e.text}
              </div>
            );
          }
          return (
            <BeatLine
              key={e.id}
              entry={e}
              expanded={expanded.has(e.id)}
              onToggle={() =>
                setExpanded((prev) => {
                  const next = new Set(prev);
                  if (next.has(e.id)) next.delete(e.id);
                  else next.add(e.id);
                  return next;
                })
              }
            />
          );
        })}
      </div>
    </section>
  );
}
