import { createClient } from "@supabase/supabase-js";

const supabaseUrl = import.meta.env.VITE_SUPABASE_URL as string;
const supabaseAnonKey = import.meta.env.VITE_SUPABASE_ANON_KEY as string;

if (!supabaseUrl || !supabaseAnonKey) {
  throw new Error(
    "필수 환경변수가 설정되지 않았습니다: VITE_SUPABASE_URL, VITE_SUPABASE_ANON_KEY\n" +
      "frontend/.env 파일을 생성하고 값을 채워주세요 (.env.example 참고)",
  );
}

export const supabase = createClient(supabaseUrl, supabaseAnonKey, {
  auth: {
    autoRefreshToken: true,
    persistSession: true,
    detectSessionInUrl: true, // 비밀번호 재설정 이메일 링크 처리
  },
});
