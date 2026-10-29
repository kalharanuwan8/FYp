import { ArrowLeft, FileText } from 'lucide-react';
import { useIdleTracker } from '../../hooks/useIdleTracker';
import { Button, Card } from '../common';

/**
 * In-app document reader with record-only idle tracking (DSM-1).
 * Videos must not use this component.
 */
export default function DocumentReader({ material, fileUrl, onClose }) {
  useIdleTracker({
    enabled: !!material?.id,
    context: 'document',
    moduleContentId: material?.id,
  });

  return (
    <div className="fixed inset-0 z-50 bg-bg flex flex-col">
      <header className="flex items-center justify-between gap-3 px-4 md:px-6 py-3 border-b border-border bg-surface">
        <div className="flex items-center gap-2 min-w-0">
          <FileText className="w-5 h-5 text-primary shrink-0" aria-hidden="true" />
          <div className="min-w-0">
            <h1 className="font-display font-bold text-text truncate">
              {material?.title || 'Document'}
            </h1>
            <p className="text-xs text-text-muted">
              Reading view · idle over 15 s is recorded for your teacher (not a diagnosis)
            </p>
          </div>
        </div>
        <Button type="button" variant="secondary" size="sm" onClick={onClose}>
          <ArrowLeft className="w-4 h-4 inline mr-1" aria-hidden="true" />
          Close
        </Button>
      </header>
      <div className="flex-1 bg-learning p-3 md:p-4 overflow-hidden">
        <Card className="h-full overflow-hidden p-0">
          {fileUrl ? (
            <iframe
              title={material?.title || 'Document'}
              src={fileUrl}
              className="w-full h-full min-h-[70vh] border-0 rounded-2xl bg-surface"
            />
          ) : (
            <div className="p-8 text-sm text-text-muted">
              This document has no file URL to preview.
            </div>
          )}
        </Card>
      </div>
    </div>
  );
}
