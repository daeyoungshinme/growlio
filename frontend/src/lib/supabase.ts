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

// @supabase/supabase-js(약 200KB)를 top-level import하면 이 파일을 참조하는 모든 부팅 경로
// (authStore/api client)가 실제 렌더 전에 그 파싱·실행을 먼저 기다려야 해 모바일 저사양
// 기기에서 체감 로딩 지연을 유발했다 — 동적 import로 지연 로드하고 클라이언트를 메모이즈해
// 재사용한다. 호출부는 전부 async 함수라 `const supabase = await getSupabase();`로 치환 가능.
export function getSupabase(): Promise<SupabaseClient> {
  if (!clientPromise) {
    clientPromise = import("@supabase/supabase-js").then(({ createClient }) =>
      createClient(supabaseUrl, supabaseAnonKey, {
        auth: {
          autoRefreshToken: true,
          persistSession: true,
          detectSessionInUrl: true, // 비밀번호 재설정 이메일 링크 처리
        },
      }),
    );
  }
  return clientPromise;
}
