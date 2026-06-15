import { useState } from "react";
import { Pencil } from "lucide-react";

interface Props {
  name: string;
  onSave: (name: string) => void;
  className?: string;
  textClassName?: string;
  pencilSize?: number;
}

export default function EditableNameField({ name, onSave, className, textClassName, pencilSize = 14 }: Props) {
  const [editMode, setEditMode] = useState(false);
  const [value, setValue] = useState(name);

  const handleSave = () => {
    const trimmed = value.trim();
    if (trimmed) {
      onSave(trimmed);
      setEditMode(false);
    }
  };

  const handleCancel = () => {
    setEditMode(false);
    setValue(name);
  };

  if (editMode) {
    return (
      <div className={`flex items-center gap-1.5 ${className ?? ""}`}>
        <input
          type="text"
          value={value}
          autoFocus
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") handleSave();
            if (e.key === "Escape") handleCancel();
          }}
          className="border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-50 rounded-lg px-2 py-0.5 text-sm w-40 focus:outline-none focus:ring-2 focus:ring-blue-500"
        />
        <button onClick={handleSave} className="text-xs text-blue-600 dark:text-blue-400 hover:underline font-medium">저장</button>
        <button onClick={handleCancel} className="text-xs text-gray-400 dark:text-gray-500 hover:underline">취소</button>
      </div>
    );
  }

  return (
    <div className={`flex items-center gap-1.5 ${className ?? ""}`}>
      <span className={textClassName}>{name}</span>
      <button
        onClick={() => { setValue(name); setEditMode(true); }}
        title="계좌명 수정"
        aria-label="계좌명 수정"
        className="p-2.5 sm:p-1.5 text-gray-300 dark:text-gray-600 hover:text-blue-400 transition-colors shrink-0"
      >
        <Pencil size={pencilSize} />
      </button>
    </div>
  );
}
