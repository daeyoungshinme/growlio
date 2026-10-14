import { useCallback, useState } from "react";
import { storageGet, storageSet } from "@/utils/safeStorage";

/**
 * 접힘/펼침 상태. `storageKey`를 주면 localStorage에 기억한다.
 * 반환하는 toggle·setIsOpen은 참조가 고정돼 effect 의존성에 넣어도 된다.
 */
export function useCollapsible(
  initialOpen: boolean | (() => boolean) = false,
  storageKey?: string,
): [boolean, () => void, (open: boolean) => void] {
  const [isOpen, setIsOpenState] = useState<boolean>(() => {
    const stored = storageKey ? storageGet(storageKey) : null;
    if (stored !== null) return stored === "true";
    return typeof initialOpen === "function" ? initialOpen() : initialOpen;
  });

  const setIsOpen = useCallback(
    (open: boolean) => {
      if (storageKey) storageSet(storageKey, String(open));
      setIsOpenState(open);
    },
    [storageKey],
  );

  const toggle = useCallback(() => {
    setIsOpenState((v) => {
      const next = !v;
      if (storageKey) storageSet(storageKey, String(next));
      return next;
    });
  }, [storageKey]);

  return [isOpen, toggle, setIsOpen];
}
