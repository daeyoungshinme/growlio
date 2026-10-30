/** 백엔드 공용 페이지네이션(`PaginationDep`, limit 상한 500)의 최대 크기 */
const MAX_PAGE_SIZE = 500;
// 무한 루프 방지 상한 — 500 × 20 = 1만 건
const MAX_PAGES = 20;

/** skip/limit 목록 API를 끝까지 이어 받아 한 배열로 돌려준다.
 * 화면이 받은 목록 전체를 걸러 쓰거나 합계를 내는 곳에서 쓴다 — 기본 limit(100)만 받으면
 * 오래된 기록이 조용히 빠져 합계가 줄었다(plans/90 B2). */
export async function fetchAllPages<T>(
  fetchPage: (page: { skip: number; limit: number }) => Promise<T[]>,
  pageSize = MAX_PAGE_SIZE,
): Promise<T[]> {
  const all: T[] = [];
  for (let i = 0; i < MAX_PAGES; i++) {
    const page = await fetchPage({ skip: i * pageSize, limit: pageSize });
    all.push(...page);
    if (page.length < pageSize) break;
  }
  return all;
}
