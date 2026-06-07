import type { ReactElement } from "react";
import { cloneElement } from "react";

type Position = "top" | "bottom" | "left" | "right";

interface Props {
  content: string;
  children: ReactElement;
  position?: Position;
  maxWidth?: string;
}

const POSITION_CLASSES: Record<Position, string> = {
  top: "bottom-full left-1/2 -translate-x-1/2 mb-2",
  bottom: "top-full left-1/2 -translate-x-1/2 mt-2",
  left: "right-full top-1/2 -translate-y-1/2 mr-2",
  right: "left-full top-1/2 -translate-y-1/2 ml-2",
};

export default function Tooltip({ content, children, position = "top", maxWidth = "max-w-xs" }: Props) {
  return (
    <span className="relative inline-flex group">
      {cloneElement(children, { tabIndex: 0 })}
      <span
        className={[
          "absolute z-50 px-2.5 py-1.5 text-xs text-white bg-gray-900 dark:bg-gray-700 rounded-lg shadow-lg",
          "pointer-events-none whitespace-normal",
          "opacity-0 group-hover:opacity-100 group-focus-within:opacity-100 transition-opacity duration-150",
          POSITION_CLASSES[position],
          maxWidth,
        ].join(" ")}
        role="tooltip"
      >
        {content}
      </span>
    </span>
  );
}
