import { useState } from "react";
import {
  Sun,
  Moon,
  LogOut,
  Bell,
  Fingerprint,
  LayoutGrid,
  UserX,
  Landmark,
  Target,
  Sparkles,
  ChevronRight,
  KeyRound,
} from "lucide-react";
import { Link } from "react-router-dom";
import { isNativePlatform } from "@/utils/platform";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/api/client";
import { fetchSettings } from "@/api/settings";
import { toast } from "@/utils/toast";
import { extractErrorMessage } from "@/utils/error";
import {
  REPORT_ALERT_FIELDS,
  INSTANT_ALERT_FIELDS,
  countEnabled,
} from "@/utils/notificationAlertGroups";
import { useThemeStore } from "@/stores/themeStore";
import { useAuthStore } from "@/stores/authStore";
import { useLogout } from "@/hooks/useLogout";
import { useBiometric } from "@/hooks/useBiometric";
import { retryPushRegistration, disablePushNotifications } from "@/hooks/usePushNotifications";
import { usePushNotificationStore } from "@/stores/pushNotificationStore";
import DeleteAccountModal from "@/components/settings/DeleteAccountModal";
import ChangePasswordModal from "@/components/settings/ChangePasswordModal";
import { SectionCard, ConnectedBadge } from "@/components/settings/shared";
import { QUERY_KEYS } from "@/constants/queryKeys";
import { STALE_TIME } from "@/constants/queryConfig";
import { INPUT_MD, LABEL_MD } from "@/constants/inputStyles";
import { TOUCH_TARGET_ROW } from "@/constants/uiSizes";

const RISK_TOLERANCE_LABELS: Record<string, string> = {
  CONSERVATIVE: "보수적",
  BALANCED: "중립",
  AGGRESSIVE: "공격적",
};

function SettingsLinkRow({
  to,
  icon,
  label,
  status,
  statusClassName,
}: {
  to: string;
  icon: React.ReactNode;
  label: string;
  status: string;
  statusClassName?: string;
}) {
  return (
    <Link
      to={to}
      className={`w-full gap-3 px-3 py-2 rounded-lg text-sm text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors ${TOUCH_TARGET_ROW}`}
    >
      {icon}
      <span className="flex-1 min-w-0 truncate">{label}</span>
      <span className={`text-xs shrink-0 ${statusClassName ?? "text-gray-400 dark:text-gray-500"}`}>
        {status}
      </span>
      <ChevronRight size={16} className="text-gray-300 dark:text-gray-600 shrink-0" />
    </Link>
  );
}

const inputClass = `mt-1 w-full ${INPUT_MD}`;
const labelClass = LABEL_MD;

