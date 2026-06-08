export default function SkeletonCard({ rows = 3, height = "h-4" }: { rows?: number; height?: string }) {
  return (
    <div className="card space-y-3">
      {Array.from({ length: rows }).map((_, i) => (
        <div key={i} className={`${height} bg-gray-200 dark:bg-gray-700 rounded animate-pulse`} style={{ width: `${80 - i * 10}%` }} />
      ))}
    </div>
  );
}
