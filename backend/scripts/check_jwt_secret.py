"""JWT 시크릿 포맷 진단 스크립트: raw string vs base64 decoded 중 어느 것이 유효한지 확인."""
import base64
import sys

import jwt

SECRET_RAW = "O5vDTO+apbdM1fBThD6ru5Ho0Vk7BO4F9Sa09MtTVna9I1bXumg9E5Rqp7Rd+0aLeQA2DCa5OnqjIW9YW9S+8Q=="
ANON_KEY = (
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9"
    ".eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Im1odmpwZXB6aG1qdHV4dmt6ZW9sIiwicm9sZSI6ImFub24iLCJpYXQiOjE3Nzk2NjMwNzIsImV4cCI6MjA5NTIzOTA3Mn0"
    ".EU08kxVqEcTUWvb4ygfu0b0lsLtMkA-cSTqyVvbwa64"
)

options = {"verify_exp": False, "verify_aud": False, "verify_signature": True}

a_ok = False
b_ok = False

try:
    result = jwt.decode(ANON_KEY, SECRET_RAW, algorithms=["HS256"], options=options)
    print(f"[OK] Method A (raw string) passed: {result}")
    a_ok = True
except jwt.InvalidTokenError as e:
    print(f"[FAIL] Method A (raw string): {type(e).__name__}: {e}")

try:
    result = jwt.decode(ANON_KEY, base64.b64decode(SECRET_RAW), algorithms=["HS256"], options=options)
    print(f"[OK] Method B (base64 decoded) passed: {result}")
    b_ok = True
except jwt.InvalidTokenError as e:
    print(f"[FAIL] Method B (base64 decoded): {type(e).__name__}: {e}")

if a_ok:
    print("\nResult: raw string works. Only need to fix verify_aud in auth_service.py.")
elif b_ok:
    print("\nResult: base64 decode needed. Add base64.b64decode() to auth_service.py.")
else:
    print("\nResult: both methods failed. JWT secret value itself may be wrong.")
    sys.exit(1)
