import { useState } from 'react';
import { UploadCloud, X, AlertCircle, CheckCircle2, FileText, AlertTriangle, RefreshCw } from 'lucide-react';
import { adminService } from '../../services/adminService';

export const CsvImportModal = ({ isOpen, onClose, onSuccess }) => {
  const [file, setFile] = useState(null);
  const [uploading, setUploading] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);

  if (!isOpen) return null;

  const handleResetAndClose = () => {
    setFile(null);
    setUploading(false);
    setResult(null);
    setError(null);
    onClose();
  };

  const handleFileChange = (e) => {
    const selected = e.target.files[0];
    if (selected) {
      setFile(selected);
      setError(null);
    }
  };

  const handleUpload = async (e) => {
    e.preventDefault();
    if (!file) {
      setError('Please select a valid CSV file to upload.');
      return;
    }

    setUploading(true);
    setError(null);
    setResult(null);

    try {
      const data = await adminService.bulkImportUsers(file);
      setResult(data);
    } catch (err) {
      setError(err.response?.data?.error || 'Failed to process bulk import. Please try again.');
    } finally {
      setUploading(false);
    }
  };

  return (
    <div className="fixed inset-0 bg-bg/60 backdrop-blur-sm flex items-center justify-center p-4 z-50 overflow-y-auto font-sans">
      <div role="dialog" aria-modal="true" className="bg-surface rounded-2xl p-6 md:p-8 max-w-xl w-full shadow-2xl space-y-6 my-8">
        
        {/* Modal Header */}
        <div className="flex items-center justify-between border-b border-border pb-4">
          <div className="flex items-center gap-3">
            <div className="p-2.5 bg-primary-soft text-primary rounded-xl border border-primary/30">
              <UploadCloud className="w-5 h-5" />
            </div>
            <div>
              <h2 className="text-lg font-bold text-text leading-tight">
                Bulk Import Users via CSV
              </h2>
              <p className="text-xs text-text-muted font-medium">
                Batch register teachers and students with row validation.
              </p>
            </div>
          </div>
          <button
            onClick={handleResetAndClose}
            className="p-1.5 text-text-muted hover:text-text-muted hover:bg-bg rounded-lg transition-colors cursor-pointer"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Error Alert Banner */}
        {error && (
          <div className="p-3.5 rounded-xl bg-red-50 border border-red-200 text-red-700 text-xs font-medium flex items-center gap-2">
            <AlertCircle className="w-4 h-4 text-red-500 flex-shrink-0" />
            <span>{error}</span>
          </div>
        )}

        {/* Instructions Banner */}
        {!result && (
          <div className="bg-bg border border-border/80 rounded-xl p-4 text-xs space-y-2 text-text-muted">
            <span className="font-bold text-text uppercase tracking-wider text-[11px] block">
              Expected CSV Header Format:
            </span>
            <code className="block bg-surface p-2 rounded-lg border border-border text-sky-900 font-mono text-[11px] overflow-x-auto">
              email, password, first_name, last_name, role, grade_level, guardian_name, guardian_email
            </code>
            <p className="text-[11px] text-text-muted">
              Note: <strong className="text-text">grade_level</strong>, <strong className="text-text">guardian_name</strong>, and <strong className="text-text">guardian_email</strong> are required for student rows.
            </p>
          </div>
        )}

        {/* Upload Form View */}
        {!result ? (
          <form onSubmit={handleUpload} className="space-y-5">
            <div className="border-2 border-dashed border-border hover:border-primary rounded-2xl p-6 text-center bg-bg/50 hover:bg-primary-soft/30 transition-all">
              <input
                type="file"
                accept=".csv"
                id="csv-file-input"
                onChange={handleFileChange}
                className="hidden"
              />
              <label htmlFor="csv-file-input" className="cursor-pointer space-y-2 block">
                <FileText className="w-8 h-8 text-primary mx-auto" />
                <span className="text-xs font-bold text-text block">
                  {file ? file.name : 'Click to select CSV file from your computer'}
                </span>
                {file ? (
                  <span className="text-[11px] text-text-muted font-mono">
                    ({(file.size / 1024).toFixed(1)} KB)
                  </span>
                ) : (
                  <span className="text-[11px] text-text-muted block">
                    Supports standard UTF-8 encoded .csv files
                  </span>
                )}
              </label>
            </div>

            {/* Modal Actions */}
            <div className="pt-2 border-t border-border flex items-center justify-end gap-3">
              <button
                type="button"
                onClick={handleResetAndClose}
                className="px-4 py-2 text-xs font-semibold text-text-muted hover:bg-bg rounded-lg transition-colors cursor-pointer"
              >
                Cancel
              </button>

              <button
                type="submit"
                disabled={!file || uploading}
                className="bg-primary hover:bg-primary-hover text-on-primary text-xs font-bold px-5 py-2.5 rounded-lg shadow-xs transition-all flex items-center gap-2 cursor-pointer disabled:opacity-50"
              >
                {uploading ? (
                  <>
                    <RefreshCw className="w-4 h-4 animate-spin" />
                    <span>Processing Import...</span>
                  </>
                ) : (
                  <>
                    <UploadCloud className="w-4 h-4" />
                    <span>Upload & Import</span>
                  </>
                )}
              </button>
            </div>
          </form>
        ) : (
          /* Import Results View */
          <div className="space-y-5 text-xs">
            {/* Summary Counters */}
            <div className="grid grid-cols-2 gap-4">
              <div className="bg-emerald-50 border border-emerald-200 p-4 rounded-xl text-center space-y-1">
                <span className="text-xs font-bold uppercase tracking-wider text-emerald-800 flex items-center justify-center gap-1.5">
                  <CheckCircle2 className="w-4 h-4 text-emerald-600" />
                  <span>Successfully Created</span>
                </span>
                <span className="text-2xl font-extrabold text-emerald-700 block">
                  {result.created}
                </span>
              </div>

              <div className="bg-amber-50 border border-amber-200 p-4 rounded-xl text-center space-y-1">
                <span className="text-xs font-bold uppercase tracking-wider text-amber-800 flex items-center justify-center gap-1.5">
                  <AlertTriangle className="w-4 h-4 text-amber-600" />
                  <span>Failed Rows</span>
                </span>
                <span className="text-2xl font-extrabold text-amber-700 block">
                  {result.failed}
                </span>
              </div>
            </div>

            {/* Error Detail Breakdown Table */}
            {result.errors && result.errors.length > 0 && (
              <div className="space-y-2">
                <h4 className="font-bold text-text uppercase tracking-wider text-[11px]">
                  Failed Rows Breakdown ({result.errors.length}):
                </h4>
                <div className="bg-bg border border-border rounded-xl overflow-hidden max-h-56 overflow-y-auto">
                  <table className="w-full text-left border-collapse">
                    <thead className="bg-bg text-text-muted font-bold uppercase tracking-wider text-[10px] sticky top-0 border-b border-border">
                      <tr>
                        <th className="py-2 px-3 w-20">Row #</th>
                        <th className="py-2 px-3">Validation Error Details</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-border text-text text-[11px]">
                      {result.errors.map((errItem, idx) => (
                        <tr key={idx} className="hover:bg-bg/60">
                          <td className="py-2 px-3 font-mono font-bold text-text">
                            #{errItem.row_number}
                          </td>
                          <td className="py-2 px-3 font-medium text-red-700">
                            {errItem.error}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}

            {/* Done Action */}
            <div className="pt-3 border-t border-border flex items-center justify-end">
              <button
                onClick={() => {
                  onSuccess();
                  handleResetAndClose();
                }}
                className="bg-primary hover:bg-primary-hover text-on-primary text-xs font-bold px-6 py-2.5 rounded-lg shadow-xs transition-all cursor-pointer"
              >
                Done
              </button>
            </div>
          </div>
        )}

      </div>
    </div>
  );
};

export default CsvImportModal;
