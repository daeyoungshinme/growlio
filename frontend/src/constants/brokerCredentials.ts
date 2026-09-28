// 증권사 API 자격증명 입력 폼 설정 — BrokerCredentialFields가 이 테이블만 보고 렌더한다.
export type BrokerDataSource = "KIS_API" | "KIWOOM_API" | "TOSS_API";

type CredentialKey =
  | "kis_app_key"
  | "kis_app_secret"
  | "kiwoom_app_key"
  | "kiwoom_app_secret"
  | "toss_client_id"
  | "toss_client_secret";
type AccountNoKey = "kis_account_no" | "kiwoom_account_no" | "toss_account_no";

interface BrokerCredentialConfig {
  /** input id 접두사 — `stock-${idPrefix}-account-no` 등 */
  idPrefix: string;
  accountNo: { field: AccountNoKey; label: string; placeholder: string };
  key: { field: CredentialKey; idSuffix: string; label: string; placeholder: string };
  secret: { field: CredentialKey; idSuffix: string; label: string; placeholder: string };
  /** 수정 모드: 비워두면 기존 자격증명을 유지한다는 안내 + 입력 placeholder */
  edit: { hint: string; keyPlaceholder: string; secretPlaceholder: string };
}

const KEEP_KEY = {
  hint: "비워두면 기존 키를 유지합니다",
  keyPlaceholder: "기존 키 유지",
  secretPlaceholder: "기존 시크릿 유지",
};

// 백엔드 app/services/asset_credential_service.py BROKER_CREDENTIAL_SPECS와 필드명이 대응한다
export const BROKER_CREDENTIAL_CONFIG: Record<BrokerDataSource, BrokerCredentialConfig> = {
  KIS_API: {
    idPrefix: "kis",
    accountNo: { field: "kis_account_no", label: "KIS 계좌번호", placeholder: "12345678-01" },
    key: {
      field: "kis_app_key",
      idSuffix: "app-key",
      label: "KIS App Key",
      placeholder: "KIS 앱 키",
    },
    secret: {
      field: "kis_app_secret",
      idSuffix: "app-secret",
      label: "KIS App Secret",
      placeholder: "KIS 앱 시크릿",
    },
    edit: KEEP_KEY,
  },
  KIWOOM_API: {
    idPrefix: "kiwoom",
    accountNo: { field: "kiwoom_account_no", label: "키움 계좌번호", placeholder: "12345678-01" },
    key: {
      field: "kiwoom_app_key",
      idSuffix: "app-key",
      label: "키움 App Key",
      placeholder: "키움 앱 키",
    },
    secret: {
      field: "kiwoom_app_secret",
      idSuffix: "app-secret",
      label: "키움 App Secret",
      placeholder: "키움 앱 시크릿",
    },
    edit: KEEP_KEY,
  },
  TOSS_API: {
    idPrefix: "toss",
    accountNo: {
      field: "toss_account_no",
      label: "토스증권 계좌번호",
      placeholder: "토스증권 계좌번호",
    },
    key: {
      field: "toss_client_id",
      idSuffix: "client-id",
      label: "토스 Client ID",
      placeholder: "토스 Client ID",
    },
    secret: {
      field: "toss_client_secret",
      idSuffix: "client-secret",
      label: "토스 Client Secret",
      placeholder: "토스 Client Secret",
    },
    edit: {
      hint: "비워두면 기존 값을 유지합니다",
      keyPlaceholder: "기존 값 유지",
      secretPlaceholder: "기존 값 유지",
    },
  },
};

export function isBrokerDataSource(source: string | undefined): source is BrokerDataSource {
  return !!source && source in BROKER_CREDENTIAL_CONFIG;
}
