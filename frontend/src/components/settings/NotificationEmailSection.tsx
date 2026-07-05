import { useState } from "react";
import { api } from "@/api/client";
import { toast } from "@/utils/toast";
import { SectionCard, inputClass, labelClass } from "./shared";

interface Props {
  userEmail?: string;
  onSettingsChange: () => void;
}

export function NotificationEmailSection({ userEmail, onSettingsChange }: Props) {
  const [notificationEmail, setNotificationEmail] = useState(userEmail ?? "");
  const [saving, setSaving] = useState<string | null>(null);

  const saveNotificationEmail = async () => {
    setSaving("notification-email");
    try {
      await api.put("/settings/notification-email", {
        notification_email: notificationEmail || null,
      });
      toast("알림 이메일이 저장되었습니다", "success");
      onSettingsChange();
    } catch {
      toast("저장에 실패했습니다", "error");
    } finally {
      setSaving(null);
    }
  };

  const sendTestEmail = async () => {
    setSaving("test-email");
    try {
      await api.post("/settings/test-email");
      toast("테스트 이메일을 발송했습니다. 받은편지함을 확인하세요.", "success");
    } catch {
      toast("이메일 발송에 실패했습니다. SMTP 설정을 확인하세요.", "error");
    } finally {
      setSaving(null);
    }
  };

  return (
    <SectionCard title="알림 수신 이메일">
      <div>
        <label className={labelClass}>이메일 주소</label>
        <input
          type="email"
          className={inputClass}
          value={notificationEmail}
          onChange={(e) => setNotificationEmail(e.target.value)}
          placeholder={userEmail ?? "이메일 주소"}
        />
        <p className="text-xs text-gray-400 dark:text-gray-500 mt-1">
          환율/주가/리밸런싱/시장신호 알림 모두 이 이메일로 발송됩니다. 비워두면 로그인 이메일(
          {userEmail})로 발송됩니다.
        </p>
      </div>
      <div className="flex items-center gap-3">
        <button
          onClick={saveNotificationEmail}
          disabled={saving === "notification-email"}
          className="bg-blue-600 text-white px-5 py-2 rounded-lg text-sm font-medium hover:bg-blue-700 disabled:opacity-50 transition-colors"
        >
          {saving === "notification-email" ? "저장 중..." : "저장"}
        </button>
        <button
          onClick={sendTestEmail}
          disabled={saving === "test-email"}
          className="px-5 py-2 text-sm border border-gray-300 dark:border-gray-600 text-gray-600 dark:text-gray-300 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-800 disabled:opacity-50 transition-colors"
        >
          {saving === "test-email" ? "발송 중..." : "테스트 발송"}
        </button>
      </div>
    </SectionCard>
  );
}
