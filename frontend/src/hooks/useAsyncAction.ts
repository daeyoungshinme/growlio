import { useState } from "react";
import { extractErrorMessage } from "../utils/error";

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
      setError(extractErrorMessage(e));
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
