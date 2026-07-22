import { useState } from "react";
import { Pencil } from "lucide-react";
import { INPUT_SM } from "@/constants/inputStyles";
import {
  TOUCH_TARGET_COMPACT_MOBILE_ONLY,
  TOUCH_TARGET_MIN_MOBILE_ONLY,
} from "@/constants/uiSizes";

interface Props {
  name: string;
  onSave: (name: string) => void;
  className?: string;
  textClassName?: string;
  pencilSize?: number;
}

export default function EditableNameField({
  name,
  onSave,
  className,
  textClassName,
  pencilSize = 14,
}: Props) {
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
      <div className={`flex flex-wrap items-center gap-1.5 ${className ?? ""}`}>
        <input
          type="text"
          value={value}
          autoFocus
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") handleSave();
            if (e.key === "Escape") handleCancel();
          }}
          className={`flex-1 min-w-0 ${INPUT_SM}`}
        />
        <button
          onClick={handleSave}
          className={`${TOUCH_TARGET_COMPACT_MOBILE_ONLY} px-2 text-xs text-blue-600 dark:text-blue-400 hover:underline font-medium`}
        >
          저장
        </button>
        <button
          onClick={handleCancel}
          className={`${TOUCH_TARGET_COMPACT_MOBILE_ONLY} px-2 text-xs text-gray-400 dark:text-gray-500 hover:underline`}
        >
          취소
        </button>
      </div>
    );
  }

  return (
    <div className={`flex items-center gap-1.5 ${className ?? ""}`}>
      <h3 className={textClassName}>{name}</h3>
      <button
        onClick={() => {
          setValue(name);
          setEditMode(true);
        }}
        title="계좌명 수정"
        aria-label="계좌명 수정"
        className={`${TOUCH_TARGET_MIN_MOBILE_ONLY} p-2.5 sm:p-1.5 text-gray-300 dark:text-gray-600 hover:text-blue-400 transition-colors shrink-0`}
      >
        <Pencil size={pencilSize} />
      </button>
    </div>
  );
}
