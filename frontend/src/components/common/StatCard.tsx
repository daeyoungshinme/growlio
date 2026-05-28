const COLOR_CLASSES = {
  red: "text-red-500",
  green: "text-green-600",
  blue: "text-blue-600",
  gray: "text-gray-900 dark:text-gray-50",
} as const;

interface Props {
  label: string;
  value: string;
  sub?: string;
  color?: keyof typeof COLOR_CLASSES;
}

export default function StatCard({ label, value, sub, color = "gray" }: Props) {
  return (
    <div className="bg-white dark:bg-gray-900 rounded-2xl border border-gray-200 dark:border-gray-700 p-3 sm:p-5">
      <p className="text-xs text-gray-400 dark:text-gray-500 font-medium">{label}</p>
      <p className={`text-xl sm:text-2xl font-bold mt-1 leading-tight ${COLOR_CLASSES[color]}`}>{value}</p>
      {sub && <p className="text-xs text-gray-400 dark:text-gray-500 mt-1">{sub}</p>}
    </div>
  );
}
