import { useEffect } from 'react';
import { Headphones, MapPin, Play, Volume2 } from 'lucide-react';
import Dialog from '../common/Dialog';

/**
 * Environment noise notice — one-time per session, modal and lesson-pausing.
 * Fired by the backend as intervention_type "environment_noise_notice" when
 * background loudness stays high. The student picks one option to continue;
 * the choice is logged as noise_action on the intervention.
 */
export default function NoiseNotice({ message, interventionId, onRespond, onPauseContent }) {
  useEffect(() => {
    if (onPauseContent) onPauseContent();
  }, [onPauseContent]);

  const options = [
    {
      action: 'headphones',
      label: "I'll use headphones",
      detail: 'Block out the noise around me',
      Icon: Headphones,
    },
    {
      action: 'move_environment',
      label: "I'll move somewhere quieter",
      detail: 'Find a calmer spot to keep learning',
      Icon: MapPin,
    },
    {
      action: 'continue_anyway',
      label: 'Continue anyway',
      detail: "I'm okay to keep going like this",
      Icon: Play,
    },
  ];

  return (
    <Dialog
      title="It's quite noisy around you"
      description={
        message ||
        "It's quite noisy where you are — that can make it hard to concentrate. What would you like to do?"
      }
      allowEscape={false}
    >
      <div className="text-center">
        <span
          className="inline-flex items-center justify-center w-14 h-14 rounded-full bg-primary-soft text-primary"
          aria-hidden="true"
        >
          <Volume2 className="w-7 h-7" />
        </span>
      </div>

      <div className="space-y-3" role="group" aria-label="How would you like to continue">
        {options.map(({ action, label, detail, Icon }, index) => (
          <button
            key={action}
            type="button"
            data-dialog-autofocus={index === 0 ? true : undefined}
            onClick={() => onRespond(interventionId, 'reengaged', { noise_action: action })}
            className="w-full flex items-center gap-3 min-h-14 rounded-2xl border border-border bg-bg hover:border-primary hover:bg-primary-soft transition-colors cursor-pointer px-4 py-3 text-left"
          >
            <span className="text-primary shrink-0" aria-hidden="true">
              <Icon className="w-6 h-6" />
            </span>
            <span className="flex-1">
              <span className="block text-sm font-semibold text-text">{label}</span>
              <span className="block text-xs text-text-muted">{detail}</span>
            </span>
          </button>
        ))}
      </div>

      <p className="text-center text-xs text-text-muted">Pick one to continue your lesson.</p>
    </Dialog>
  );
}
