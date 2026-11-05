import type { AssetAccountCreate } from "@/api/assets";
import { REAL_ESTATE_ASSET_TYPE } from "@/constants/assets";
import { RealEstateFormModal } from "./RealEstateFormModal";

interface CreateModalProps {
  onClose: () => void;
  onSubmit: (data: AssetAccountCreate) => void;
  isLoading: boolean;
}

export function RealEstateAccountModal({ onClose, onSubmit, isLoading }: CreateModalProps) {
  return (
    <RealEstateFormModal
      title="부동산 추가"
      submitLabel="추가"
      idSuffix="create"
      initial={{
        name: "",
        market_value: "",
        property_type: "아파트",
        address: "",
        purchase_price: "",
        purchase_date: "",
        mortgage_balance: "",
        include_in_total: true,
      }}
      placeholders={{
        name: "예: 강남 아파트",
        address: "예: 서울시 강남구 ...",
        market_value: "예: 800000000",
        purchase_price: "예: 600000000",
        mortgage_balance: "0",
      }}
      onClose={onClose}
      onSubmit={(values) =>
        onSubmit({ ...values, asset_type: REAL_ESTATE_ASSET_TYPE, data_source: "MANUAL" })
      }
      isLoading={isLoading}
    />
  );
}
