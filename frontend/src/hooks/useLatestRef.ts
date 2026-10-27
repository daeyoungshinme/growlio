import { useLayoutEffect, useRef } from "react";

/**
 * 항상 최신 값을 가리키는 ref — 리스너를 한 번만 등록하고 콜백 안에서 최신 값을 읽을 때 쓴다.
 *
 * 예: react-router의 non-data `BrowserRouter`에서 `useNavigate()`는 경로가 바뀔 때마다 새 함수를 돌려준다.
 * 그 함수를 effect deps에 넣으면 화면 이동마다 네이티브 리스너 해제·재등록(푸시는 권한 요청·토큰 재등록까지)이 일어난다.
 */
export function useLatestRef<T>(value: T) {
  const ref = useRef(value);
  useLayoutEffect(() => {
    ref.current = value;
  });
  return ref;
}
