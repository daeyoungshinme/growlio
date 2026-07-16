/* eslint-disable react-refresh/only-export-components */
import { INPUT_SM, LABEL_MD } from "@/constants/inputStyles";
export const inputClass = `mt-1 w-full ${INPUT_SM}`;
export const labelClass = LABEL_MD;

export function SectionCard({
  title,
  badge,
  children,
}: {
  title: string;
  badge?: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <div className="bg-white dark:bg-gray-900 rounded-2xl border border-gray-200 dark:border-gray-700 p-5 space-y-4">
      <div className="flex items-center gap-3">
        <h2 className="text-base font-semibold text-gray-800 dark:text-gray-200">{title}</h2>
        {badge}
      </div>
      {children}
    </div>
  );
}

export function DeleteIcon() {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      className="w-4 h-4"
      fill="none"
      viewBox="0 0 24 24"
      stroke="currentColor"
    >
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
    </svg>
  );
}

export function ConnectedBadge() {
  return (
    <span className="text-xs bg-green-100 dark:bg-green-950 text-green-700 dark:text-green-400 px-2 py-0.5 rounded-full font-medium">
      연결됨
    </span>
  );
}
