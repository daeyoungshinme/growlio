export default function SkeletonStatBox() {
  return (
    <div className="flex-1 text-center px-4">
      <div className="h-3 w-16 bg-gray-200 dark:bg-gray-700 rounded animate-pulse mx-auto mb-2" />
      <div className="h-6 w-24 bg-gray-200 dark:bg-gray-700 rounded animate-pulse mx-auto" />
    </div>
  );
}
