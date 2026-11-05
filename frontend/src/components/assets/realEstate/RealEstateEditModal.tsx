import type { AssetAccount, AssetAccountCreate, RealEstateDetails } from "@/api/assets";
import { RealEstateFormModal } from "./RealEstateFormModal";

interface EditModalProps {
  account: AssetAccount;
  onClose: () => void;
  onSubmit: (
    id: string,
    data: Partial<AssetAccountCreate & { real_estate_details: RealEstateDetails }>,
  ) => void;
  isLoading: boolean;
}

export function RealEstateEditModal({ account, onClose, onSubmit, isLoading }: EditModalProps) {
  const re = account.real_estate_details;
  return (
    <RealEstateFormModal
      title="부동산 수정"
      submitLabel="수정"
      idSuffix="edit"
      initial={{
        name: account.name,
        market_value: String(account.manual_amount ?? ""),
        property_type: re?.property_type ?? "아파트",
        address: re?.address ?? "",
        purchase_price: String(re?.purchase_price_krw ?? ""),
        purchase_date: re?.purchase_date ?? "",
        mortgage_balance: String(re?.mortgage_balance_krw ?? ""),
        include_in_total: account.include_in_total ?? true,
      }}
      onClose={onClose}
      onSubmit={(values) => onSubmit(account.id, values)}
      isLoading={isLoading}
    />
  );
}
