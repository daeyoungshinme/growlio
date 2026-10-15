import type { SupabaseClient } from "@supabase/supabase-js";

const supabaseUrl = import.meta.env.VITE_SUPABASE_URL as string;
const supabaseAnonKey = import.meta.env.VITE_SUPABASE_ANON_KEY as string;

if (!supabaseUrl || !supabaseAnonKey) {
  throw new Error(
    "필수 환경변수가 설정되지 않았습니다: VITE_SUPABASE_URL, VITE_SUPABASE_ANON_KEY\n" +
      "frontend/.env 파일을 생성하고 값을 채워주세요 (.env.example 참고)",
  );
}

let clientPromise: Promise<SupabaseClient> | null = null;

// detectSessionInUrl은 클라이언트 초기화 중에 PASSWORD_RECOVERY를 딱 한 번 발생시킨다. 재설정 페이지는
// 지연 청크라 구독 시점에 이미 지나갔을 수 있으므로(부팅 시 api/client가 먼저 클라이언트를 만든다),
// 클라이언트 생성 직후 등록한 리스너로 기록해 둔다. 로그인 세션만으로는 재설정 화면을 열지 않기 위함.
let passwordRecoveryDetected = false;

export function wasPasswordRecoveryDetected(): boolean {
  return passwordRecoveryDetected;
}

// @supabase/supabase-js(약 200KB)를 top-level import하면 이 파일을 참조하는 모든 부팅 경로
// (authStore/api client)가 실제 렌더 전에 그 파싱·실행을 먼저 기다려야 해 모바일 저사양
// 기기에서 체감 로딩 지연을 유발했다 — 동적 import로 지연 로드하고 클라이언트를 메모이즈해
// 재사용한다. 호출부는 전부 async 함수라 `const supabase = await getSupabase();`로 치환 가능.
export function getSupabase(): Promise<SupabaseClient> {
  if (!clientPromise) {
    clientPromise = import("@supabase/supabase-js").then(({ createClient }) => {
      const client = createClient(supabaseUrl, supabaseAnonKey, {
        auth: {
          autoRefreshToken: true,
          persistSession: true,
          detectSessionInUrl: true, // 비밀번호 재설정 이메일 링크 처리
        },
      });
      // 초기화(URL 세션 감지)는 비동기라 동기적으로 등록한 이 리스너가 이벤트를 놓치지 않는다
      client.auth.onAuthStateChange((event) => {
        if (event === "PASSWORD_RECOVERY") passwordRecoveryDetected = true;
      });
      return client;
    });
  }
  return clientPromise;
}
