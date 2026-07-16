import { useState, type KeyboardEvent } from "react";

export function useCapsLockWarning() {
  const [isCapsLockOn, setIsCapsLockOn] = useState(false);

  const handleKeyEvent = (e: KeyboardEvent<HTMLInputElement>) => {
    setIsCapsLockOn(e.getModifierState("CapsLock"));
  };

  return { isCapsLockOn, handleKeyEvent };
}
