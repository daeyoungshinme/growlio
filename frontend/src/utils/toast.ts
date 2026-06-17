import { triggerHaptic } from "@/hooks/useHaptic";

export type ToastType = "error" | "success" | "info";

export interface ToastEvent {
  message: string;
  type: ToastType;
  id: number;
}

let _seq = 0;

export function toast(message: string, type: ToastType = "error") {
  if (type === "success") void triggerHaptic("success");
  else if (type === "error") void triggerHaptic("error");

  window.dispatchEvent(
    new CustomEvent<ToastEvent>("growlio:toast", {
      detail: { message, type, id: ++_seq },
    }),
  );
}
