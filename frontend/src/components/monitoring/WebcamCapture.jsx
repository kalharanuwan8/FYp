import { Camera } from 'lucide-react';

/**
 * Live webcam preview for monitored sessions.
 * Pass webcamRef from useMonitoringSession; keep mirrored for natural UX.
 */
export default function WebcamCapture({
  videoRef,
  canvasRef,
  cameraActive = false,
  className = '',
  compact = false,
}) {
  const sizeClass = compact ? 'w-20 h-14' : 'w-full max-w-xs aspect-video';

  return (
    <div className={`relative ${sizeClass} bg-black rounded-lg overflow-hidden border border-border ${className}`}>
      <video
        ref={videoRef}
        autoPlay
        playsInline
        muted
        className="w-full h-full object-cover transform -scale-x-100"
      />
      <canvas ref={canvasRef} className="hidden" />
      {!cameraActive && (
        <div className="absolute inset-0 flex flex-col items-center justify-center gap-1 bg-bg/90 text-text-muted">
          <Camera className="w-5 h-5" />
          {!compact && (
            <span className="text-[10px] font-semibold px-2 text-center">
              Waiting for camera…
            </span>
          )}
        </div>
      )}
    </div>
  );
}
