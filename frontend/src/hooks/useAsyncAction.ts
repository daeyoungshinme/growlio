import { useState } from "react";

interface AsyncActionState {
  loading: boolean;
  error: string | null;
}

interface AsyncActionResult extends AsyncActionState {
  run: (fn: () => Promise<void>) => Promise<void>;
  reset: () => void;
}

export function useAsyncAction(): AsyncActionResult {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function run(fn: () => Promise<void>) {
    setLoading(true);
    setError(null);
    try {
      await fn();
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : "오류가 발생했습니다.";
      setError(msg);
    } finally {
      setLoading(false);
    }
  }

  function reset() {
    setLoading(false);
    setError(null);
  }

  return { loading, error, run, reset };
}
