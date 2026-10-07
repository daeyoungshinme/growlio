import { Loader2 } from "lucide-react";

export default function GoalWizardLoading({ text }: { text: string }) {
  return (
    <div className="flex items-center gap-2 text-xs text-gray-400 dark:text-gray-500">
      <Loader2 size={14} className="animate-spin" /> {text}
    </div>
  );
}
