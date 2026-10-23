import { useId } from 'react';

const inputClass =
  'w-full min-h-11 rounded-2xl border border-border bg-bg px-4 py-2.5 text-text placeholder:text-text-muted disabled:opacity-50';

export function Field({ label, hint, error, children, id: idProp }) {
  const autoId = useId();
  const id = idProp || autoId;
  return (
    <div className="space-y-1.5">
      {label && (
        <label htmlFor={id} className="block text-sm font-semibold text-text">
          {label}
        </label>
      )}
      {typeof children === 'function' ? children(id) : children}
      {hint && !error && <p className="text-xs text-text-muted">{hint}</p>}
      {error && (
        <p role="alert" className="text-xs font-medium text-danger">
          {error}
        </p>
      )}
    </div>
  );
}

export function Input({ id, ...props }) {
  return <input id={id} className={inputClass} {...props} />;
}

export function Textarea({ id, ...props }) {
  return <textarea id={id} className={`${inputClass} min-h-24`} {...props} />;
}

export function Select({ id, children, ...props }) {
  return (
    <select id={id} className={inputClass} {...props}>
      {children}
    </select>
  );
}

/**
 * Accessible segmented toggle: radiogroup semantics, selection shown by
 * border + weight + aria-checked, never colour alone.
 */
export function SegmentedControl({ label, options, value, onChange }) {
  return (
    <div>
      {label && <p className="text-sm font-semibold text-text mb-2">{label}</p>}
      <div role="radiogroup" aria-label={label} className="flex flex-wrap gap-2">
        {options.map((opt) => {
          const selected = opt.value === value;
          return (
            <button
              key={String(opt.value)}
              type="button"
              role="radio"
              aria-checked={selected}
              onClick={() => onChange(opt.value)}
              className={`min-h-11 px-4 rounded-2xl border text-sm cursor-pointer transition-colors ${
                selected
                  ? 'border-primary bg-primary-soft text-text font-bold shadow-soft'
                  : 'border-border bg-bg text-text-muted hover:border-primary font-medium'
              }`}
            >
              {opt.label}
            </button>
          );
        })}
      </div>
    </div>
  );
}
