"""
Supabase Auth 유저 마이그레이션 스크립트 (1회성 실행)

로컬 PostgreSQL의 기존 유저를 Supabase Auth에 동일한 UUID로 생성.
bcrypt 해시는 이전 불가 → 기존 유저는 비밀번호 재설정 필요.

사전 조건:
  1. Supabase DB에 alembic upgrade head 실행 완료
  2. Supabase DB에 users 테이블 데이터 복원 완료
  3. 아래 환경 변수 설정:
     - SOURCE_DATABASE_URL: 로컬 Docker PostgreSQL URL (asyncpg 형식)
     - SUPABASE_PROJECT_URL: https://xyzabc.supabase.co
     - SUPABASE_SERVICE_ROLE_KEY: Supabase Service Role Key

사용법:
  SOURCE_DATABASE_URL=postgresql://postgres:postgres@localhost:5432/growlio \
  SUPABASE_PROJECT_URL=https://xyzabc.supabase.co \
  SUPABASE_SERVICE_ROLE_KEY=eyJ... \
  python scripts/migrate_to_supabase.py [--send-reset-email]
"""

import asyncio
import os
import sys

import asyncpg
import httpx


SOURCE_DB = os.environ.get("SOURCE_DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/growlio")
SUPABASE_URL = os.environ["SUPABASE_PROJECT_URL"]
SERVICE_KEY = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
SEND_RESET_EMAIL = "--send-reset-email" in sys.argv

ADMIN_HEADERS = {
    "apikey": SERVICE_KEY,
    "Authorization": f"Bearer {SERVICE_KEY}",
    "Content-Type": "application/json",
}


async def create_supabase_user(client: httpx.AsyncClient, user: asyncpg.Record) -> bool:
    user_id = str(user["id"])
    email = user["email"]

    resp = await client.post(
        f"{SUPABASE_URL}/auth/v1/admin/users",
        headers=ADMIN_HEADERS,
        json={
            "id": user_id,
            "email": email,
            "email_confirm": True,
            "user_metadata": {
                "display_name": user["display_name"],
            },
        },
    )

    if resp.status_code in (200, 201):
        print(f"  OK  {email} (id={user_id})")
        return True
    elif resp.status_code == 422 and "already" in resp.text.lower():
        print(f"  SKIP (already exists)  {email}")
        return True
    else:
        print(f"  FAIL  {email} — HTTP {resp.status_code}: {resp.text[:200]}")
        return False


async def send_reset_email(client: httpx.AsyncClient, user_id: str, email: str) -> None:
    resp = await client.post(
        f"{SUPABASE_URL}/auth/v1/admin/users/{user_id}/recover",
        headers=ADMIN_HEADERS,
        json={},
    )
    if resp.status_code in (200, 201, 204):
        print(f"  RESET EMAIL SENT  {email}")
    else:
        print(f"  RESET EMAIL FAILED  {email} — HTTP {resp.status_code}: {resp.text[:200]}")


async def main() -> None:
    print("=== Supabase Auth 유저 마이그레이션 시작 ===\n")

    conn = await asyncpg.connect(SOURCE_DB)
    users = await conn.fetch(
        "SELECT id, email, display_name, is_active FROM users WHERE is_active = true ORDER BY created_at"
    )
    await conn.close()

    print(f"이전 대상 유저: {len(users)}명\n")

    success_count = 0
    fail_count = 0

    async with httpx.AsyncClient(timeout=30.0) as client:
        for user in users:
            ok = await create_supabase_user(client, user)
            if ok:
                success_count += 1
                if SEND_RESET_EMAIL:
                    await send_reset_email(client, str(user["id"]), user["email"])
            else:
                fail_count += 1

    print(f"\n=== 완료: 성공 {success_count}명, 실패 {fail_count}명 ===")
    if fail_count > 0:
        print("실패한 유저를 Supabase Dashboard에서 수동으로 확인하세요.")

    if not SEND_RESET_EMAIL:
        print("\n팁: --send-reset-email 플래그를 추가하면 비밀번호 재설정 이메일을 자동 발송합니다.")


if __name__ == "__main__":
    asyncio.run(main())
