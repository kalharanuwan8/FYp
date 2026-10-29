/**
 * Quiz authoring for new quizzes is done via CreateQuizModal on the course editor.
 * This page remains as a pointer so older links do not break.
 */
import { useNavigate } from 'react-router-dom';
import { HelpCircle } from 'lucide-react';
import { Button, Card } from '../../components/common';

export default function QuizEditor() {
  const navigate = useNavigate();
  return (
    <div className="max-w-xl mx-auto space-y-4">
      <Card className="p-6 space-y-3">
        <div className="flex items-center gap-2 text-primary">
          <HelpCircle className="w-5 h-5" />
          <h1 className="font-display font-bold text-text">Quiz editor</h1>
        </div>
        <p className="text-sm text-text-muted">
          Create quizzes from a subject&apos;s course editor (+ Add Quiz). You can set a
          time limit, mark each question easy/medium/hard, and add a teacher hint.
        </p>
        <Button type="button" onClick={() => navigate('/teacher/courses')}>
          Go to courses
        </Button>
      </Card>
    </div>
  );
}
