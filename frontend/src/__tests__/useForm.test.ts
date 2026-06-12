import { describe, it, expect } from "vitest";
import { renderHook, act } from "@testing-library/react";
import { useForm } from "@/hooks/useForm";

describe("useForm", () => {
  it("초기값이 form 상태로 설정된다", () => {
    const initial = { name: "", age: 0 };
    const { result } = renderHook(() => useForm(initial));
    expect(result.current.form).toEqual(initial);
  });

  it("set 함수로 특정 필드를 업데이트한다", () => {
    const { result } = renderHook(() => useForm({ name: "", age: 0 }));
    act(() => {
      result.current.set("name", "홍길동");
    });
    expect(result.current.form.name).toBe("홍길동");
    expect(result.current.form.age).toBe(0);
  });

  it("set 함수로 숫자 필드를 업데이트한다", () => {
    const { result } = renderHook(() => useForm({ name: "", age: 0 }));
    act(() => {
      result.current.set("age", 30);
    });
    expect(result.current.form.age).toBe(30);
  });

  it("reset 함수가 초기값으로 되돌린다", () => {
    const initial = { name: "", age: 0 };
    const { result } = renderHook(() => useForm(initial));
    act(() => {
      result.current.set("name", "홍길동");
      result.current.set("age", 30);
    });
    act(() => {
      result.current.reset();
    });
    expect(result.current.form).toEqual(initial);
  });

  it("setForm으로 전체 상태를 교체한다", () => {
    const { result } = renderHook(() => useForm({ name: "", age: 0 }));
    act(() => {
      result.current.setForm({ name: "홍길동", age: 30 });
    });
    expect(result.current.form).toEqual({ name: "홍길동", age: 30 });
  });

  it("여러 set 호출이 순서대로 적용된다", () => {
    const { result } = renderHook(() => useForm({ a: 1, b: 2, c: 3 }));
    act(() => {
      result.current.set("a", 10);
      result.current.set("b", 20);
    });
    expect(result.current.form.a).toBe(10);
    expect(result.current.form.b).toBe(20);
    expect(result.current.form.c).toBe(3);
  });

  it("타입에 맞는 다양한 값 타입을 지원한다", () => {
    const initial = { flag: false, count: 0, text: "" };
    const { result } = renderHook(() => useForm(initial));
    act(() => {
      result.current.set("flag", true);
    });
    expect(result.current.form.flag).toBe(true);
  });
});
