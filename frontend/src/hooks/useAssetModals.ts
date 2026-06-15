import { useState } from "react";
import type { AssetAccount } from "@/api/assets";

export interface PositionsAccountInfo {
  id: string;
  name: string;
  dataSource: string;
}

export interface TxAccountInfo {
  id: string;
  name: string;
  depositKrw: number;
}

export function useAssetModals() {
  const [showBankModal, setShowBankModal] = useState(false);
  const [showStockModal, setShowStockModal] = useState(false);
  const [showRealEstateModal, setShowRealEstateModal] = useState(false);
  const [editingRealEstate, setEditingRealEstate] = useState<AssetAccount | null>(null);
  const [editingBankAccount, setEditingBankAccount] = useState<AssetAccount | null>(null);
  const [editingStockAccount, setEditingStockAccount] = useState<AssetAccount | null>(null);
  const [confirmDeleteId, setConfirmDeleteId] = useState<string | null>(null);
  const [positionsAccount, setPositionsAccount] = useState<PositionsAccountInfo | null>(null);
  const [txAccount, setTxAccount] = useState<TxAccountInfo | null>(null);

  return {
    showBankModal,
    setShowBankModal,
    showStockModal,
    setShowStockModal,
    showRealEstateModal,
    setShowRealEstateModal,
    editingRealEstate,
    setEditingRealEstate,
    editingBankAccount,
    setEditingBankAccount,
    editingStockAccount,
    setEditingStockAccount,
    confirmDeleteId,
    setConfirmDeleteId,
    positionsAccount,
    setPositionsAccount,
    txAccount,
    setTxAccount,
  };
}
