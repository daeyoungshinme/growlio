import { useEffect, useRef, useState } from "react";

interface Props {
  isVisible: boolean;
}

export default function TopLoadingBar({ isVisible }: Props) {
  const [width, setWidth] = useState(0);
  const [opacity, setOpacity] = useState(0);
  const completeTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    if (completeTimer.current) clearTimeout(completeTimer.current);

    if (isVisible) {
      // 0% → 즉시 시작, 다음 frame에서 85%로 느리게 진행
      const raf = requestAnimationFrame(() => {
        setOpacity(1);
        setWidth(0);
        requestAnimationFrame(() => {
          setWidth(85);
        });
      });
      return () => cancelAnimationFrame(raf);
    } else {
      // 완료: 100%로 즉시 채운 뒤 fade out
      const raf = requestAnimationFrame(() => {
        setWidth(100);
        completeTimer.current = setTimeout(() => {
          setOpacity(0);
          completeTimer.current = setTimeout(() => setWidth(0), 300);
        }, 150);
      });
      return () => {
        cancelAnimationFrame(raf);
        if (completeTimer.current) clearTimeout(completeTimer.current);
      };
    }
  }, [isVisible]);

  if (opacity === 0 && width === 0) return null;

  return (
    <div
      role="progressbar"
      aria-label="페이지 로딩 중"
      aria-busy={isVisible}
      style={{
        position: "fixed",
        top: 0,
        left: 0,
        width: `${width}%`,
        height: "2px",
        backgroundColor: "#6366f1", // indigo-500
        opacity,
        transition: isVisible
          ? "width 8s ease-out, opacity 0.15s"
          : "width 0.15s ease-in, opacity 0.3s 0.15s",
        zIndex: 9999,
        pointerEvents: "none",
      }}
    />
  );
}
