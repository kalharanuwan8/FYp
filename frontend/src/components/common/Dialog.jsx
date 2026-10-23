import { useEffect, useId, useRef } from 'react';
import { X } from 'lucide-react';

const FOCUSABLE =
  'a[href], button:not([disabled]), textarea:not([disabled]), input:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex="-1"])';

/**
 * Shared accessible dialog: focus trap, initial focus, Escape policy,
 * focus return to the invoking control, and body scroll lock.
 * Set `allowEscape={false}` (and omit onClose) for forced-choice dialogs
 * such as interventions, where choosing an option is how you continue.
 */
export default function Dialog({
  open = true,
  onClose,
  title,
  description,
  children,
  allowEscape = true,
  showClose = false,
  labelledBy,
  panelClassName = 'max-w-md',
  initialFocusRef,
}) {
  const panelRef = useRef(null);
  const titleId = useId();
  const descId = useId();

  useEffect(() => {
    if (!open) return undefined;
    const previouslyFocused = document.activeElement;
    const panel = panelRef.current;
    if (!panel) return undefined;

    const prevOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';

    const focusInitial = () => {
      const target =
        initialFocusRef?.current ||
        panel.querySelector('[data-dialog-autofocus]') ||
        panel.querySelector(FOCUSABLE);
      (target || panel).focus?.();
    };
    const raf = requestAnimationFrame(focusInitial);

    const onKeyDown = (event) => {
      if (event.key === 'Escape' && allowEscape && onClose) {
        event.preventDefault();
        onClose();
        return;
      }
      if (event.key !== 'Tab') return;
      const focusables = Array.from(panel.querySelectorAll(FOCUSABLE)).filter(
        (el) => el.offsetParent !== null || el === document.activeElement
      );
      if (focusables.length === 0) {
        event.preventDefault();
        panel.focus();
        return;
      }
      const first = focusables[0];
      const last = focusables[focusables.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };
    document.addEventListener('keydown', onKeyDown, true);
    return () => {
      cancelAnimationFrame(raf);
      document.removeEventListener('keydown', onKeyDown, true);
      document.body.style.overflow = prevOverflow;
      if (previouslyFocused?.focus) previouslyFocused.focus();
    };
  }, [open, allowEscape, onClose, initialFocusRef]);

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-[70] flex items-end sm:items-center justify-center bg-bg/60 backdrop-blur-sm p-4 overflow-y-auto">
      <div
        ref={panelRef}
        tabIndex={-1}
        role="dialog"
        aria-modal="true"
        aria-labelledby={labelledBy || titleId}
        aria-describedby={description ? descId : undefined}
        className={`bg-surface rounded-t-3xl sm:rounded-3xl shadow-lift border border-border w-full ${panelClassName} p-6 space-y-5 animate-slide-up outline-none max-h-[92vh] overflow-y-auto`}
      >
        {(title || showClose) && (
          <div className="flex items-start justify-between gap-4">
            <div className="space-y-1">
              {title && (
                <h2 id={titleId} className="font-display text-xl font-bold text-text">
                  {title}
                </h2>
              )}
              {description && (
                <p id={descId} className="text-sm text-text-muted">
                  {description}
                </p>
              )}
            </div>
            {showClose && onClose && (
              <button
                type="button"
                onClick={onClose}
                aria-label="Close dialog"
                className="min-h-11 min-w-11 inline-flex items-center justify-center rounded-2xl text-text-muted hover:bg-primary-soft hover:text-text cursor-pointer shrink-0"
              >
                <X className="w-5 h-5" aria-hidden="true" />
              </button>
            )}
          </div>
        )}
        {!title && description && (
          <p id={descId} className="sr-only">
            {description}
          </p>
        )}
        {children}
      </div>
    </div>
  );
}

/** Confirm dialog built on Dialog — replaces alert()/window.confirm(). */
export function ConfirmDialog({
  open,
  onClose,
  onConfirm,
  title,
  description,
  confirmLabel = 'Confirm',
  cancelLabel = 'Cancel',
  busy = false,
}) {
  if (!open) return null;
  return (
    <Dialog open={open} onClose={onClose} title={title} description={description} showClose>
      <div className="flex flex-col sm:flex-row gap-3">
        <button
          type="button"
          onClick={onClose}
          disabled={busy}
          className="flex-1 min-h-11 px-5 rounded-2xl bg-surface text-text border border-border hover:bg-primary-soft font-semibold cursor-pointer disabled:opacity-50"
        >
          {cancelLabel}
        </button>
        <button
          type="button"
          data-dialog-autofocus
          onClick={onConfirm}
          disabled={busy}
          className="flex-1 min-h-11 px-5 rounded-2xl bg-attention text-white hover:brightness-105 font-semibold cursor-pointer disabled:opacity-50"
        >
          {busy ? 'Working…' : confirmLabel}
        </button>
      </div>
    </Dialog>
  );
}
