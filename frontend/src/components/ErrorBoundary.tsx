import * as Sentry from "@sentry/react";
import { Component } from "react";
import type { ReactNode, ErrorInfo } from "react";

interface Props {
  children: ReactNode;
  /** "page" (default): full-height error view; "section": compact inline error */
  variant?: "page" | "section";
}

interface State {
  hasError: boolean;
  error: Error | null;
}

export default class ErrorBoundary extends Component<Props, State> {
  state: State = { hasError: false, error: null };

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("ErrorBoundary caught:", error, info.componentStack);
    Sentry.captureException(error, { extra: { componentStack: info.componentStack } });
  }

  render() {
    if (this.state.hasError) {
      const isDev = import.meta.env.DEV;
      if (this.props.variant === "section") {
        return (
          <div className="flex flex-col items-center justify-center gap-2 py-6 px-4 bg-gray-50 dark:bg-gray-800 rounded-2xl border border-gray-200 dark:border-gray-700">
            <p className="text-gray-500 dark:text-gray-400 text-sm">이 섹션을 불러올 수 없습니다.</p>
            {isDev && this.state.error && (
              <p className="text-xs text-red-400 bg-red-50 dark:bg-red-950 rounded p-2 max-w-xs text-center break-all">
                {this.state.error.message}
              </p>
            )}
            <button
              onClick={() => this.setState({ hasError: false, error: null })}
              className="text-xs text-blue-600 dark:text-blue-400 hover:underline"
            >
              다시 시도
            </button>
          </div>
        );
      }
      return (
        <div className="flex flex-col items-center justify-center h-64 gap-3 p-4">
          <p className="text-gray-500 dark:text-gray-400 text-sm text-center">
            페이지를 불러올 수 없습니다.
          </p>
          {isDev && this.state.error && (
            <p className="text-xs text-red-400 bg-red-50 dark:bg-red-950 rounded p-2 max-w-sm text-center break-all">
              {this.state.error.message}
            </p>
          )}
          <button
            onClick={() => window.location.reload()}
            className="px-4 py-1.5 text-sm bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors"
          >
            새로고침
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}
