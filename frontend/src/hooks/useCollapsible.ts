import { useState } from "react";

export function useCollapsible(
  initialOpen: boolean | (() => boolean) = false,
  storageKey?: string,
): [boolean, () => void, (open: boolean) => void] {
  const [isOpen, setIsOpenState] = useState<boolean>(() => {
    const stored = storageKey ? localStorage.getItem(storageKey) : null;
    if (stored !== null) return stored === "true";
    return typeof initialOpen === "function" ? initialOpen() : initialOpen;
  });

  const setIsOpen = (open: boolean) => {
    if (storageKey) localStorage.setItem(storageKey, String(open));
    setIsOpenState(open);
  };

  const toggle = () => {
    setIsOpenState((v) => {
      const next = !v;
      if (storageKey) localStorage.setItem(storageKey, String(next));
      return next;
    });
  };

  return [isOpen, toggle, setIsOpen];
}
