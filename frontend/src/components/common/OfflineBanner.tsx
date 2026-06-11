import { WifiOff } from "lucide-react";
import { useOnlineStatus } from "@/hooks/useOnlineStatus";

export default function OfflineBanner() {
  const online = useOnlineStatus();
  if (online) return null;
  return (
    <div
      role="alert"
      aria-live="polite"
      className="flex items-center gap-2 px-4 py-2 bg-amber-50 dark:bg-amber-900/20 border-b border-amber-200 dark:border-amber-700 text-sm text-amber-800 dark:text-amber-300 lg:hidden"
    >
      <WifiOff size={14} aria-hidden="true" />
      <span>오프라인 상태입니다. 일부 기능이 제한될 수 있습니다.</span>
    </div>
  );
}
