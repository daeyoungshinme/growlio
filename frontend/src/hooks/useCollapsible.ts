import { useState } from "react";

export function useCollapsible(
  initialOpen: boolean | (() => boolean) = false,
): [boolean, () => void, (open: boolean) => void] {
  const [isOpen, setIsOpen] = useState(initialOpen);
  const toggle = () => setIsOpen((v) => !v);
  return [isOpen, toggle, setIsOpen];
}
