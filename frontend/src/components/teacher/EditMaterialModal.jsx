import { useState, useEffect } from 'react';
import { Edit3, X, AlertCircle, Save, Sparkles, Trash2 } from 'lucide-react';
import { courseService } from '../../services/courseService';

const emptyMilestone = () => ({
  question: '',
  options: ['', '', '', ''],
  correct_option: 0,
  hint_text: '',
  sequence_order: 1,
});

const mapMilestones = (list) =>
  (list || []).map((m, idx) => ({
    question: m.question || '',
    options:
      Array.isArray(m.options) && m.options.length >= 2
        ? [...m.options]
        : ['', '', '', ''],
    correct_option: typeof m.correct_option === 'number' ? m.correct_option : 0,
    hint_text: m.hint_text || '',
    sequence_order: m.sequence_order || idx + 1,
  }));

export const EditMaterialModal = ({
  isOpen,
  material,
  moduleContents = [],
  onClose,
  onSuccess,
}) => {
  const [title, setTitle] = useState('');
  const [contentType, setContentType] = useState('document');
  const [fileUrl, setFileUrl] = useState('');
  const [description, setDescription] = useState('');
  const [summary, setSummary] = useState('');
  const [milestones, setMilestones] = useState([]);
  const [remediationForId, setRemediationForId] = useState('');
  const [altTitle, setAltTitle] = useState('');
  const [altFileUrl, setAltFileUrl] = useState('');
  const [altUploading, setAltUploading] = useState(false);
  const [removeAlt, setRemoveAlt] = useState(false);
  const [lessonQuestions, setLessonQuestions] = useState([]);
  const [hasLessonQuiz, setHasLessonQuiz] = useState(false);

  const [loading, setLoading] = useState(false);
  const [loadingDetail, setLoadingDetail] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [uploadingFile, setUploadingFile] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (!isOpen || !material?.id) return;

    let cancelled = false;
    (async () => {
      setLoadingDetail(true);
      setError(null);
      try {
        const data = await courseService.getMaterial(material.id);
        if (cancelled) return;
        setTitle(data.title || '');
        setContentType(data.content_type === 'quiz' ? 'document' : data.content_type || 'document');
        setFileUrl(data.file_url || '');
        setSummary(data.summary || '');
        setDescription('');
        setMilestones(mapMilestones(data.milestones));
        setRemediationForId(
          data.remediation_for_content_id != null ? String(data.remediation_for_content_id) : ''
        );
        const existingAlt = (moduleContents || []).find(
          (c) => Number(c.remediation_for_content_id) === Number(material.id)
        );
        setAltTitle(existingAlt?.title || '');
        setAltFileUrl(existingAlt?.file_url || '');
        setRemoveAlt(false);
        setLessonQuestions([]);
        setHasLessonQuiz(Boolean(data.quiz_id));
      } catch (err) {
        if (cancelled) return;
        // Fall back to list payload if detail fetch fails
        setTitle(material.title || '');
        setContentType(
          material.content_type === 'quiz' ? 'document' : material.content_type || 'document'
        );
        setFileUrl(material.file_url || '');
        setSummary(material.summary || '');
        setMilestones(mapMilestones(material.milestones));
        setRemediationForId(
          material.remediation_for_content_id != null
            ? String(material.remediation_for_content_id)
            : ''
        );
        const existingAlt = (moduleContents || []).find(
          (c) => Number(c.remediation_for_content_id) === Number(material.id)
        );
        setAltTitle(existingAlt?.title || '');
        setAltFileUrl(existingAlt?.file_url || '');
        setRemoveAlt(false);
        setLessonQuestions([]);
        setHasLessonQuiz(Boolean(material.quiz_id));
        setError(err.response?.data?.error || null);
      } finally {
        if (!cancelled) setLoadingDetail(false);
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [isOpen, material, moduleContents]);

  if (!isOpen || !material) return null;

  const videoOptions = (moduleContents || []).filter(
    (c) => c.content_type === 'video' && c.id !== material.id
  );
  const linkedAlternate = (moduleContents || []).find(
    (c) => Number(c.remediation_for_content_id) === Number(material.id)
  );

  const handleResetAndClose = () => {
    setError(null);
    onClose();
  };

  const handleFileChange = async (e) => {
    const file = e.target.files[0];
    if (!file) return;
    setUploadingFile(true);
    setError(null);
    try {
      const data = await courseService.uploadMaterialFile(file);
      setFileUrl(data.file_url);
    } catch (err) {
      setError(err.response?.data?.error || 'Failed to upload file to server.');
    } finally {
      setUploadingFile(false);
    }
  };

  const handleAltFileChange = async (e) => {
    const file = e.target.files[0];
    if (!file) return;
    setAltUploading(true);
    setRemoveAlt(false);
    setError(null);
    try {
      const data = await courseService.uploadMaterialFile(file);
      setAltFileUrl(data.file_url);
      if (!altTitle.trim()) {
        const base = file.name.replace(/\.[^.]+$/, '').replace(/[_-]+/g, ' ');
        setAltTitle(base);
      }
    } catch (err) {
      setError(err.response?.data?.error || 'Failed to upload the other version.');
    } finally {
      setAltUploading(false);
    }
  };

  const handleGenerate = async () => {
    setError(null);
    if (!description.trim() && !summary.trim()) {
      setError('Add a description (or keep the summary) so AI can regenerate the quiz pack.');
      return;
    }
    setGenerating(true);
    try {
      const pack = await courseService.generateMaterialPack({
        description: (description.trim() || summary.trim()),
        title: title.trim() || undefined,
        num_questions: 3,
      });
      if (pack.summary) setSummary(pack.summary);
      setMilestones(mapMilestones(pack.milestones));
    } catch (err) {
      const apiMsg = err.response?.data?.error;
      const timedOut = err.code === 'ECONNABORTED' || err.message?.includes('timeout');
      setError(
        apiMsg ||
          (timedOut
            ? 'AI generation timed out. Check Ollama and LLM_MODEL in backend/.env.'
            : 'AI generation failed. Is Ollama running with the configured model?')
      );
    } finally {
      setGenerating(false);
    }
  };

  const updateMilestone = (index, patch) => {
    setMilestones((prev) => prev.map((m, i) => (i === index ? { ...m, ...patch } : m)));
  };

  const updateOption = (mIndex, oIndex, value) => {
    setMilestones((prev) =>
      prev.map((m, i) => {
        if (i !== mIndex) return m;
        const options = [...(m.options || [])];
        options[oIndex] = value;
        return { ...m, options };
      })
    );
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError(null);
    if (!title.trim()) {
      setError('Material title is required.');
      return;
    }

    const cleanedMilestones = milestones
      .filter((m) => m.question.trim())
      .map((m, idx) => ({
        question: m.question.trim(),
        options: (m.options || []).map((o) => o.trim()).filter(Boolean),
        correct_option: m.correct_option || 0,
        hint_text: m.hint_text?.trim() || null,
        sequence_order: m.sequence_order || idx + 1,
      }))
      .filter((m) => m.options.length >= 2);

    if (
      contentType === 'video' &&
      !removeAlt &&
      !linkedAlternate &&
      altTitle.trim() &&
      !altFileUrl.trim()
    ) {
      setError('Upload the other version (PDF, slides, or mind map) or clear its title.');
      return;
    }

    const cleanedLessonQuiz = lessonQuestions
      .map((q) => ({
        question: q.question.trim(),
        options: (q.options || []).map((o) => o.trim()).filter(Boolean),
        correct_option: q.correct_option || 0,
      }))
      .filter((q) => q.question || q.options.length);
    if (contentType === 'video' && cleanedLessonQuiz.some((q) => !q.question || q.options.length < 2)) {
      setError('Each lesson question needs a prompt and at least two answers.');
      return;
    }

    setLoading(true);
    try {
      await courseService.updateMaterial(material.id, {
        title: title.trim(),
        content_type: contentType,
        file_url: fileUrl.trim() || null,
        summary: summary.trim() || null,
        remediation_for_content_id:
          contentType === 'video' ? null : remediationForId ? Number(remediationForId) : null,
        milestones: cleanedMilestones,
        video_quiz:
          contentType === 'video' && cleanedLessonQuiz.length ? cleanedLessonQuiz : undefined,
      });

      if (contentType === 'video') {
        if (removeAlt && linkedAlternate) {
          await courseService.updateMaterial(linkedAlternate.id, {
            remediation_for_content_id: null,
          });
        } else if (linkedAlternate && (altTitle.trim() || altFileUrl.trim())) {
          await courseService.updateMaterial(linkedAlternate.id, {
            title: altTitle.trim() || linkedAlternate.title,
            file_url: altFileUrl.trim() || linkedAlternate.file_url || null,
            remediation_for_content_id: material.id,
          });
        } else if (!linkedAlternate && altFileUrl.trim()) {
          await courseService.createMaterial(material.module_id, {
            title: altTitle.trim() || `${title.trim()} — another way`,
            content_type: 'document',
            file_url: altFileUrl.trim(),
            remediation_for_content_id: material.id,
          });
        }
      }

      onSuccess();
      handleResetAndClose();
    } catch (err) {
      const details = err.response?.data?.details;
      if (details && Array.isArray(details) && details.length > 0) {
        setError(details.map((d) => `${d.field}: ${d.message}`).join(' | '));
      } else {
        setError(err.response?.data?.error || 'Failed to update material.');
      }
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 bg-bg/60 backdrop-blur-sm flex items-center justify-center p-4 z-50 overflow-hidden font-sans">
      <div role="dialog" aria-modal="true" className="bg-surface rounded-2xl p-6 md:p-8 max-w-2xl w-full shadow-2xl space-y-4 my-4 max-h-[90vh] flex flex-col overflow-hidden">
        <div className="flex items-center justify-between border-b border-border pb-4 flex-shrink-0">
          <div className="flex items-center gap-3">
            <div className="p-2.5 bg-primary-soft text-primary rounded-xl border border-primary/30">
              <Edit3 className="w-5 h-5" />
            </div>
            <div>
              <h2 className="text-lg font-bold text-text leading-tight">Edit Learning Material</h2>
              <p className="text-xs text-text-muted font-medium">
                Update file, alternate link, and AI-drafted summary — review before saving.
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

        {error && (
          <div className="p-3.5 rounded-xl bg-red-50 border border-red-200 text-red-700 text-xs font-medium flex items-center gap-2 flex-shrink-0">
            <AlertCircle className="w-4 h-4 text-red-500 flex-shrink-0" />
            <span>{error}</span>
          </div>
        )}

        {loadingDetail ? (
          <p className="text-xs text-text-muted font-medium py-8 text-center">Loading material…</p>
        ) : (
          <form onSubmit={handleSubmit} className="space-y-4 overflow-y-auto overscroll-contain pr-2 flex-1 min-h-0 text-xs">
            <div>
              <label className="block font-bold text-text uppercase tracking-wider mb-1">
                Content Title *
              </label>
              <input
                type="text"
                required
                maxLength={150}
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                className="w-full bg-bg border border-border focus:border-primary focus:bg-surface focus:outline-none rounded-lg p-2.5 text-text"
              />
            </div>

            <div>
              <label className="block font-bold text-text uppercase tracking-wider mb-1">
                Content Type *
              </label>
              <select
                value={contentType}
                onChange={(e) => setContentType(e.target.value)}
                className="w-full bg-bg border border-border focus:border-primary focus:bg-surface focus:outline-none rounded-lg p-2.5 text-text font-semibold"
              >
                <option value="document">Document (PDF / Slides / DOC)</option>
                <option value="video">Video (MP4 / WebM / Stream URL)</option>
                <option value="other">Other Resource Link</option>
              </select>
            </div>

            <div className="bg-bg p-4 rounded-xl border border-dashed border-border space-y-2">
              <label className="block font-bold text-text uppercase tracking-wider text-[11px]">
                Replace File (Optional)
              </label>
              <input
                type="file"
                onChange={handleFileChange}
                className="text-xs text-text-muted file:mr-3 file:py-1.5 file:px-3 file:rounded-lg file:border-0 file:text-xs file:font-bold file:bg-primary file:text-on-primary hover:file:bg-primary-hover cursor-pointer"
              />
              {uploadingFile && <span className="text-primary font-bold">Uploading...</span>}
            </div>

            <div>
              <label className="block font-bold text-text uppercase tracking-wider mb-1">
                File URL or Server Path
              </label>
              <input
                type="text"
                value={fileUrl}
                onChange={(e) => setFileUrl(e.target.value)}
                className="w-full bg-bg border border-border focus:border-primary focus:bg-surface focus:outline-none rounded-lg p-2.5 text-text font-mono text-[11px]"
              />
            </div>

            {contentType === 'video' && (
              <div className="rounded-xl border border-primary/30 bg-primary-soft/40 p-4 space-y-3">
                <div>
                  <p className="font-bold text-text uppercase tracking-wider">
                    If they fail, deliver it another way
                  </p>
                  <p className="mt-1 text-[11px] text-text-muted">
                    PDF, slides, or a mind map offered when a student fails this video&apos;s quiz.
                  </p>
                </div>
                {linkedAlternate && !removeAlt && (
                  <p className="text-[11px] font-semibold text-primary">
                    Currently linked: {linkedAlternate.title}
                  </p>
                )}
                {removeAlt && (
                  <p className="text-[11px] font-semibold text-warning">
                    The other version will be unlinked when you save. It stays in the module as a
                    normal document.
                  </p>
                )}
                <div>
                  <label className="block font-bold text-text uppercase tracking-wider mb-1">
                    Other version title
                  </label>
                  <input
                    type="text"
                    maxLength={150}
                    value={altTitle}
                    onChange={(e) => {
                      setAltTitle(e.target.value);
                      setRemoveAlt(false);
                    }}
                    placeholder="e.g. Chapter 1 mind map"
                    className="w-full bg-surface border border-border focus:border-primary focus:outline-none rounded-lg p-2.5 text-text"
                  />
                </div>
                <div className="bg-surface p-3 rounded-xl border border-dashed border-border space-y-2">
                  <label className="block font-bold text-text uppercase tracking-wider text-[11px]">
                    {linkedAlternate ? 'Replace the other version' : 'Upload the other version'}
                  </label>
                  <input
                    type="file"
                    accept=".pdf,.ppt,.pptx,.doc,.docx,.png,.jpg,.jpeg,.webp"
                    onChange={handleAltFileChange}
                    className="text-xs text-text-muted file:mr-3 file:py-1.5 file:px-3 file:rounded-lg file:border-0 file:text-xs file:font-bold file:bg-primary file:text-on-primary hover:file:bg-primary-hover cursor-pointer"
                  />
                  {altUploading && <span className="text-primary font-bold">Uploading...</span>}
                  {altFileUrl && !altUploading && (
                    <p className="text-[11px] text-primary font-semibold break-all">
                      Attached: {altFileUrl}
                    </p>
                  )}
                </div>
                {linkedAlternate && (
                  <button
                    type="button"
                    onClick={() => setRemoveAlt((v) => !v)}
                    className="text-[11px] font-bold text-red-600 hover:underline cursor-pointer"
                  >
                    {removeAlt ? 'Keep the other version' : 'Unlink the other version'}
                  </button>
                )}

                <div className="space-y-3 pt-1">
                  <div className="flex items-center justify-between gap-2">
                    <div>
                      <p className="font-bold text-text uppercase tracking-wider">Lesson quiz</p>
                      <p className="mt-1 text-[11px] text-text-muted">
                        {hasLessonQuiz
                          ? 'A lesson quiz is already on this video. New questions replace it, unless a student has already taken it.'
                          : 'Questions about this video. Not the focus intervention. A miss asks the student to study the other version.'}
                      </p>
                    </div>
                    <button
                      type="button"
                      onClick={() =>
                        setLessonQuestions((prev) => [
                          ...prev,
                          { question: '', options: ['', '', '', ''], correct_option: 0 },
                        ])
                      }
                      className="text-[11px] font-bold text-primary hover:underline cursor-pointer shrink-0"
                    >
                      + Add question
                    </button>
                  </div>
                  {lessonQuestions.map((q, qi) => (
                    <div key={qi} className="rounded-xl border border-border bg-surface p-3 space-y-2">
                      <div className="flex items-start gap-2">
                        <input
                          type="text"
                          value={q.question}
                          onChange={(e) =>
                            setLessonQuestions((prev) =>
                              prev.map((item, i) =>
                                i === qi ? { ...item, question: e.target.value } : item
                              )
                            )
                          }
                          placeholder={`Question ${qi + 1} about the video`}
                          className="flex-1 bg-bg border border-border rounded-lg p-2 text-text"
                        />
                        <button
                          type="button"
                          onClick={() => setLessonQuestions((prev) => prev.filter((_, i) => i !== qi))}
                          className="p-2 text-text-muted hover:text-red-600 cursor-pointer"
                          title="Remove question"
                        >
                          <Trash2 className="w-4 h-4" />
                        </button>
                      </div>
                      <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                        {(q.options || []).map((opt, oi) => (
                          <label key={oi} className="flex items-center gap-2">
                            <input
                              type="radio"
                              name={`edit-lesson-correct-${qi}`}
                              checked={q.correct_option === oi}
                              onChange={() =>
                                setLessonQuestions((prev) =>
                                  prev.map((item, i) =>
                                    i === qi ? { ...item, correct_option: oi } : item
                                  )
                                )
                              }
                            />
                            <input
                              type="text"
                              value={opt}
                              onChange={(e) =>
                                setLessonQuestions((prev) =>
                                  prev.map((item, i) => {
                                    if (i !== qi) return item;
                                    const options = [...item.options];
                                    options[oi] = e.target.value;
                                    return { ...item, options };
                                  })
                                )
                              }
                              placeholder={`Answer ${String.fromCharCode(65 + oi)}`}
                              className="flex-1 bg-bg border border-border rounded-lg p-2 text-text"
                            />
                          </label>
                        ))}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {contentType !== 'video' && (
              <div>
                <label className="block font-bold text-text uppercase tracking-wider mb-1">
                  Use as alternate for (optional)
                </label>
                <select
                  value={remediationForId}
                  onChange={(e) => setRemediationForId(e.target.value)}
                  className="w-full bg-bg border border-border focus:border-primary focus:bg-surface focus:outline-none rounded-lg p-2.5 text-text font-semibold"
                >
                  <option value="">Not an alternate</option>
                  {videoOptions.map((v) => (
                    <option key={v.id} value={v.id}>
                      {v.title}
                    </option>
                  ))}
                </select>
                <p className="mt-1 text-[11px] text-text-muted">
                  Shown when a student fails that video&apos;s quiz (mind map, PDF, slides, notes).
                </p>
              </div>
            )}

            <div>
              <label className="block font-bold text-text uppercase tracking-wider mb-1">
                Teacher description (for AI draft)
              </label>
              <textarea
                rows={2}
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                placeholder="Optional — leave blank to regenerate from the current summary"
                className="w-full bg-bg border border-border focus:border-primary focus:bg-surface focus:outline-none rounded-lg p-2.5 text-text resize-none"
              />
              <button
                type="button"
                onClick={handleGenerate}
                disabled={generating || uploadingFile}
                className="mt-2 inline-flex items-center gap-2 px-3 py-2 rounded-lg bg-primary hover:bg-primary-hover text-on-primary text-xs font-bold cursor-pointer disabled:opacity-50"
              >
                <Sparkles className="w-3.5 h-3.5" />
                {generating ? 'Generating…' : 'AI draft summary & checkpoints'}
              </button>
              <p className="mt-1 text-[11px] text-text-muted">
                AI drafts for your review only — students never see unsaved drafts.
              </p>
            </div>

            <div>
              <label className="block font-bold text-text uppercase tracking-wider mb-1">
                Summary
              </label>
              <textarea
                rows={3}
                value={summary}
                onChange={(e) => setSummary(e.target.value)}
                className="w-full bg-bg border border-border focus:border-primary focus:bg-surface focus:outline-none rounded-lg p-2.5 text-text resize-none"
              />
            </div>

            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <label className="block font-bold text-text uppercase tracking-wider">
                  Milestone quiz items
                </label>
                <button
                  type="button"
                  onClick={() =>
                    setMilestones((prev) => [
                      ...prev,
                      { ...emptyMilestone(), sequence_order: prev.length + 1 },
                    ])
                  }
                  className="text-[11px] font-bold text-primary hover:underline cursor-pointer"
                >
                  + Add question
                </button>
              </div>

              {milestones.map((m, mi) => (
                <div
                  key={mi}
                  className="rounded-xl border border-border bg-bg/80 p-3 space-y-2"
                >
                  <div className="flex items-start justify-between gap-2">
                    <input
                      type="text"
                      value={m.question}
                      onChange={(e) => updateMilestone(mi, { question: e.target.value })}
                      placeholder={`Question ${mi + 1}`}
                      className="flex-1 bg-surface border border-border rounded-lg p-2 text-text"
                    />
                    <button
                      type="button"
                      onClick={() => setMilestones((prev) => prev.filter((_, i) => i !== mi))}
                      className="p-2 text-text-muted hover:text-red-600 cursor-pointer"
                      title="Remove"
                    >
                      <Trash2 className="w-4 h-4" />
                    </button>
                  </div>
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                    {(m.options || []).map((opt, oi) => (
                      <label key={oi} className="flex items-center gap-2">
                        <input
                          type="radio"
                          name={`edit-correct-${mi}`}
                          checked={m.correct_option === oi}
                          onChange={() => updateMilestone(mi, { correct_option: oi })}
                        />
                        <input
                          type="text"
                          value={opt}
                          onChange={(e) => updateOption(mi, oi, e.target.value)}
                          placeholder={`Option ${String.fromCharCode(65 + oi)}`}
                          className="flex-1 bg-surface border border-border rounded-lg p-2 text-text"
                        />
                      </label>
                    ))}
                  </div>
                  <input
                    type="text"
                    value={m.hint_text || ''}
                    onChange={(e) => updateMilestone(mi, { hint_text: e.target.value })}
                    placeholder="Optional hint"
                    className="w-full bg-surface border border-border rounded-lg p-2 text-text"
                  />
                </div>
              ))}
            </div>

            <div className="pt-4 border-t border-border flex items-center justify-end gap-3 sticky bottom-0 bg-surface pb-1">
              <button
                type="button"
                onClick={handleResetAndClose}
                className="px-4 py-2 text-xs font-semibold text-text-muted hover:bg-bg rounded-lg transition-colors cursor-pointer"
              >
                Cancel
              </button>
              <button
                type="submit"
                disabled={loading || uploadingFile || generating || altUploading}
                className="bg-primary hover:bg-primary-hover text-on-primary text-xs font-bold px-5 py-2.5 rounded-lg shadow-xs transition-all flex items-center gap-2 cursor-pointer disabled:opacity-50"
              >
                <Save className="w-4 h-4" />
                <span>{loading ? 'Saving…' : 'Save Changes'}</span>
              </button>
            </div>
          </form>
        )}
      </div>
    </div>
  );
};

export default EditMaterialModal;
