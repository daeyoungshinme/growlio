import { useEffect, useState } from "react";
import { createPortal } from "react-dom";
import type { StockSuggestion } from "@/api/assets";

interface SuggestionDropdownProps {
  rowIndex: number;
  suggestions: StockSuggestion[];
  anchorEl: HTMLInputElement | null;
  onSelect: (rowIndex: number, suggestion: StockSuggestion) => void;
}

const MAX_DROPDOWN_H = 208;

export function SuggestionDropdown({
  rowIndex,
  suggestions,
  anchorEl,
  onSelect,
}: SuggestionDropdownProps) {
  const [pos, setPos] = useState<{
    top?: number;
    bottom?: number;
    maxHeight: number;
    left: number;
    width: number;
  } | null>(null);

  useEffect(() => {
    if (!anchorEl) return;

    const update = () => {
      const rect = anchorEl.getBoundingClientRect();
      const vv = window.visualViewport;
      const vh = vv?.height ?? window.innerHeight;
      const vvOffsetTop = vv?.offsetTop ?? 0;
      const vvOffsetLeft = vv?.offsetLeft ?? 0;
      const layoutH = window.innerHeight;

      if (rect.top >= vh || rect.bottom <= 0) {
        setPos(null);
        return;
      }

      const spaceBelow = vh - rect.bottom;
      const spaceAbove = rect.top - 8;

      if (spaceBelow < 200) {
        const maxH = Math.min(MAX_DROPDOWN_H, Math.max(0, spaceAbove));
        setPos({
          bottom: layoutH - rect.top - vvOffsetTop + 4,
          maxHeight: maxH,
          left: rect.left + vvOffsetLeft,
          width: rect.width,
        });
      } else {
        setPos({
          top: rect.bottom + vvOffsetTop + 4,
          maxHeight: Math.min(MAX_DROPDOWN_H, spaceBelow - 8),
          left: rect.left + vvOffsetLeft,
          width: rect.width,
        });
      }
    };

    update();
    window.visualViewport?.addEventListener("resize", update);
    window.visualViewport?.addEventListener("scroll", update);
    return () => {
      window.visualViewport?.removeEventListener("resize", update);
      window.visualViewport?.removeEventListener("scroll", update);
    };
  }, [anchorEl]);

  if (!anchorEl || !pos) return null;

  return createPortal(
    <div
      role="listbox"
      aria-label="종목 검색 결과"
      style={{
        position: "fixed",
        zIndex: 9999,
        top: pos.top,
        bottom: pos.bottom,
        left: pos.left,
        width: pos.width,
        maxHeight: pos.maxHeight,
      }}
      className="bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg shadow-lg overflow-y-auto"
    >
      {suggestions.map((s, si) => (
        <button
          key={si}
          role="option"
          aria-selected={false}
          className="w-full flex items-center justify-between px-3 py-2.5 text-sm hover:bg-blue-50 dark:hover:bg-blue-950 text-left"
          onMouseDown={(e) => {
            e.preventDefault();
            onSelect(rowIndex, s);
          }}
        >
          <span className="flex flex-col">
            <span className="font-medium text-gray-900 dark:text-gray-50">{s.name}</span>
            <span className="text-gray-400 dark:text-gray-500 font-mono text-xs">{s.ticker}</span>
          </span>
          <span className="text-gray-400 dark:text-gray-500 bg-gray-100 dark:bg-gray-700 rounded px-2 py-0.5 ml-2 shrink-0 text-xs">
            {s.market}
          </span>
        </button>
      ))}
    </div>,
    document.body,
  );
}
