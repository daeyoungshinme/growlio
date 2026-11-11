import { afterEach, describe, expect, it, vi } from "vitest";
import { act, render } from "@testing-library/react";
import { useInView } from "@/hooks/useInView";

function Probe() {
  const [ref, inView] = useInView<HTMLDivElement>();
  return <div ref={ref}>{inView ? "visible" : "hidden"}</div>;
}

describe("useInView (plans/125 E6)", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("IntersectionObserver가 없으면 바로 보인다고 본다", () => {
    vi.stubGlobal("IntersectionObserver", undefined);
    const { container } = render(<Probe />);
    expect(container.textContent).toBe("visible");
  });

  it("교차가 일어나면 true가 되고 관찰을 끝낸다", () => {
    let callback: IntersectionObserverCallback = () => {};
    const disconnect = vi.fn();
    vi.stubGlobal(
      "IntersectionObserver",
      class {
        constructor(cb: IntersectionObserverCallback) {
          callback = cb;
        }
        observe() {}
        disconnect = disconnect;
      },
    );
    const { container } = render(<Probe />);
    expect(container.textContent).toBe("hidden");

    act(() => {
      callback([{ isIntersecting: true } as IntersectionObserverEntry], {} as IntersectionObserver);
    });
    expect(container.textContent).toBe("visible");
    expect(disconnect).toHaveBeenCalled();
  });
});
