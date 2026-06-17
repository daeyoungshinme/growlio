import { Loader2 } from "lucide-react";

export default function PageLoader() {
  return (
    <div
      role="status"
      aria-label="로딩 중"
      className="flex items-center justify-center min-h-[60vh]"
    >
      <Loader2 size={32} className="animate-spin text-blue-500" aria-hidden="true" />
    </div>
  );
}
