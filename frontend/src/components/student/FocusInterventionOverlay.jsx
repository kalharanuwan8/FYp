import InterventionOverlay from '../intervention/InterventionOverlay';

/** Back-compat wrapper — prefer InterventionOverlay directly. */
export default function FocusInterventionOverlay(props) {
  return <InterventionOverlay {...props} />;
}
