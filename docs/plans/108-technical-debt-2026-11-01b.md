# 108. 기술부채 — 107 머지 후 재점검 (2026-11-01b)

## 배경

107이 main에 머지된 뒤로는 Dependabot PR 6건, 배당 테스트 네트워크 차단, python minor bump 보류만 들어왔다. 백엔드·프론트를 다시 훑었고 고전적 부채(700줄 넘는 파일, TODO·noqa, `any`·ts-ignore, 하드코딩 딥링크, CLAUDE.md 목록 드리프트)는 0건이었다.

남은 것은 셋이다.

- **Capacitor 8.6이 빌드 확인 없이 main에 들어왔다.** 107은 cap sync·Android 빌드 확인이 필요하다며 8.6을 이관했는데, Dependabot #212가 `@capacitor/android`만 `^8.6.0`으로 올렸고 lock은 core·cli·android 모두 8.6.0이 됐다. 하한은 core·cli `^8.5.3`로 갈라졌다. APK CI는 저장소 Variables가 없어 돈 적이 없다.
- **실버그(작음)**: `providers/http_client.py` `_is_rate_limit_body`가 JSON 본문을 항상 dict로 가정했다. 배열·`null`·문자열 본문이면 `AttributeError`가 나서, `broker_request`의 오류 처리 경로에서 원래 HTTP 오류를 덮었다.
- 정리: 효과 없는 `SplashScreen` 설정(`@capacitor/splash-screen` 미설치), 옛 탭 리다이렉트의 탭 이름 리터럴 타입 미검사, 불필요한 export, `gradlew.bat` 줄바꿈.

## 결과

| 항목 | 커밋 | 내용 |
|---|---|---|
| A | `381579c7` | `_is_rate_limit_body`에 비객체 본문 가드, 테스트 4케이스(`[]`·`null`·문자열·숫자) |
| B | `c8f1802f` | core·cli 하한 `^8.6.0`(lock diff는 루트 명세 2줄), `plugins.SplashScreen` 삭제. 스플래시는 `styles.xml`의 `Theme.SplashScreen`이 띄운다 |
| C | `5d9a1b88` | `legacyTabRedirect`·`AssetManagementPage`의 탭 리터럴을 `constants/tabs` 유니온으로 검사, `CURRENCY_TYPES` export 제거, `.gitattributes`에 `*.bat -text` |

### 계획과 달라진 것 / 스캐너 오탐

- `legacyAssetsTaxRedirect`를 `investPlanUrl` 빌더로 바꾸라는 제안은 채택하지 않았다. 사용자 URL에서 온 `taxTab`·`account`를 넘기므로 인코딩이 필요한데 빌더는 값을 인코딩하지 않는다. 이유를 주석으로 남겼다.
- `fetchTrades`·`fetchTransactions`는 죽은 export가 아니다. 같은 파일의 `fetchAll*`이 내부에서 쓴다.

## 검증

- 백엔드: 3230 tests 통과, 커버리지 92.82%. ruff·mypy clean.
- 프론트: 1966 tests 통과, typecheck(앱+테스트) clean, 변경 파일 eslint·prettier clean, `npm run build` 성공.
- Android: `npx cap sync android`(플러그인 4개: app·haptics·push-notifications·native-biometric) → `gradlew.bat assembleDebug` 성공(Gradle 8.14.6, `app-debug.apk` 8.0MB). **실기기 설치·스모크는 미실행.**

## 이관

- **사용자 확인 필요**: 8.6 APK 실기기 스모크(로그인·생체인증·푸시), 운영 Supabase Postgres 버전, APK CI 저장소 Variables.
- `npm audit` dev moderate 23건: vite-plugin-pwa 체인. 2.0.0이 최신이라 대기.
- 그대로 두는 것: `ExchangeRateAlertSection` 쿼리 정의(107 C4 판단), `InvestPlanPage`(574줄)·`PortfolioListSection`(538줄), 총자산 엔진 2벌, 메이저 업그레이드(react 19·recharts 3·tailwind 4·TS 7).
