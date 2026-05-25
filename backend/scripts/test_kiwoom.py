"""키움증권 OpenAPI+ 순차 연결 테스트 스크립트.

사용법 (backend/ 디렉터리에서 실행):

  # DB에서 계좌 정보 자동 로드
  .venv/Scripts/python.exe scripts/test_kiwoom.py --account-id <UUID>

  # 자격증명 직접 입력 (DB 불필요)
  .venv/Scripts/python.exe scripts/test_kiwoom.py \\
      --app-key <APP_KEY> --app-secret <APP_SECRET> \\
      --account-no 53845567 --real

각 단계(STEP 1~5)가 순서대로 실행되며 raw request/response를 출력한다.
"""
import argparse
import asyncio
import json
import os
import sys

import httpx

# ---------------------------------------------------------------------------
# CLI 인자 파싱
# ---------------------------------------------------------------------------

parser = argparse.ArgumentParser(description="키움 API 순차 테스트")
parser.add_argument("--account-id", help="AssetAccount UUID (DB 로드 모드)")
parser.add_argument("--app-key", help="키움 App Key (직접 입력 모드)")
parser.add_argument("--app-secret", help="키움 App Secret (직접 입력 모드)")
parser.add_argument("--account-no", help="키움 계좌번호 (예: 53845567)")
parser.add_argument("--real", action="store_true", help="실계좌 모드 (기본값: 모의)")
args = parser.parse_args()

REAL_BASE_URL = "https://api.kiwoom.com"
MOCK_BASE_URL = "https://mockapi.kiwoom.com"


# ---------------------------------------------------------------------------
# 유틸
# ---------------------------------------------------------------------------

def _mask(s: str) -> str:
    if not s:
        return "(없음)"
    return s[:4] + "****" + s[-4:] if len(s) > 8 else "****"


def _print_step(n: int, title: str) -> None:
    print(f"\n{'='*60}")
    print(f"  STEP {n}: {title}")
    print(f"{'='*60}")


def _print_req(method: str, url: str, body: dict | None = None) -> None:
    print(f"▶ {method} {url}")
    if body:
        safe = {k: (_mask(str(v)) if k in ("appkey", "secretkey", "appsecret") else v) for k, v in body.items()}
        print(f"  Request body: {json.dumps(safe, ensure_ascii=False)}")


def _print_resp(resp: httpx.Response) -> None:
    print(f"◀ Status: {resp.status_code}")
    try:
        data = resp.json()
        print(f"  Response: {json.dumps(data, ensure_ascii=False, indent=2)}")
    except Exception:
        print(f"  Response (text): {resp.text[:500]}")


# ---------------------------------------------------------------------------
# STEP 1: 자격증명 수집
# ---------------------------------------------------------------------------

async def step1_get_credentials() -> tuple[str, str, str, bool]:
    """(app_key, app_secret, account_no, is_mock) 반환."""
    _print_step(1, "자격증명 수집")

    if args.app_key and args.app_secret and args.account_no:
        app_key = args.app_key
        app_secret = args.app_secret
        account_no = args.account_no
        is_mock = not args.real
        print(f"  모드: {'직접 입력'}")
        print(f"  App Key: {_mask(app_key)}")
        print(f"  App Secret: {_mask(app_secret)}")
        print(f"  계좌번호: {account_no}")
        print(f"  is_mock: {is_mock}")
        return app_key, app_secret, account_no, is_mock

    if args.account_id:
        print(f"  DB에서 계좌 로드: {args.account_id}")
        # 프로젝트 루트를 sys.path에 추가
        backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        sys.path.insert(0, backend_dir)

        # 환경 변수 로드
        from dotenv import load_dotenv
        load_dotenv(os.path.join(backend_dir, ".env"))

        from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
        from sqlalchemy.orm import sessionmaker
        from sqlalchemy import select

        engine = create_async_engine(os.environ["DATABASE_URL"])
        async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

        async with async_session() as db:
            from app.models.asset import AssetAccount
            from app.services.credential_service import decrypt

            row = await db.scalar(select(AssetAccount).where(AssetAccount.id == args.account_id))
            if not row:
                print(f"  ❌ account_id={args.account_id} 를 찾을 수 없음")
                sys.exit(1)

            print(f"  계좌명: {row.name}")
            print(f"  data_source: {row.data_source}")
            print(f"  asset_type: {row.asset_type}")
            print(f"  is_mock_mode: {row.is_mock_mode}")
            print(f"  kiwoom_account_no: {row.kiwoom_account_no}")

            if not row.kiwoom_app_key or not row.kiwoom_app_secret:
                print("  ❌ kiwoom_app_key / kiwoom_app_secret 가 비어있음")
                sys.exit(1)

            app_key = decrypt(row.kiwoom_app_key)
            app_secret = decrypt(row.kiwoom_app_secret)
            account_no = row.kiwoom_account_no or ""
            is_mock = row.is_mock_mode

            print(f"  App Key (복호화): {_mask(app_key)} (길이 {len(app_key)})")
            print(f"  App Secret (복호화): {_mask(app_secret)} (길이 {len(app_secret)})")

        await engine.dispose()
        return app_key, app_secret, account_no, is_mock

    print("  ❌ --account-id 또는 (--app-key + --app-secret + --account-no) 중 하나를 입력하세요")
    parser.print_help()
    sys.exit(1)


