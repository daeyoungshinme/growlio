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
  size?: "default" | "sm";
  className?: string;
}

export default function StatCard({ label, value, sub, color = "gray", size = "default", className }: Props) {
  const isSm = size === "sm";
  return (
    <div className={`bg-white dark:bg-gray-900 rounded-2xl border border-gray-200 dark:border-gray-700 ${isSm ? "p-3" : "p-3 sm:p-5"} ${className ?? ""}`}>
      <p className="text-[11px] tracking-wide uppercase font-semibold text-gray-400 dark:text-gray-500">{label}</p>
      <p className={`${isSm ? "text-sm sm:text-base" : "text-xl sm:text-2xl"} font-bold mt-1 leading-tight ${COLOR_CLASSES[color]}`}>{value}</p>
      {sub && <p className="text-xs text-gray-400 dark:text-gray-500 mt-1">{sub}</p>}
    </div>
  );
}
