export const inputClass =
  "mt-1 w-full border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-50 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500";
export const labelClass = "text-sm font-medium text-gray-700 dark:text-gray-300";

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
    <div className="bg-white dark:bg-gray-900 rounded-2xl border border-gray-200 dark:border-gray-700 p-6 space-y-4">
      <div className="flex items-center gap-3">
        <h2 className="text-base font-semibold text-gray-800 dark:text-gray-200">{title}</h2>
        {badge}
      </div>
      {children}
    </div>
  );
}

export function ConnectedBadge() {
  return (
    <span className="text-xs bg-green-100 dark:bg-green-950 text-green-700 dark:text-green-400 px-2 py-0.5 rounded-full font-medium">
      연결됨
    </span>
  );
}