# ---------------------------------------------------------------------------
# STEP 2: 자격증명 유효성 확인
# ---------------------------------------------------------------------------

def step2_validate(app_key: str, app_secret: str, account_no: str, is_mock: bool) -> None:
    _print_step(2, "자격증명 유효성 확인")
    ok = True
    if len(app_key) < 10:
        print(f"  ⚠️  App Key 길이가 너무 짧음: {len(app_key)}자")
        ok = False
    else:
        print(f"  ✅ App Key 길이: {len(app_key)}자")

    if len(app_secret) < 10:
        print(f"  ⚠️  App Secret 길이가 너무 짧음: {len(app_secret)}자")
        ok = False
    else:
        print(f"  ✅ App Secret 길이: {len(app_secret)}자")

    if not account_no:
        print("  ⚠️  계좌번호가 없음")
        ok = False
    else:
        print(f"  ✅ 계좌번호: {account_no}")

    base_url = MOCK_BASE_URL if is_mock else REAL_BASE_URL
    print(f"  ℹ️  Base URL: {base_url} ({'모의' if is_mock else '실계좌'})")

    if not ok:
        print("  ❌ 자격증명 검증 실패 — 계속 진행하지만 API 호출도 실패할 가능성 높음")


# ---------------------------------------------------------------------------
# STEP 3: OAuth2 토큰 발급
# ---------------------------------------------------------------------------

async def step3_get_token(app_key: str, app_secret: str, is_mock: bool) -> str | None:
    _print_step(3, "OAuth2 토큰 발급")
    base_url = MOCK_BASE_URL if is_mock else REAL_BASE_URL
    url = f"{base_url}/oauth2/token"
    body = {
        "grant_type": "client_credentials",
        "appkey": app_key,
        "secretkey": app_secret,
    }

    _print_req("POST", url, body)

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(url, json=body, headers={"Content-Type": "application/json;charset=UTF-8"})
        _print_resp(resp)

        if resp.status_code >= 400:
            print(f"\n  ❌ HTTP {resp.status_code} 오류")
            print("  → 원인 후보:")
            print("    1. App Key / Secret 불일치 또는 만료")
            print("    2. 모의/실계좌 모드가 자격증명과 맞지 않음 (--real 플래그 확인)")
            print("    3. IP 접근 제한 (키움 포털에서 허용 IP 등록 필요)")
            return None

        data = resp.json()
        rc = str(data.get("return_code", "0"))
        if rc != "0":
            print(f"\n  ❌ return_code={rc}: {data.get('return_msg')}")
            return None

        token = data.get("token") or data.get("access_token")
        if not token:
            print(f"\n  ❌ 응답에 'token' 또는 'access_token' 필드 없음. 전체 키: {list(data.keys())}")
            return None

        expires_dt = data.get("expires_dt", "(없음)")
        print(f"\n  ✅ 토큰 발급 성공!")
        print(f"  Token: {_mask(token)} (길이 {len(token)})")
        print(f"  expires_dt: {expires_dt}")
        return token

    except httpx.ConnectError as e:
        print(f"\n  ❌ 연결 실패: {e}")
        print(f"  → {base_url} 에 접근할 수 없음 (네트워크/방화벽 확인)")
        return None
    except Exception as e:
        print(f"\n  ❌ 예외 발생: {type(e).__name__}: {e}")
        return None


# ---------------------------------------------------------------------------
# STEP 4: 잔고 조회
# ---------------------------------------------------------------------------

