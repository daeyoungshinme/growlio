import type { ExecutionState, ExecutionAction, BalanceLoadState } from "./types";

export function executionReducer(state: ExecutionState, action: ExecutionAction): ExecutionState {
  switch (action.type) {
    case "BALANCES_START":
      return {
        ...state,
        balanceState: Object.fromEntries(
          action.accountIds.map((id) => [id, "loading" as BalanceLoadState]),
        ),
      };
    case "BALANCES_LOADED":
      return {
        ...state,
        liveBalances: action.balances,
        depositKrw: action.deposits,
        orderableKrw: action.orderables,
        balanceState: { ...state.balanceState, ...action.states },
      };
    case "BALANCES_ERROR":
      return {
        ...state,
        balanceState: Object.fromEntries(
          action.accountIds.map((id) => [id, "error" as BalanceLoadState]),
        ),
      };
    case "BALANCE_LOADING":
      return { ...state, balanceState: { ...state.balanceState, [action.accountId]: "loading" } };
    case "BALANCE_LOADED": {
      const nextOrderable = { ...state.orderableKrw };
      if (action.orderable !== null) nextOrderable[action.accountId] = action.orderable;
      return {
        ...state,
        liveBalances: { ...state.liveBalances, [action.accountId]: action.positions },
        depositKrw: { ...state.depositKrw, [action.accountId]: action.deposit },
        orderableKrw: nextOrderable,
        balanceState: { ...state.balanceState, [action.accountId]: "loaded" },
      };
    }
    case "BALANCE_ERROR":
      return {
        ...state,
        balanceState: {
          ...state.balanceState,
          [action.accountId]: action.is404 ? "not_found" : "error",
        },
      };
    case "PRICES_START":
      return {
        ...state,
        priceState: "loading",
        priceLoadProgress: { loaded: 0, total: action.total },
      };
    case "PRICES_PROGRESS":
      return { ...state, priceLoadProgress: { ...state.priceLoadProgress, loaded: action.loaded } };
    case "PRICES_DONE":
      return {
        ...state,
        livePricesKrw: action.krw,
        livePricesUsd: action.usd,
        globalUsdRate: action.usdRate ?? state.globalUsdRate,
        priceState: Object.keys(action.krw).length > 0 ? "loaded" : "error",
      };
    case "SET_ORDER_TYPE":
      return { ...state, orderType: action.orderType };
    case "SET_LIMIT_PRICE":
      return {
        ...state,
        limitPriceOverrides: {
          ...state.limitPriceOverrides,
          [action.key]: Math.max(0, action.price),
        },
      };
    case "SET_QTY":
      return {
        ...state,
        qtyOverrides: { ...state.qtyOverrides, [action.key]: Math.max(0, action.qty) },
      };
    case "SET_QTY_AND_SELECT": {
      const next = new Set(state.selected);
      if (action.qty > 0) next.add(action.key);
      else next.delete(action.key);
      return {
        ...state,
        qtyOverrides: { ...state.qtyOverrides, [action.key]: Math.max(0, action.qty) },
        selected: next,
      };
    }
    case "TOGGLE_SELECTED": {
      const next = new Set(state.selected);
      if (next.has(action.key)) next.delete(action.key);
      else next.add(action.key);
      return { ...state, selected: next };
    }
    case "ADD_BUY_ACCOUNT":
      return {
        ...state,
        buyAccounts: {
          ...state.buyAccounts,
          [action.ticker]: [...(state.buyAccounts[action.ticker] ?? []), action.accountId],
        },
        qtyOverrides: { ...state.qtyOverrides, [`buy_${action.ticker}_${action.accountId}`]: 0 },
      };
    case "REMOVE_BUY_ACCOUNT": {
      const key = `buy_${action.ticker}_${action.accountId}`;
      const next = new Set(state.selected);
      next.delete(key);
      const nextQty = { ...state.qtyOverrides };
      delete nextQty[key];
      return {
        ...state,
        buyAccounts: {
          ...state.buyAccounts,
          [action.ticker]: (state.buyAccounts[action.ticker] ?? []).filter(
            (id) => id !== action.accountId,
          ),
        },
        selected: next,
        qtyOverrides: nextQty,
      };
    }
    case "EXECUTE_START":
      return { ...state, phase: "executing", errorMsg: null, confirmed: false };
    case "EXECUTE_SUCCESS":
      return { ...state, phase: "result", results: action.results };
    case "EXECUTE_ERROR":
      return { ...state, phase: "confirm", errorMsg: action.msg };
    case "CONFIRM_CLICK":
      return { ...state, confirmed: true };
    case "BULK_SET_QTY": {
      const nextQtyOverrides = { ...state.qtyOverrides };
      const nextSelected = new Set(state.selected);
      for (const { key, qty } of action.entries) {
        nextQtyOverrides[key] = Math.max(0, qty);
        if (qty <= 0) nextSelected.delete(key);
      }
      return { ...state, qtyOverrides: nextQtyOverrides, selected: nextSelected };
    }
    default:
      return state;
  }
}
