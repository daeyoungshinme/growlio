interface Props {
  title: string;
  value: string;
  subtitle: string;
  color: "blue" | "green" | "red" | "purple";
}

const colorMap = {
  blue: "text-blue-600 dark:text-blue-400",
  green: "text-green-600 dark:text-green-400",
  red: "text-red-600 dark:text-red-400",
  purple: "text-purple-600 dark:text-purple-400",
};

export default function StatCard({ title, value, subtitle, color }: Props) {
  return (
    <div className="bg-white dark:bg-gray-900 rounded-2xl border border-gray-200 dark:border-gray-700 p-5">
      <p className="text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wide mb-1">{title}</p>
      <p className={`text-2xl font-bold ${colorMap[color]} mt-1`}>{value}</p>
      <p className="text-xs text-gray-400 dark:text-gray-500 mt-1">{subtitle}</p>
    </div>
  );
}
