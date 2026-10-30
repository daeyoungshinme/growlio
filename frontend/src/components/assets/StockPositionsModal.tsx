import { useEffect, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { Loader2, RefreshCw, X } from "lucide-react";
import {
  fetchAccountPositions,
  replaceAccountPositions,
  syncAccountPositionPrices,
  type AccountPositionsSummary,
} from "@/api/assets";
import { useExchangeRate } from "@/hooks/useExchangeRate";
import { usePositionsEditor } from "@/hooks/usePositionsEditor";
import { extractErrorMessage } from "@/utils/error";
import { fmtKrwShort } from "@/utils/format";
import { pnlColor } from "@/utils/colors";
import { invalidateAccountData } from "@/utils/queryInvalidation";
import { toast } from "@/utils/toast";
import Modal from "@/components/common/Modal";
import { PositionsTable } from "./PositionsTable";
import type { Position } from "@/hooks/usePositionsEditor";
import { TOUCH_TARGET_MIN_MOBILE_ONLY } from "@/constants/uiSizes";

type Summary = AccountPositionsSummary;

const EMPTY_ROW: Position = {
  ticker: "",
  name: "",
  market: "KOSPI",
  qty: 0,
  avg_price: 0,
  avg_price_usd: null,
  usd_rate: null,
  current_price: null,
  current_price_usd: null,
};

export default function StockPositionsModal({
  accountId,
  accountName,
  onClose,
  readonly = false,
}: {
  accountId: string;
  accountName: string;
  onClose: () => void;
  readonly?: boolean;
}) {
  const [summary, setSummary] = useState<Summary | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [syncing, setSyncing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const usdRate = useExchangeRate();
  const queryClient = useQueryClient();

  const editor = usePositionsEditor([], usdRate);
  // setRows(useState setter)·enrichRows(모듈 함수)는 참조가 안정적이라 effect dep에 넣어도 재조회가 없다
  const { setRows, enrichRows } = editor;

  useEffect(() => {
    // 계좌 전환 시 늦게 도착한 이전 계좌 응답이 새 행을 덮어쓰지 않도록, 언마운트 후 setState도 막는다
    let cancelled = false;
    fetchAccountPositions<Position>(accountId)
      .then((data) => {
        if (cancelled) return;
        const positions = data.positions;
        setRows(enrichRows(positions.length ? positions : readonly ? [] : [{ ...EMPTY_ROW }]));
        setSummary(data.summary);
      })
      .catch((e) => {
        if (!cancelled) setError(extractErrorMessage(e, "포지션 조회에 실패했습니다"));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [accountId, readonly, setRows, enrichRows]);

  const liveSummary: Summary = editor.liveRows.reduce(
    (acc, r) => ({
      total_invested: acc.total_invested + (r.invested_amount ?? 0),
      total_value: acc.total_value + (r.value_amount ?? 0),
      total_pnl: acc.total_pnl + (r.pnl ?? 0),
      total_pnl_pct: 0,
    }),
    { total_invested: 0, total_value: 0, total_pnl: 0, total_pnl_pct: 0 },
  );
  if (liveSummary.total_invested > 0) {
    liveSummary.total_pnl_pct = (liveSummary.total_pnl / liveSummary.total_invested) * 100;
  }

  const handleSave = async () => {
    const valid = editor.rows.filter((r) => r.ticker || r.name || r.qty || r.avg_price);
    // 백엔드는 수량 0 이하를 422로 거부하지만 어느 행인지 알려주지 않는다
    const badQty = valid.find((r) => !(Number(r.qty) > 0));
    if (badQty) {
      setError(`${badQty.name || badQty.ticker || "이름 없는 종목"}: 수량은 0보다 커야 합니다`);
      return;
    }
    // 환율 로딩 전에 입력한 달러 평균단가는 원화 환산값이 0으로 남는다 — 422 대신 원인을 알려준다(plans/95 F4)
    const unconverted = valid.find((r) => r.avg_price_usd && !(Number(r.avg_price) > 0));
    if (unconverted) {
      setError(
        `${unconverted.name || unconverted.ticker || "이름 없는 종목"}: 환율을 불러오기 전에 입력한 달러 평균단가입니다. 평균단가를 다시 입력하세요`,
      );
      return;
    }
    setSaving(true);
    setError(null);
    try {
      await replaceAccountPositions(accountId, valid);
      // 무효화는 부모 onClose가 한다(닫기마다 invalidateAccountData) — 여기서 또 하면 두 번 돈다
      toast("저장되었습니다", "success");
      onClose();
    } catch (e) {
      setError(extractErrorMessage(e, "저장에 실패했습니다"));
    } finally {
      setSaving(false);
    }
  };

  const handleSyncAll = async () => {
    setSyncing(true);
    setError(null);
    try {
      const data = await syncAccountPositionPrices<Position>(accountId);
      editor.setRows(editor.enrichRows(data.positions));
      setSummary(data.summary);
      void invalidateAccountData(queryClient);
    } catch (e: unknown) {
      setError(extractErrorMessage(e, "현재가 조회에 실패했습니다"));
    } finally {
      setSyncing(false);
    }
  };

  const displaySummary = summary ?? liveSummary;

  return (
    <Modal size="xl" onClose={onClose}>
      {/* 헤더 */}
      <div className="flex items-center justify-between px-6 py-3 border-b border-gray-200 dark:border-gray-700">
        <div>
          <h2 className="text-base font-bold text-gray-900 dark:text-gray-50">종목 관리</h2>
          <p className="text-xs text-gray-400 dark:text-gray-500">{accountName}</p>
        </div>
        <div className="flex items-center gap-3">
          {usdRate && (
            <span className="text-xs text-gray-400 dark:text-gray-500 bg-gray-50 dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg px-3 py-1.5">
              USD/KRW{" "}
              <strong className="text-gray-600 dark:text-gray-300">
                {usdRate.toLocaleString(undefined, { maximumFractionDigits: 0 })}원
              </strong>
            </span>
          )}
          <button
            onClick={onClose}
            aria-label="닫기"
            className={`${TOUCH_TARGET_MIN_MOBILE_ONLY} p-2 hover:bg-gray-100 dark:hover:bg-gray-800 rounded-lg text-gray-500 dark:text-gray-400`}
          >
            <X size={18} />
          </button>
        </div>
      </div>

      {/* 증권사 API 계좌 읽기전용 배너 */}
      {readonly && (
        <div className="px-6 py-2 bg-blue-50 dark:bg-blue-950 border-b border-blue-100 dark:border-blue-900 text-xs text-blue-600 dark:text-blue-400">
          증권사 연동(KIS/키움/토스) 계좌는 동기화로 자동 업데이트됩니다. 종목을 직접 편집하려면
          수동 계좌를 사용하세요.
        </div>
      )}

      {/* 요약 카드 */}
      <div className="grid grid-cols-3 gap-2 px-4 sm:px-6 py-2 sm:py-3 bg-gray-50 dark:bg-gray-800 border-b border-gray-200 dark:border-gray-700 text-center text-sm">
        <div>
          <p className="text-gray-400 dark:text-gray-500 text-xs mb-0.5">매입금액</p>
          <p className="font-bold text-sm text-gray-900 dark:text-gray-50">
            {fmtKrwShort(displaySummary.total_invested)}원
          </p>
        </div>
        <div>
          <p className="text-gray-400 dark:text-gray-500 text-xs mb-0.5">평가금액</p>
          <p className="font-bold text-sm text-gray-900 dark:text-gray-50">
            {fmtKrwShort(displaySummary.total_value)}원
          </p>
        </div>
        <div>
          <p className="text-gray-400 dark:text-gray-500 text-xs mb-0.5">손익/수익률</p>
          <p className={`font-bold text-sm ${pnlColor(displaySummary.total_pnl)}`}>
            {displaySummary.total_pnl >= 0 ? "+" : ""}
            {fmtKrwShort(displaySummary.total_pnl)}원
          </p>
          <p className={`text-xs ${pnlColor(displaySummary.total_pnl_pct)}`}>
            {displaySummary.total_pnl_pct >= 0 ? "+" : ""}
            {displaySummary.total_pnl_pct.toFixed(2)}%
          </p>
        </div>
      </div>

      {/* 종목 목록 */}
      <div className="flex-1 min-h-0 overflow-auto px-4 sm:px-6 py-2">
        {loading ? (
          <div className="text-gray-400 dark:text-gray-500 text-sm py-8 text-center flex items-center justify-center gap-2">
            <Loader2 size={16} className="animate-spin" /> 불러오는 중...
          </div>
        ) : readonly && editor.rows.length === 0 ? (
          <div className="text-gray-400 dark:text-gray-500 text-sm py-12 text-center">
            동기화 후 보유종목이 표시됩니다
          </div>
        ) : (
          <PositionsTable
            rows={editor.rows}
            liveRows={editor.liveRows}
            readonly={readonly}
            usdRate={usdRate}
            suggestions={editor.suggestions}
            suggestIdx={editor.suggestIdx}
            searchLoading={editor.searchLoading}
            priceLoadingRows={editor.priceLoadingRows}
            setSuggestIdx={editor.setSuggestIdx}
            handleNameChange={editor.handleNameChange}
            handleNameBlur={editor.handleNameBlur}
            handleSelectSuggestion={editor.handleSelectSuggestion}
            setRow={editor.setRow}
            removeRow={editor.removeRow}
            addRow={editor.addRow}
            handleAvgPriceUsd={editor.handleAvgPriceUsd}
            handleCurrentPriceUsd={editor.handleCurrentPriceUsd}
          />
        )}
      </div>

      {error && (
        <div className="mx-6 mb-2 text-xs text-red-600 dark:text-red-400 bg-red-50 dark:bg-red-950 border border-red-200 dark:border-red-800 rounded-lg px-3 py-2">
          {error}
        </div>
      )}

      {/* 하단 버튼 */}
      <div className="flex-shrink-0 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2 px-6 py-3 border-t border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-800 rounded-b-2xl">
        <button
          onClick={handleSyncAll}
          disabled={syncing || editor.rows.every((r) => !r.ticker)}
          className="flex items-center justify-center gap-2 text-sm text-gray-600 dark:text-gray-400 border border-gray-300 dark:border-gray-600 px-4 py-2 rounded-lg hover:bg-white dark:hover:bg-gray-700 disabled:opacity-40 transition-colors w-full sm:w-auto"
        >
          <RefreshCw size={14} className={syncing ? "animate-spin" : ""} />
          전체 현재가 갱신
        </button>
        <div className="flex gap-3 sm:justify-end">
          <button
            onClick={onClose}
            className="flex-1 sm:flex-none px-4 py-2 text-sm border border-gray-300 dark:border-gray-600 text-gray-700 dark:text-gray-300 rounded-lg hover:bg-white dark:hover:bg-gray-700"
          >
            닫기
          </button>
          {!readonly && (
            <button
              onClick={handleSave}
              disabled={saving}
              className="flex-1 sm:flex-none px-5 py-2 text-sm bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 font-medium"
            >
              {saving ? "저장 중..." : "저장"}
            </button>
          )}
        </div>
      </div>
    </Modal>
  );
}
