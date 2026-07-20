# 계획 9: 설정탭(`/settings`) 개선 — 기능 감사 + UX + 신규기능

**리스크: 중간 (1번 항목은 FCM/네이티브 플랫폼 연동이 걸려 있어 중간, 나머지는 낮음)**

## 배경 (Why)

2026-07-20 사용자 요청으로 설정탭(`SettingsPage.tsx`)을 전수 점검했다. 설정탭은 이미 "계좌 연동/투자 목표/추천 옵션은 각 기능 페이지에서 편집, 여기서는 상태 요약+딥링크만 제공"이라는 명시적 설계 원칙(`SettingsPage.tsx:250` 주석, `frontend/CLAUDE.md` `/settings` 설명)을 갖고 있어, 이번 항목들도 그 원칙을 깨지 않는 선에서 정리했다.

## ⚠️ 실행 전 필수 확인사항

이 프로젝트는 여러 세션에서 동시에 작업되는 경우가 잦다. `git status`/`git diff`로 대상 파일이 이미 다른 세션에 의해 수정 중이 아닌지 확인하고, 파일:라인이 실제 코드와 다르면 코드 현재 상태를 우선한다.

**특히 이 문서의 3번 항목은 `docs/plans/04-notification-center-unification.md`(상태: 미착수)와 같은 파일(`SettingsPage.tsx:277-321` 알림 섹션)을 다룬다 — 둘 중 하나를 먼저 진행했다면 다른 하나를 시작하기 전 반드시 최신 코드를 다시 읽을 것.**

## 현재 코드 상태 (2026-07-20 기준)

- `frontend/src/pages/SettingsPage.tsx` — DART API키(212-248행) / 다른 설정 딥링크(250-275행) / 알림 설정(277-321행, `ALERT_TABS`: 환율/주가/시장신호/발송이력) / 앱 설정(323-374행: 다크모드/생체인증/로그아웃/탈퇴)
- `frontend/src/hooks/usePushNotifications.ts` — FCM 등록, `App.tsx`에서 전역 마운트(설정탭과 무관하게 자동 실행)
- `frontend/src/hooks/useBiometric.ts` — 생체인증 토글(이미 설정탭에 UI 있음, 참고 패턴)
- 백엔드: `backend/app/api/v1/settings.py` — `PUT /settings/push-token`(322행)

## 구현 단계 (항목별 독립 실행 가능)

### 1. [기능감사/버그 성격, 중간 리스크, 최우선] 푸시 알림 토글 UI 부재

`usePushNotifications.ts`가 `App.tsx`에서 전역 자동 등록만 수행하고, `SettingsPage.tsx` "앱 설정" 섹션(323-374행)에는 생체인증(342-356행)과 달리 푸시 알림 on/off 토글이 없다. 환율/주가/시장신호/이메일 알림은 전부 명시적 UI가 있는데 푸시만 빠져 있어, 알림이 안 오는 사용자가 원인 파악·재등록을 할 방법이 없다.

- `usePushNotifications.ts`의 현재 등록 상태(권한 허용 여부, 토큰 등록 성공 여부)를 노출하는 값/함수가 있는지 먼저 확인 — 없다면 훅에 상태 반환 추가
- `SettingsPage.tsx` "앱 설정" 섹션에 `useBiometric.ts` 토글 UI(342-356행)와 동일한 패턴으로 "푸시 알림" row 추가 — `isNativePlatform()` 가드도 동일하게 적용(웹에서는 FCM 미지원 시 숨김 처리 필요 여부 확인)
- 권한 거부 상태일 때는 토글 대신 "기기 설정에서 알림 권한을 허용해주세요" 안내로 대체(네이티브 OS 권한은 앱에서 강제로 못 켬)
- 테스트: 기존 `SettingsPage` 테스트 파일에 케이스 추가

### 2. [기능감사] 로그인 상태에서 비밀번호 변경 불가

설정탭에 "계정 정보"(로그인 이메일 표시) 섹션이 없고, 비밀번호 변경은 `ForgotPasswordPage`(로그아웃 상태 전용 플로우)를 거쳐야 한다. 로그인된 사용자가 단순히 비밀번호만 바꾸고 싶을 때 불편하다.

- Supabase 인증 흐름(`src/lib/supabase.ts`)에서 로그인 상태의 비밀번호 변경 API(`updateUser({ password })` 등) 지원 여부 확인
- "앱 설정" 섹션 또는 신규 "계정 정보" 섹션에 이메일 표시(읽기전용) + "비밀번호 변경" 버튼(모달 또는 기존 재설정 플로우 딥링크) 추가
- **주의**: `src/lib/supabase.ts`는 "직접 확장 금지 — 인증 흐름은 백엔드 JWT가 담당"이라고 `CLAUDE.md`에 명시되어 있음. 비밀번호 변경이 Supabase 세션과 백엔드 JWT 중 어느 쪽 책임인지 먼저 확인 후 진행(백엔드에 별도 엔드포인트가 필요할 수 있음)

### 3. [조율 필요] 리밸런싱 알림 요약과의 중복 가능성

`docs/plans/04-notification-center-unification.md`(미착수)가 `SettingsPage.tsx:280-289`의 "리밸런싱 비중 이탈 알림은 리밸런싱 탭에서 설정합니다" 텍스트 문구를 실제 알림 현황을 보여주는 요약 카드로 교체하는 계획이다. 이 문서(09번)의 범위에는 포함하지 않지만, 09번의 다른 항목(1, 2, 4, 5번)을 먼저 진행해 `SettingsPage.tsx`를 수정했다면 04번 진행 시 라인 번호가 달라져 있을 수 있으니 실행 전 재확인.

### 4. [UX] 알림 발송 이력 페이지네이션/필터 없음

`SettingsPage.tsx:81-128` `AlertHistorySection` — `fetchAlertHistory({ limit: 50 })`(84행) 고정, 더 이전 이력을 볼 방법이 없고 알림 유형별 필터도 없다.

- "더 보기" 버튼 또는 무한 스크롤로 `limit`/`offset` 페이지네이션 추가(백엔드 `fetchAlertHistory` API가 offset 파라미터를 지원하는지 `backend/app/api/v1/alerts.py` 확인 필요 — 미지원이면 백엔드도 함께 수정)
- `ALERT_TYPE_LABELS`(71-79행) 기준 유형별 필터 드롭다운 추가(선택적)

### 5. [신규기능, 낮은 우선순위] DART API 키 안내 부족

`SettingsPage.tsx:212-248` — "opendart.fss.or.kr에서 발급받은 API 키를 입력하세요"라는 텍스트 안내만 있고 발급 절차 링크가 없다. 외부 링크(`<a href="https://opendart.fss.or.kr" target="_blank">`)를 안내 문구에 추가하는 정도의 간단한 개선.

## 확장 아이디어 (이번 계획 범위 밖, 참고용)

- 알림 채널별(이메일/푸시) 수신 여부를 유형별로 세분화(예: 리밸런싱은 푸시만, 환율은 이메일만 등) — 현재는 채널 구분 없이 유형별 on/off만 존재
- 다크모드 외 테마 커스터마이징(포인트 컬러 등)