export default function SettingsPage() {
  const { isDark, toggle } = useThemeStore();
  const logout = useLogout();
  const { isAvailable, isEnabled, setEnabled } = useBiometric();
  const pushStatus = usePushNotificationStore((s) => s.status);
  const qc = useQueryClient();
  const [dart, setDart] = useState({ api_key: "" });
  const [saving, setSaving] = useState<string | null>(null);
  const [showDeleteAccount, setShowDeleteAccount] = useState(false);
  const [showChangePassword, setShowChangePassword] = useState(false);
  const authEmail = useAuthStore((s) => s.email);

  const { data: current } = useQuery({
    queryKey: QUERY_KEYS.settings,
    queryFn: fetchSettings,
    staleTime: STALE_TIME.LONG,
  });

  const invalidateSettings = () => qc.invalidateQueries({ queryKey: QUERY_KEYS.settings });

  const saveDart = async () => {
    setSaving("dart");
    try {
      await api.put("/settings/dart", { api_key: dart.api_key });
      toast("DART API 키가 저장되었습니다", "success");
      void invalidateSettings();
    } catch (e) {
      toast(extractErrorMessage(e, "저장에 실패했습니다"), "error");
    } finally {
      setSaving(null);
    }
  };

  const deleteDart = async () => {
    setSaving("dart-delete");
    try {
      await api.delete("/settings/dart");
      toast("DART API 키가 삭제되었습니다", "success");
      void invalidateSettings();
    } catch (e) {
      toast(extractErrorMessage(e, "삭제에 실패했습니다"), "error");
    } finally {
      setSaving(null);
    }
  };

  const goalFieldsSetCount = current
    ? [
        current.goal_amount,
        current.annual_deposit_goal,
        current.monthly_deposit_amount,
        current.retirement_target_year,
        current.annual_dividend_goal,
      ].filter((v) => v !== null && v !== undefined).length
    : 0;
  const goalSummary = !current
    ? "불러오는 중..."
    : goalFieldsSetCount > 0
      ? `목표 ${goalFieldsSetCount}개 설정됨`
      : "설정된 목표 없음";

  const recommendationSummary = current
    ? `${RISK_TOLERANCE_LABELS[current.goal_risk_tolerance] ?? current.goal_risk_tolerance} · 후보 ${current.goal_candidate_tickers.length}개`
    : "불러오는 중...";

  const reportAlertsEnabledCount = current
    ? countEnabled(REPORT_ALERT_FIELDS.map((field) => Boolean(current[field])))
    : 0;
  const instantAlertsEnabledCount = current
    ? countEnabled(INSTANT_ALERT_FIELDS.map((field) => Boolean(current[field])))
    : 0;
  const notificationSummary = !current
    ? "불러오는 중..."
    : `정기 ${REPORT_ALERT_FIELDS.length}개 중 ${reportAlertsEnabledCount}개 · 즉시 ${INSTANT_ALERT_FIELDS.length}개 중 ${instantAlertsEnabledCount}개 켜짐`;

  return (
    <div className="space-y-6 max-w-xl">
      <h1 className="sr-only">설정</h1>
      {/* DART OpenAPI */}
      <SectionCard
        title="DART OpenAPI (금융감독원)"
        badge={current?.has_dart ? <ConnectedBadge /> : undefined}
      >
        <p className="text-xs text-gray-500 dark:text-gray-400">
          <a
            href="https://opendart.fss.or.kr"
            target="_blank"
            rel="noopener noreferrer"
            className="text-blue-600 dark:text-blue-400 underline"
          >
            opendart.fss.or.kr
          </a>
          에서 발급받은 API 키를 입력하세요. 국내 주식 배당 데이터 조회에 사용됩니다.
        </p>
        <div>
          <label className={labelClass}>API Key</label>
          <input
            type="password"
            className={inputClass}
            value={dart.api_key}
            onChange={(e) => setDart({ api_key: e.target.value })}
            placeholder={current?.has_dart ? "••••••••" : "DART OpenAPI 인증키"}
          />
        </div>
        <div className="flex items-center gap-3">
          <button
            onClick={saveDart}
            disabled={saving === "dart"}
            className="bg-blue-600 text-white px-5 py-2 rounded-lg text-sm font-medium hover:bg-blue-700 disabled:opacity-50 transition-colors"
          >
            {saving === "dart" ? "저장 중..." : "저장"}
          </button>
          {current?.has_dart && (
            <button
              onClick={deleteDart}
              disabled={saving === "dart-delete"}
              className="px-5 py-2 text-sm border border-red-300 dark:border-red-700 text-red-600 dark:text-red-400 rounded-lg hover:bg-red-50 dark:hover:bg-red-950 disabled:opacity-50 transition-colors"
            >
              {saving === "dart-delete" ? "삭제 중..." : "삭제"}
            </button>
          )}
        </div>
      </SectionCard>

      {/* 계정 정보 */}
      <SectionCard title="계정 정보">
        <div>
          <label className={labelClass}>로그인 이메일</label>
          <p className="mt-1 text-sm text-gray-700 dark:text-gray-300">{authEmail ?? "—"}</p>
        </div>
        <button
          onClick={() => setShowChangePassword(true)}
          className={`w-full gap-3 px-3 py-2 rounded-lg text-sm text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors ${TOUCH_TARGET_ROW}`}
        >
          <KeyRound size={18} />
          비밀번호 변경
        </button>
      </SectionCard>

      {/* 다른 설정 — 계좌 연동/목표/추천 옵션은 각 기능 페이지에서 편집, 여기서는 상태 요약 + 딥링크만 제공 */}
      <SectionCard title="다른 설정">
        <SettingsLinkRow
          to="/assets?tab=계좌관리"
          icon={<Landmark size={18} className="text-gray-400 dark:text-gray-500" />}
          label="계좌 연동 (KIS/키움)"
          status={!current ? "불러오는 중..." : current.has_kis ? "연결됨" : "미연결"}
          statusClassName={
            current?.has_kis
              ? "text-green-600 dark:text-green-400"
              : "text-gray-400 dark:text-gray-500"
          }
        />
        <SettingsLinkRow
          to="/invest-plan?tab=적립 계획"
          icon={<Target size={18} className="text-gray-400 dark:text-gray-500" />}
          label="투자·입금·배당 목표"
          status={goalSummary}
        />
        <SettingsLinkRow
          to="/rebalancing?rtab=포트폴리오"
          icon={<Sparkles size={18} className="text-gray-400 dark:text-gray-500" />}
          label="목표 역산 추천 옵션"
          status={recommendationSummary}
        />
      </SectionCard>

      {/* 알림 설정 — 실제 토글/이력은 별도 라우트(밀도가 높아 분리) */}
      <SectionCard title="알림">
        <SettingsLinkRow
          to="/settings/notifications"
          icon={<Bell size={18} className="text-gray-400 dark:text-gray-500" />}
          label="알림 설정"
          status={notificationSummary}
        />
      </SectionCard>

      {/* 앱 설정 */}
      <div>
        <SectionCard title="앱 설정">
          {isNativePlatform() && (
            <div className="flex items-start gap-3 p-3 rounded-lg bg-blue-50 dark:bg-blue-950/30 text-blue-700 dark:text-blue-400 mb-1">
              <LayoutGrid size={18} className="shrink-0 mt-0.5" />
              <p className="text-xs leading-relaxed">
                홈 화면을 길게 눌러 "위젯 추가"에서 Growlio를 선택하면 자산 현황을 홈 화면에서 바로
                확인할 수 있어요.
              </p>
            </div>
          )}
          <button
            onClick={toggle}
            className={`w-full gap-3 px-3 py-2 rounded-lg text-sm text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors ${TOUCH_TARGET_ROW}`}
          >
            {isDark ? <Sun size={18} /> : <Moon size={18} />}
            {isDark ? "라이트 모드로 전환" : "다크 모드로 전환"}
          </button>
          {isNativePlatform() && isAvailable && (
            <button
              onClick={() => setEnabled(!isEnabled)}
              className={`w-full gap-3 px-3 py-2 rounded-lg text-sm text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors ${TOUCH_TARGET_ROW}`}
              aria-pressed={isEnabled}
            >
              <Fingerprint size={18} className={isEnabled ? "text-blue-500" : undefined} />
              생체 인증
              <span
                className={`ml-auto text-xs font-medium ${isEnabled ? "text-blue-500" : "text-gray-400"}`}
              >
                {isEnabled ? "켜짐" : "꺼짐"}
              </span>
            </button>
          )}
          {isNativePlatform() && (
            <>
              <button
                onClick={() => {
                  if (pushStatus === "registered") {
                    void disablePushNotifications();
                  } else {
                    void retryPushRegistration();
                  }
                }}
                disabled={pushStatus === "requesting"}
                className={`w-full gap-3 px-3 py-2 rounded-lg text-sm text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors disabled:opacity-50 ${TOUCH_TARGET_ROW}`}
                aria-pressed={pushStatus === "registered"}
              >
                <Bell
                  size={18}
                  className={pushStatus === "registered" ? "text-blue-500" : undefined}
                />
                푸시 알림
                <span
                  className={`ml-auto text-xs font-medium ${pushStatus === "registered" ? "text-blue-500" : "text-gray-400"}`}
                >
                  {pushStatus === "registered"
                    ? "켜짐"
                    : pushStatus === "requesting"
                      ? "확인 중..."
                      : "꺼짐"}
                </span>
              </button>
              {pushStatus === "denied" && (
                <p className="px-3 -mt-1 mb-1 text-xs text-amber-600 dark:text-amber-400">
                  알림 권한이 거부되어 있어요. 기기 설정 &gt; 앱 &gt; Growlio에서 알림을
                  허용해주세요.
                </p>
              )}
            </>
          )}
          <button
            onClick={logout}
            className={`w-full gap-3 px-3 py-2 rounded-lg text-sm text-red-600 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-950 transition-colors ${TOUCH_TARGET_ROW}`}
          >
            <LogOut size={18} />
            로그아웃
          </button>
          <div className="border-t border-gray-100 dark:border-gray-800 pt-3">
            <button
              onClick={() => setShowDeleteAccount(true)}
              className={`w-full gap-3 px-3 py-2 rounded-lg text-sm text-gray-500 dark:text-gray-400 hover:text-red-600 dark:hover:text-red-400 hover:bg-red-50 dark:hover:bg-red-950 transition-colors ${TOUCH_TARGET_ROW}`}
            >
              <UserX size={18} />
              회원 탈퇴
            </button>
          </div>
        </SectionCard>
      </div>

      {showDeleteAccount && <DeleteAccountModal onClose={() => setShowDeleteAccount(false)} />}
      {showChangePassword && <ChangePasswordModal onClose={() => setShowChangePassword(false)} />}
    </div>
  );
}
