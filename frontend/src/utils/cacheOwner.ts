import { PERSIST_CACHE_KEY } from "@/constants/queryConfig";
import { storageGet, storageRemove, storageSet } from "@/utils/safeStorage";

/** 쿼리 캐시(메모리 + localStorage 24h persist)를 마지막으로 채운 사용자 id. */
const CACHE_OWNER_KEY = "growlio:cache-owner";

/** 캐시 소유자가 바뀌었을 때 App이 queryClient를 비우도록 보내는 이벤트. */
export const CACHE_OWNER_CHANGED_EVENT = "growlio:cache-owner-changed";

/**
 * 로그인한 사용자를 캐시 소유자로 기록한다. 이전 소유자와 다르면 persist 캐시를 지우고 true를 돌려준다.
 *
 * 쿼리키에 user id가 없어서, 앱이 닫힌 사이 세션이 만료된 뒤 다른 사람이 같은 기기로 로그인하면
 * 이전 사용자의 대시보드·계좌 캐시가 그대로 복원돼 보였다(plans/61 B3). 소유자 기록이 없는데 persist
 * 캐시가 남아 있으면(이 기능 배포 전 캐시) 누구 것인지 알 수 없으므로 한 번 지운다.
 */
export function claimCacheOwner(userId: string): boolean {
  const previous = storageGet(CACHE_OWNER_KEY);
  storageSet(CACHE_OWNER_KEY, userId);
  const changed = previous ? previous !== userId : storageGet(PERSIST_CACHE_KEY) !== null;
  if (changed) storageRemove(PERSIST_CACHE_KEY);
  return changed;
}