async def step4_get_balance(token: str, account_no: str, is_mock: bool) -> dict | None:
    _print_step(4, "잔고 조회 (kt00018)")
    base_url = MOCK_BASE_URL if is_mock else REAL_BASE_URL
    url = f"{base_url}/api/dostk/acnt"
    headers = {
        "Content-Type": "application/json;charset=UTF-8",
        "authorization": f"Bearer {token}",
        "api-id": "kt00018",
    }
    body = {
        "acnt_no": account_no,
        "acnt_prdt_cd": "01",
        "inqr_dvsn_1": "1",
        "inqr_dvsn_2": "0",
    }

    _print_req("POST", url, body)
    print(f"  Headers: api-id=kt00018, authorization=Bearer {_mask(token)}")

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(url, json=body, headers=headers)
        _print_resp(resp)

        if resp.status_code >= 400:
            print(f"\n  ❌ HTTP {resp.status_code} 오류")
            if resp.status_code == 401:
                print("  → 토큰 만료 또는 무효")
            return None

        data = resp.json()
        rc = str(data.get("return_code", "0"))
        if rc != "0":
            print(f"\n  ❌ return_code={rc}: {data.get('return_msg')}")
            return None

        print(f"\n  ✅ 잔고 조회 성공!")
        print(f"  응답 최상위 키: {list(data.keys())}")
        return data

    except Exception as e:
        print(f"\n  ❌ 예외 발생: {type(e).__name__}: {e}")
        return None


# ---------------------------------------------------------------------------
# STEP 5: 응답 파싱 검증
# ---------------------------------------------------------------------------

def step5_parse(data: dict) -> None:
    _print_step(5, "응답 필드 파싱 검증 (balance.py 기준)")

    checks = [
        ("acnt_eval_remn_base_amt_list", "보유종목 배열"),
        ("tot_eval_amt",                 "전체 평가금액"),
        ("dnca_tot_amt",                 "예수금"),
        ("pchs_amt_smtl",                "매입금액 합계"),
        ("eval_pfls_smtl_amt",           "평가손익 합계"),
    ]

    for field, desc in checks:
        val = data.get(field)
        if val is None:
            print(f"  ❌ [{field}] ({desc}) — 없음. 실제 응답 키를 확인하세요.")
        else:
            display = f"(리스트 {len(val)}건)" if isinstance(val, list) else val
            print(f"  ✅ [{field}] ({desc}) = {display}")

    # 종목 배열 내부 필드 검증
    items = data.get("acnt_eval_remn_base_amt_list", [])
    if items:
        sample = items[0]
        print(f"\n  보유종목 샘플 키: {list(sample.keys())}")
        position_fields = [
            ("stk_cd", "종목코드"), ("stk_nm", "종목명"), ("hldg_qty", "보유수량"),
            ("pchs_avg_pric", "매입평균가"), ("cur_prc", "현재가"),
            ("eval_amt", "평가금액"), ("eval_pfls_amt", "평가손익"), ("eval_pfls_rt", "수익률"),
        ]
        for f, d in position_fields:
            status = "✅" if f in sample else "❌"
            print(f"    {status} [{f}] ({d})")
    else:
        print("\n  ℹ️  보유종목이 없거나 필드명이 달라 파싱 불가")


# ---------------------------------------------------------------------------
# 메인
# ---------------------------------------------------------------------------

async def main() -> None:
    print("\n키움증권 OpenAPI+ 순차 연결 테스트")
    print("=" * 60)

    app_key, app_secret, account_no, is_mock = await step1_get_credentials()
    step2_validate(app_key, app_secret, account_no, is_mock)
    token = await step3_get_token(app_key, app_secret, is_mock)

    if not token:
        print("\n⛔ STEP 3 실패 — 이후 단계를 건너뜁니다.")
        print("\n[요약] 토큰 발급 실패. 위 STEP 3 출력에서 HTTP 상태/return_msg를 확인하세요.")
        sys.exit(1)

    balance_data = await step4_get_balance(token, account_no, is_mock)

    if not balance_data:
        print("\n⛔ STEP 4 실패 — STEP 5를 건너뜁니다.")
        sys.exit(1)

    step5_parse(balance_data)

    print("\n" + "=" * 60)
    print("✅ 모든 단계 완료. sync 플로우가 정상 동작해야 합니다.")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
