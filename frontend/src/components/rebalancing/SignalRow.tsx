import type { SignalRowContent } from "@/utils/marketSignalRows";

interface Props {
  label: string;
  content: SignalRowContent | null;
}

export default function SignalRow({ label, content }: Props) {
  return (
    <div className="flex items-center gap-2">
      <span className="text-xs text-gray-500 dark:text-gray-400 w-20 shrink-0">{label}</span>
      {content ? (
        <>
          <span className={`w-2 h-2 rounded-full shrink-0 ${content.dotColor}`} />
          <span className="text-xs font-medium text-gray-700 dark:text-gray-300">
            {content.valueText}
          </span>
          <span className="text-xs text-gray-400 dark:text-gray-500 ml-auto text-right">
            {content.hintText}
          </span>
        </>
      ) : (
        <span className="text-xs text-gray-400">—</span>
      )}
    </div>
  );
}
