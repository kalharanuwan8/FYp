import { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { 
  BookOpen, 
  Layers, 
  Plus, 
  ArrowLeft, 
  Archive, 
  Edit3, 
  FileText,
  Video,
  Lightbulb,
  FileUp,
  Trash2,
  HelpCircle,
  Shield,
} from 'lucide-react';
import { courseService } from '../../services/courseService';
import CreateModuleModal from '../../components/teacher/CreateModuleModal';
import EditModuleModal from '../../components/teacher/EditModuleModal';
import UploadMaterialModal from '../../components/teacher/UploadMaterialModal';
import EditMaterialModal from '../../components/teacher/EditMaterialModal';
import CreateQuizModal from '../../components/teacher/CreateQuizModal';
import InterventionSettings from './InterventionSettings';
import { ConfirmDialog } from '../../components/common';

export const CourseEditor = () => {
  const { id } = useParams();
  const navigate = useNavigate();

  const [subject, setSubject] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const [createModuleModalOpen, setCreateModuleModalOpen] = useState(false);
  const [editModuleModalOpen, setEditModuleModalOpen] = useState(false);
  const [uploadMaterialModalOpen, setUploadMaterialModalOpen] = useState(false);
  const [editMaterialModalOpen, setEditMaterialModalOpen] = useState(false);
  const [createQuizModalOpen, setCreateQuizModalOpen] = useState(false);

  const [activeModule, setActiveModule] = useState(null);
  const [activeMaterial, setActiveMaterial] = useState(null);
  const [materialToDelete, setMaterialToDelete] = useState(null);
  const [actionError, setActionError] = useState(null);

  const fetchSubjectDetails = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await courseService.getSubjectDetail(id);
      setSubject(data);
    } catch (err) {
      setError(err.response?.data?.error || 'Failed to load course details');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (id) {
      fetchSubjectDetails();
    }
  }, [id]);

  const handleToggleArchive = async () => {
    if (!subject) return;
    try {
      const updated = await courseService.archiveSubject(subject.id, !subject.is_archived);
      setSubject(updated);
    } catch (err) {
      setActionError(err.response?.data?.error || 'Failed to toggle archive status');
    }
  };

  const handleOpenEditModule = (mod) => {
    setActiveModule(mod);
    setEditModuleModalOpen(true);
  };

  const handleOpenAddMaterial = (mod) => {
    setActiveModule(mod);
    setUploadMaterialModalOpen(true);
  };

  const handleOpenEditMaterial = (cnt) => {
    if (cnt.content_type === 'quiz') {
      setActionError('Quiz items are managed via + Add Quiz. Material edit is for documents/videos.');
      return;
    }
    setActiveMaterial(cnt);
    setEditMaterialModalOpen(true);
  };

  const handleOpenAddQuiz = (mod) => {
    setActiveModule(mod);
    setCreateQuizModalOpen(true);
  };

  const handleDeleteMaterial = async () => {
    if (!materialToDelete) return;
    try {
      await courseService.deleteMaterial(materialToDelete);
      setMaterialToDelete(null);
      fetchSubjectDetails();
    } catch (err) {
      setMaterialToDelete(null);
      setActionError(err.response?.data?.error || 'Failed to delete material');
    }
  };

  if (loading) {
    return (
      <div className="bg-surface border border-border/80 rounded-2xl p-12 text-center text-xs text-text-muted max-w-5xl mx-auto font-sans">
        Loading course editor...
      </div>
    );
  }

  if (error || !subject) {
    return (
      <div className="space-y-4 max-w-5xl mx-auto font-sans">
        <button
          onClick={() => navigate('/teacher/courses')}
          className="text-xs font-bold text-primary hover:underline flex items-center gap-1.5"
        >
          <ArrowLeft className="w-4 h-4" />
          <span>Back to Courses</span>
        </button>
        <div className="bg-red-50 border border-red-200 text-red-700 text-xs p-6 rounded-2xl">
          {error || 'Course not found'}
        </div>
      </div>
    );
  }

  const modules = subject.modules || [];
  const nextSequence = modules.length > 0 ? Math.max(...modules.map((m) => m.sequence_order)) + 1 : 1;

  const renderMaterialIcon = (type) => {
    switch (type) {
      case 'video':
        return <Video className="w-4 h-4 text-purple-600" />;
      case 'quiz':
        return <HelpCircle className="w-4 h-4 text-emerald-600" />;
      case 'other':
        return <Lightbulb className="w-4 h-4 text-amber-600" />;
      default:
        return <FileText className="w-4 h-4 text-primary" />;
    }
  };

  return (
    <div className="space-y-8 max-w-5xl mx-auto font-sans">
      {/* Top Navigation */}
      <button
        onClick={() => navigate('/teacher/courses')}
        className="text-xs font-bold text-text-muted hover:text-text flex items-center gap-1.5 transition-colors cursor-pointer"
      >
        <ArrowLeft className="w-4 h-4" />
        <span>Back to My Courses</span>
      </button>

      {actionError && (
        <p role="alert" className="bg-danger/10 border border-danger text-danger text-sm font-medium p-4 rounded-2xl">
          {actionError}
        </p>
      )}

      {/* Subject Header Card */}
      <div className="bg-surface border border-border/80 rounded-2xl p-6 md:p-8 shadow-xs space-y-4">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-border pb-6">
          <div>
            <div className="flex items-center gap-2.5 mb-2">
              <span className="text-xs font-extrabold text-primary bg-primary-soft px-3 py-1 rounded-full border border-primary/30 shadow-2xs">
                🎯 Target Audience: {subject.grade_level_name || 'Standard Grade'}
              </span>
              <span className={`text-[11px] font-bold px-2.5 py-0.5 rounded-full ${
                subject.is_archived ? 'bg-bg text-text-muted' : 'bg-emerald-50 text-emerald-700 border border-emerald-200'
              }`}>
                {subject.is_archived ? 'Archived' : 'Active'}
              </span>
            </div>
            <h1 className="text-2xl font-bold text-text tracking-tight">
              {subject.title}
            </h1>
            <p className="text-xs text-text-muted font-medium mt-1 leading-relaxed max-w-2xl">
              {subject.description || 'No course description provided.'}
            </p>
          </div>

          <div className="flex items-center gap-3">
            <button
              onClick={handleToggleArchive}
              className={`text-xs font-semibold px-3.5 py-2 rounded-xl border flex items-center gap-1.5 transition-all cursor-pointer ${
                subject.is_archived
                  ? 'border-emerald-300 text-emerald-700 hover:bg-emerald-50'
                  : 'border-border text-text-muted hover:bg-bg'
              }`}
            >
              <Archive className="w-4 h-4" />
              <span>{subject.is_archived ? 'Unarchive' : 'Archive'}</span>
            </button>
          </div>
        </div>

        {/* Summary Bar */}
        <div className="grid grid-cols-3 gap-4 pt-2 text-xs font-medium text-text-muted">
          <div>
            <span className="text-text-muted block text-[11px]">Total Modules</span>
            <span className="font-bold text-text text-base">{modules.length}</span>
          </div>
          <div>
            <span className="text-text-muted block text-[11px]">Grade Audience</span>
            <span className="font-bold text-primary text-base">{subject.grade_level_name || 'All'}</span>
          </div>
          <div>
            <span className="text-text-muted block text-[11px]">Status</span>
            <span className="font-bold text-text text-base">{subject.is_archived ? 'Archived' : 'Published'}</span>
          </div>
        </div>
      </div>

      {/* Intervention tier settings */}
      <div className="space-y-3">
        <h2 className="text-sm font-bold text-text flex items-center gap-2">
          <Shield className="w-4 h-4 text-primary" />
          Focus interventions
        </h2>
        <InterventionSettings subjectId={subject.id} />
      </div>

      {/* Modules Syllabus & Content Section */}
      <div className="space-y-4">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-lg font-bold text-text tracking-tight flex items-center gap-2">
              <Layers className="w-5 h-5 text-primary" />
              <span>Course Syllabus Modules</span>
            </h2>
            <p className="text-xs text-text-muted font-medium">
              Create and manage topic modules and content materials for this grade level.
            </p>
          </div>

          <button
            onClick={() => setCreateModuleModalOpen(true)}
            className="bg-primary hover:bg-primary-hover text-on-primary text-xs font-semibold py-2.5 px-4 rounded-xl flex items-center gap-2 shadow-xs transition-all cursor-pointer"
          >
            <Plus className="w-4 h-4" />
            <span>Add Module</span>
          </button>
        </div>

        {modules.length === 0 ? (
          <div className="bg-surface border border-border/80 rounded-2xl p-10 text-center text-xs text-text-muted space-y-3">
            <Layers className="w-8 h-8 text-text-muted mx-auto" />
            <p>No modules created for this course yet.</p>
            <button
              onClick={() => setCreateModuleModalOpen(true)}
              className="text-xs font-bold text-primary hover:underline"
            >
              + Create the first module
            </button>
          </div>
        ) : (
          <div className="space-y-4">
            {modules.map((mod) => {
              const contents = mod.contents || [];

              return (
                <div
                  key={mod.id}
                  className="bg-surface border border-border/80 rounded-2xl p-6 shadow-xs space-y-4 hover:border-border transition-all"
                >
                  {/* Module Header */}
                  <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-border pb-4">
                    <div className="flex items-start gap-4">
                      <div className="w-9 h-9 rounded-xl bg-primary/10 text-primary font-bold text-xs flex items-center justify-center border border-primary/20">
                        #{mod.sequence_order}
                      </div>
                      <div>
                        <h3 className="font-bold text-text text-base">
                          {mod.title}
                        </h3>
                        <p className="text-xs text-text-muted font-medium leading-relaxed">
                          {mod.description || 'No module description.'}
                        </p>
                      </div>
                    </div>

                    <div className="flex items-center gap-2 text-xs">
                      <button
                        onClick={() => handleOpenAddQuiz(mod)}
                        className="px-3 py-1.5 rounded-lg bg-emerald-50 text-emerald-700 border border-emerald-200 font-bold hover:bg-emerald-100 flex items-center gap-1.5 cursor-pointer transition-all"
                      >
                        <HelpCircle className="w-3.5 h-3.5 text-emerald-600" />
                        <span>+ Add Quiz</span>
                      </button>

                      <button
                        onClick={() => handleOpenAddMaterial(mod)}
                        className="px-3 py-1.5 rounded-lg bg-primary-soft text-primary border border-primary/30 font-bold hover:bg-primary-soft flex items-center gap-1.5 cursor-pointer transition-all"
                      >
                        <FileUp className="w-3.5 h-3.5" />
                        <span>+ Add Material</span>
                      </button>

                      <button
                        onClick={() => handleOpenEditModule(mod)}
                        className="px-3 py-1.5 rounded-lg border border-border text-text-muted hover:bg-bg font-bold flex items-center gap-1.5 cursor-pointer transition-all"
                        title="Edit Module"
                      >
                        <Edit3 className="w-3.5 h-3.5" />
                        <span>Edit</span>
                      </button>
                    </div>
                  </div>

                  {/* Module Content Materials List */}
                  <div className="space-y-2">
                    <span className="text-[11px] font-bold text-text-muted uppercase tracking-wider block">
                      Module Content ({contents.length})
                    </span>

                    {contents.length === 0 ? (
                      <div className="text-[11px] text-text-muted font-medium italic bg-bg/70 p-3 rounded-xl border border-dashed border-border">
                        No content materials attached to this module yet. Click "+ Add Quiz" or "+ Add Material" to attach learning items.
                      </div>
                    ) : (
                      <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5">
                        {contents.map((cnt) => (
                          <div
                            key={cnt.id}
                            className="bg-bg border border-border/70 p-3 rounded-xl flex items-center justify-between gap-3 text-xs"
                          >
                            <div className="flex items-center gap-2.5 min-w-0">
                              <div className="p-1.5 bg-surface rounded-lg border border-border shadow-2xs">
                                {renderMaterialIcon(cnt.content_type)}
                              </div>
                              <div className="min-w-0">
                                <span className="font-bold text-text truncate block">
                                  {cnt.title}
                                </span>
                                <span className="text-[10px] text-text-muted font-medium capitalize truncate block">
                                  {cnt.content_type} {cnt.file_url ? `• ${cnt.file_url}` : ''}
                                </span>
                              </div>
                            </div>

                            <div className="flex items-center gap-1 shrink-0">
                              {cnt.content_type !== 'quiz' && (
                                <button
                                  onClick={() => handleOpenEditMaterial(cnt)}
                                  className="text-text-muted hover:text-primary p-1 cursor-pointer transition-colors"
                                  title="Edit Material"
                                >
                                  <Edit3 className="w-3.5 h-3.5" />
                                </button>
                              )}
                              <button
                                onClick={() => setMaterialToDelete(cnt.id)}
                                className="text-text-muted hover:text-red-600 p-1 cursor-pointer transition-colors"
                                title="Delete Content"
                              >
                                <Trash2 className="w-3.5 h-3.5" />
                              </button>
                            </div>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* Create Module Modal */}
      <CreateModuleModal
        isOpen={createModuleModalOpen}
        subjectId={subject.id}
        nextSequence={nextSequence}
        onClose={() => setCreateModuleModalOpen(false)}
        onSuccess={fetchSubjectDetails}
      />

      {/* Edit Module Modal */}
      <EditModuleModal
        isOpen={editModuleModalOpen}
        moduleData={activeModule}
        onClose={() => {
          setEditModuleModalOpen(false);
          setActiveModule(null);
        }}
        onSuccess={fetchSubjectDetails}
      />

      {/* Upload Material Modal */}
      {activeModule && (
        <UploadMaterialModal
          isOpen={uploadMaterialModalOpen}
          moduleId={activeModule.id}
          onClose={() => {
            setUploadMaterialModalOpen(false);
            setActiveModule(null);
          }}
          onSuccess={fetchSubjectDetails}
        />
      )}

      {/* Edit Material Modal */}
      <EditMaterialModal
        isOpen={editMaterialModalOpen}
        material={activeMaterial}
        onClose={() => {
          setEditMaterialModalOpen(false);
          setActiveMaterial(null);
        }}
        onSuccess={fetchSubjectDetails}
      />

      <ConfirmDialog
        open={materialToDelete !== null}
        onClose={() => setMaterialToDelete(null)}
        onConfirm={handleDeleteMaterial}
        title="Delete this material?"
        description="This removes the material from the module. Students will no longer see it."
        confirmLabel="Delete material"
      />

      {/* Create Quiz Modal */}
      {activeModule && (
        <CreateQuizModal
          isOpen={createQuizModalOpen}
          moduleId={activeModule.id}
          onClose={() => {
            setCreateQuizModalOpen(false);
            setActiveModule(null);
          }}
          onSuccess={fetchSubjectDetails}
        />
      )}
    </div>
  );
};

export default CourseEditor;
