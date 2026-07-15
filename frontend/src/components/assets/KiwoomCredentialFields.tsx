import type { AssetAccountCreate } from "@/api/assets";
import { INPUT_SM } from "@/constants/inputStyles";
import { useForm } from "@/hooks/useForm";

interface Props {
  form: AssetAccountCreate;
  set: ReturnType<typeof useForm<AssetAccountCreate>>["set"];
  isEdit: boolean;
}

// 키움증권 자격증명 입력
export default function KiwoomCredentialFields({ form, set, isEdit }: Props) {
  return (
    <>
      {!isEdit && (
        <div>
          <label
            htmlFor="stock-kiwoom-account-no"
            className="text-sm font-medium text-gray-700 dark:text-gray-300"
          >
            키움 계좌번호 *
          </label>
          <input
            id="stock-kiwoom-account-no"
            className={`mt-1 w-full ${INPUT_SM}`}
            value={form.kiwoom_account_no ?? ""}
            onChange={(e) => set("kiwoom_account_no", e.target.value)}
            placeholder="12345678-01"
            autoComplete="off"
          />
        </div>
      )}
      <div>
        <label
          htmlFor="stock-kiwoom-app-key"
          className="text-sm font-medium text-gray-600 dark:text-gray-400"
        >
          키움 App Key{!isEdit && " *"}
        </label>
        {isEdit && (
          <p className="text-xs text-gray-400 dark:text-gray-500 mt-0.5 mb-1">
            비워두면 기존 키를 유지합니다
          </p>
        )}
        <input
          id="stock-kiwoom-app-key"
          type="password"
          className={`mt-1 w-full ${INPUT_SM}`}
          value={form.kiwoom_app_key ?? ""}
          onChange={(e) => set("kiwoom_app_key", e.target.value || undefined)}
          placeholder={isEdit ? "기존 키 유지" : "키움 앱 키"}
          autoComplete="off"
        />
      </div>
      <div>
        <label
          htmlFor="stock-kiwoom-app-secret"
          className="text-sm font-medium text-gray-600 dark:text-gray-400"
        >
          키움 App Secret{!isEdit && " *"}
        </label>
        <input
          id="stock-kiwoom-app-secret"
          type="password"
          className={`mt-1 w-full ${INPUT_SM}`}
          value={form.kiwoom_app_secret ?? ""}
          onChange={(e) => set("kiwoom_app_secret", e.target.value || undefined)}
          placeholder={isEdit ? "기존 시크릿 유지" : "키움 앱 시크릿"}
          autoComplete="off"
        />
      </div>
    </>
  );
}
