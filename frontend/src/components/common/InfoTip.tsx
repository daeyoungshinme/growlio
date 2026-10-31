import { Info } from "lucide-react";
import { useEffect, useId, useRef, useState, type ReactNode } from "react";
import { TOUCH_TARGET_COMPACT_MOBILE_ONLY } from "@/constants/uiSizes";

interface Props {
  /** 팝오버 본문 */
  content: ReactNode;
  /** 트리거 버튼의 접근성 이름 (예: "MDD 설명") */
  label: string;
  /** 트리거 내용 — 생략 시 ⓘ 아이콘. 지표 이름처럼 텍스트를 넘기면 점선 밑줄로 표시 */
  children?: ReactNode;
  className?: string;
}

const MAX_WIDTH = 256;
const GAP = 6;
const EDGE = 8;

interface Pos {
  left: number;
  top: number;
  width: number;
  above: boolean;
}

function computePos(rect: DOMRect): Pos {
  const vw = window.innerWidth;
  const width = Math.min(MAX_WIDTH, vw - EDGE * 2);
  const left = Math.min(Math.max(rect.left + rect.width / 2 - width / 2, EDGE), vw - width - EDGE);
  // 아래 공간이 부족하면 위로 — 하단 네비 근처 지표에서 팝오버가 잘리지 않게
  const above = rect.bottom + 120 > window.innerHeight;
  return { left, top: above ? rect.top - GAP : rect.bottom + GAP, width, above };
}

/** 탭으로 여는 설명 팝오버. `title`/hover 툴팁은 터치에서 보이지 않는다(frontend/CLAUDE.md 모바일 UI).
 * 바깥 탭·Esc·스크롤로 닫힌다. Esc는 캡처 단계에서 먼저 소비해 감싼 모달까지 닫히지 않게 한다. */
export default function InfoTip({ content, label, children, className = "" }: Props) {
  const [pos, setPos] = useState<Pos | null>(null);
  const btnRef = useRef<HTMLButtonElement>(null);
  const popRef = useRef<HTMLSpanElement>(null);
  const popId = useId();
  const open = pos !== null;

  useEffect(() => {
    if (!open) return;
    const close = () => setPos(null);
    const onPointerDown = (e: PointerEvent) => {
      const t = e.target as Node;
      if (btnRef.current?.contains(t) || popRef.current?.contains(t)) return;
      close();
    };
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key !== "Escape") return;
      e.stopPropagation();
      close();
      btnRef.current?.focus();
    };
    document.addEventListener("pointerdown", onPointerDown);
    window.addEventListener("keydown", onKeyDown, true);
    window.addEventListener("scroll", close, true);
    window.addEventListener("resize", close);
    return () => {
      document.removeEventListener("pointerdown", onPointerDown);
      window.removeEventListener("keydown", onKeyDown, true);
      window.removeEventListener("scroll", close, true);
      window.removeEventListener("resize", close);
    };
  }, [open]);

  const toggle = () => {
    if (open || !btnRef.current) {
      setPos(null);
      return;
    }
    setPos(computePos(btnRef.current.getBoundingClientRect()));
  };

  return (
    <>
      <button
        ref={btnRef}
        type="button"
        onClick={(e) => {
          // label 안에 있을 때 연결된 입력으로 포커스가 넘어가지 않게
          e.preventDefault();
          e.stopPropagation();
          toggle();
        }}
        aria-label={children ? undefined : label}
        aria-expanded={open}
        aria-controls={open ? popId : undefined}
        className={
          children
            ? `underline decoration-dotted decoration-gray-400 underline-offset-2 rounded ${className}`
            : `${TOUCH_TARGET_COMPACT_MOBILE_ONLY} -my-2 text-gray-400 hover:text-gray-600 dark:text-gray-500 dark:hover:text-gray-300 rounded ${className}`
        }
      >
        {children ?? <Info size={14} aria-hidden="true" />}
      </button>
      {pos && (
        <span
          ref={popRef}
          id={popId}
          role="tooltip"
          style={{
            left: pos.left,
            top: pos.top,
            width: pos.width,
            transform: pos.above ? "translateY(-100%)" : undefined,
          }}
          className="fixed z-[80] px-3 py-2 text-xs leading-relaxed font-normal text-left text-white bg-gray-900 dark:bg-gray-700 rounded-lg shadow-lg whitespace-normal break-keep"
        >
          {content}
        </span>
      )}
    </>
  );
}
