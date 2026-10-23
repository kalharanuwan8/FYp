import { useState } from 'react';
import { X, HelpCircle, Plus, Trash2, AlertCircle, CheckCircle2 } from 'lucide-react';
import { quizService } from '../../services/quizService';

const createEmptyQuestion = () => ({
  question_text: '',
  question_type: 'multiple_choice',
  correct_answer_text: '',
  options: [
    { option_text: '', is_correct: true },
    { option_text: '', is_correct: false },
  ],
});

export const CreateQuizModal = ({ isOpen, moduleId, onClose, onSuccess }) => {
  const [title, setTitle] = useState('');
  const [questions, setQuestions] = useState([createEmptyQuestion()]);

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  if (!isOpen) return null;

  const handleResetAndClose = () => {
    setTitle('');
    setQuestions([createEmptyQuestion()]);
    setError(null);
    setLoading(false);
    onClose();
  };

  const setCorrectOption = (qIdx, optIdx) => {
    setQuestions((prev) =>
      prev.map((q, i) =>
        i !== qIdx
          ? q
          : {
              ...q,
              options: q.options.map((opt, j) => ({ ...opt, is_correct: j === optIdx })),
            }
      )
    );
  };

  const updateQuestionText = (qIdx, text) => {
    setQuestions((prev) =>
      prev.map((q, i) => (i !== qIdx ? q : { ...q, question_text: text }))
    );
  };

  const updateQuestionType = (qIdx, type) => {
    setQuestions((prev) =>
      prev.map((q, i) => {
        if (i !== qIdx) return q;
        const newOptions =
          type === 'multiple_choice' && (!q.options || q.options.length < 2)
            ? [
                { option_text: '', is_correct: true },
                { option_text: '', is_correct: false },
              ]
            : q.options;
        return {
          ...q,
          question_type: type,
          options: newOptions,
        };
      })
    );
  };

  const updateShortAnswerText = (qIdx, text) => {
    setQuestions((prev) =>
      prev.map((q, i) => (i !== qIdx ? q : { ...q, correct_answer_text: text }))
    );
  };

  const updateOptionText = (qIdx, optIdx, text) => {
    setQuestions((prev) =>
      prev.map((q, i) =>
        i !== qIdx
          ? q
          : {
              ...q,
              options: q.options.map((opt, j) => (j !== optIdx ? opt : { ...opt, option_text: text })),
            }
      )
    );
  };

  const addOption = (qIdx) => {
    setQuestions((prev) =>
      prev.map((q, i) =>
        i !== qIdx
          ? q
          : {
              ...q,
              options: [...q.options, { option_text: '', is_correct: false }],
            }
      )
    );
  };

  const removeOption = (qIdx, optIdx) => {
    setQuestions((prev) =>
      prev.map((q, i) => {
        if (i !== qIdx) return q;
        if (q.options.length <= 2) return q;
        let newOptions = q.options.filter((_, j) => j !== optIdx);
        const hasCorrect = newOptions.some((o) => o.is_correct);
        if (!hasCorrect && newOptions.length > 0) {
          newOptions = newOptions.map((o, idx) => (idx === 0 ? { ...o, is_correct: true } : o));
        }
        return { ...q, options: newOptions };
      })
    );
  };

  const addQuestion = () => {
    setQuestions((prev) => [...prev, createEmptyQuestion()]);
  };

  const removeQuestion = (qIdx) => {
    if (questions.length <= 1) return;
    setQuestions((prev) => prev.filter((_, i) => i !== qIdx));
  };

  const validateClientSide = () => {
    if (!title.trim()) {
      return 'Quiz title is required.';
    }
    if (questions.length < 1) {
      return 'At least one question is required.';
    }
    for (let i = 0; i < questions.length; i++) {
      const q = questions[i];
      const qNum = i + 1;
      if (!q.question_text.trim()) {
        return `Question #${qNum} text is required.`;
      }
      if (q.question_type === 'multiple_choice') {
        if (!q.options || q.options.length < 2) {
          return `Question #${qNum} must have at least 2 options.`;
        }
        for (let j = 0; j < q.options.length; j++) {
          if (!q.options[j].option_text.trim()) {
            return `Question #${qNum}, Option #${j + 1} text cannot be empty.`;
          }
        }
        const correctCount = q.options.filter((o) => o.is_correct).length;
        if (correctCount !== 1) {
          return `Question #${qNum} must have exactly one correct option selected.`;
        }
      } else if (q.question_type === 'short_answer') {
        if (!q.correct_answer_text || !q.correct_answer_text.trim()) {
          return `Question #${qNum} requires a non-empty correct answer text.`;
        }
      }
    }
    return null;
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError(null);

    const clientErr = validateClientSide();
    if (clientErr) {
      setError(clientErr);
      return;
    }

    setLoading(true);

    const payload = {
      title: title.trim(),
      questions: questions.map((q) => {
        if (q.question_type === 'multiple_choice') {
          return {
            question_text: q.question_text.trim(),
            question_type: 'multiple_choice',
            options: q.options.map((opt) => ({
              option_text: opt.option_text.trim(),
              is_correct: opt.is_correct,
            })),
          };
        } else {
          return {
            question_text: q.question_text.trim(),
            question_type: 'short_answer',
            correct_answer_text: q.correct_answer_text.trim(),
          };
        }
      }),
    };

    try {
      await quizService.createQuiz(moduleId, payload);
      onSuccess();
      handleResetAndClose();
    } catch (err) {
      const details = err.response?.data?.details;
      if (details && Array.isArray(details) && details.length > 0) {
        setError(details.map((d) => `${d.field}: ${d.message}`).join(' | '));
      } else {
        setError(err.response?.data?.error || 'Failed to create quiz. Please check fields.');
      }
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 bg-bg/60 backdrop-blur-sm flex items-center justify-center p-4 z-50 overflow-y-auto font-sans">
      <div role="dialog" aria-modal="true" className="bg-surface rounded-2xl p-6 md:p-8 max-w-2xl w-full shadow-2xl space-y-6 my-8 max-h-[90vh] flex flex-col">
        
        {/* Header */}
        <div className="flex justify-between items-center border-b border-border pb-4 flex-shrink-0">
          <div className="flex items-center gap-2.5">
            <div className="w-9 h-9 rounded-xl bg-primary/10 text-primary flex items-center justify-center font-bold">
              <HelpCircle className="w-5 h-5" />
            </div>
            <div>
              <h3 className="font-bold text-text text-base">Create Assessment Quiz</h3>
              <p className="text-xs text-text-muted font-medium">Add multiple choice or short answer questions</p>
            </div>
          </div>
          <button
            type="button"
            onClick={handleResetAndClose}
            className="text-text-muted hover:text-text-muted transition-colors cursor-pointer"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Error Banner */}
        {error && (
          <div className="p-3.5 rounded-xl bg-red-50 border border-red-200 text-red-700 text-xs font-medium flex items-center gap-2 flex-shrink-0">
            <AlertCircle className="w-4 h-4 text-red-500 flex-shrink-0" />
            <span>{error}</span>
          </div>
        )}

        {/* Scrollable Form Body */}
        <form onSubmit={handleSubmit} className="space-y-6 overflow-y-auto pr-2 flex-1 text-xs">
          
          {/* Quiz Title */}
          <div>
            <label className="block font-bold text-text uppercase tracking-wider mb-1">
              Quiz Title *
            </label>
            <input
              type="text"
              required
              maxLength={150}
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="e.g. Chapter 1 Concept Check Quiz"
              className="w-full bg-bg border border-border focus:border-primary focus:bg-surface focus:outline-none rounded-lg p-2.5 text-text text-sm font-medium"
            />
          </div>

          {/* Questions Container */}
          <div className="space-y-6 pt-2">
            <div className="flex items-center justify-between">
              <span className="font-bold text-text uppercase tracking-wider text-[11px]">
                Questions List ({questions.length})
              </span>
            </div>

            {questions.map((q, qIdx) => (
              <div
                key={qIdx}
                className="bg-bg/70 border border-border p-4 md:p-5 rounded-2xl space-y-4 relative"
              >
                {/* Question Header Bar */}
                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 border-b border-border/60 pb-3">
                  <span className="font-bold text-text text-xs flex items-center gap-1.5">
                    <span className="w-5 h-5 rounded-full bg-primary text-on-primary text-[10px] font-bold flex items-center justify-center">
                      {qIdx + 1}
                    </span>
                    Question #{qIdx + 1}
                  </span>

                  <div className="flex items-center gap-3">
                    <select
                      value={q.question_type}
                      onChange={(e) => updateQuestionType(qIdx, e.target.value)}
                      className="bg-surface border border-border focus:border-primary focus:outline-none rounded-lg px-2.5 py-1 text-xs font-semibold text-text cursor-pointer"
                    >
                      <option value="multiple_choice">Multiple Choice</option>
                      <option value="short_answer">Short Answer</option>
                    </select>

                    <button
                      type="button"
                      disabled={questions.length <= 1}
                      onClick={() => removeQuestion(qIdx)}
                      className="text-text-muted hover:text-red-600 disabled:opacity-30 disabled:cursor-not-allowed cursor-pointer p-1 transition-colors"
                      title="Remove Question"
                    >
                      <Trash2 className="w-4 h-4" />
                    </button>
                  </div>
                </div>

                {/* Question Text */}
                <div>
                  <label className="block font-bold text-text-muted mb-1">
                    Question Text *
                  </label>
                  <textarea
                    rows={2}
                    required
                    value={q.question_text}
                    onChange={(e) => updateQuestionText(qIdx, e.target.value)}
                    placeholder="Enter the question for students..."
                    className="w-full bg-surface border border-border focus:border-primary focus:outline-none rounded-lg p-2.5 text-text"
                  />
                </div>

                {/* Question Type Specific Body */}
                {q.question_type === 'multiple_choice' ? (
                  <div className="space-y-3 pt-1">
                    <div className="flex items-center justify-between">
                      <span className="text-[11px] font-bold text-text-muted uppercase tracking-wider">
                        Options (Mark exact 1 correct answer)
                      </span>
                      <button
                        type="button"
                        onClick={() => addOption(qIdx)}
                        className="text-primary font-bold hover:underline text-xs flex items-center gap-1 cursor-pointer"
                      >
                        <Plus className="w-3.5 h-3.5" />
                        <span>Add Option</span>
                      </button>
                    </div>

                    <div className="space-y-2">
                      {q.options.map((opt, optIdx) => (
                        <div
                          key={optIdx}
                          className="flex items-center gap-2 bg-surface p-2 rounded-xl border border-border"
                        >
                          <label className="flex items-center gap-1.5 cursor-pointer px-1">
                            <input
                              type="radio"
                              name={`correct_opt_${qIdx}`}
                              checked={opt.is_correct}
                              onChange={() => setCorrectOption(qIdx, optIdx)}
                              className="accent-primary w-4 h-4 cursor-pointer"
                            />
                            <span className={`text-[10px] font-bold px-2 py-0.5 rounded-full ${
                              opt.is_correct ? 'bg-emerald-100 text-emerald-800 border border-emerald-300' : 'bg-bg text-text-muted'
                            }`}>
                              {opt.is_correct ? 'Correct' : 'Choice'}
                            </span>
                          </label>

                          <input
                            type="text"
                            required
                            maxLength={500}
                            value={opt.option_text}
                            onChange={(e) => updateOptionText(qIdx, optIdx, e.target.value)}
                            placeholder={`Option ${optIdx + 1} text...`}
                            className="flex-1 bg-transparent border-none focus:outline-none text-xs text-text px-1"
                          />

                          <button
                            type="button"
                            disabled={q.options.length <= 2}
                            onClick={() => removeOption(qIdx, optIdx)}
                            className="text-text-muted hover:text-red-600 disabled:opacity-30 disabled:cursor-not-allowed cursor-pointer p-1 transition-colors"
                            title="Remove Option"
                          >
                            <Trash2 className="w-3.5 h-3.5" />
                          </button>
                        </div>
                      ))}
                    </div>
                  </div>
                ) : (
                  <div className="pt-1">
                    <label className="block font-bold text-text-muted mb-1">
                      Correct Answer Target (Case-insensitive comparison) *
                    </label>
                    <input
                      type="text"
                      required
                      maxLength={500}
                      value={q.correct_answer_text}
                      onChange={(e) => updateShortAnswerText(qIdx, e.target.value)}
                      placeholder="e.g. Photosynthesis or 42"
                      className="w-full bg-surface border border-border focus:border-primary focus:outline-none rounded-lg p-2.5 text-text font-semibold"
                    />
                  </div>
                )}
              </div>
            ))}

            {/* Add Question Button */}
            <button
              type="button"
              onClick={addQuestion}
              className="w-full py-2.5 border-2 border-dashed border-border hover:border-primary text-text-muted hover:text-primary font-bold rounded-2xl flex items-center justify-center gap-2 cursor-pointer transition-all bg-surface"
            >
              <Plus className="w-4 h-4" />
              <span>Add Another Question</span>
            </button>
          </div>

          {/* Form Actions Footer */}
          <div className="flex justify-end gap-3 pt-4 border-t border-border flex-shrink-0">
            <button
              type="button"
              onClick={handleResetAndClose}
              className="px-4 py-2 font-semibold text-text-muted hover:bg-bg rounded-lg cursor-pointer transition-colors"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={loading}
              className="px-5 py-2 font-semibold text-on-primary bg-primary hover:bg-primary-hover rounded-lg cursor-pointer shadow-xs transition-all disabled:opacity-60 disabled:cursor-not-allowed flex items-center gap-1.5"
            >
              <CheckCircle2 className="w-4 h-4" />
              <span>{loading ? 'Creating Quiz...' : 'Save & Publish Quiz'}</span>
            </button>
          </div>
        </form>

      </div>
    </div>
  );
};

export default CreateQuizModal;
