import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { fetchTaxSummary, fetchOverseasPositionsTax } from "@/api/tax";
import { STALE_TIME } from "@/constants/queryConfig";
import { QUERY_KEYS } from "@/constants/queryKeys";

export function useTaxPlanner() {
  const currentYear = new Date().getFullYear();
  const [taxYear, setTaxYear] = useState(currentYear);
  const [showTax, setShowTax] = useState(false);

  const { data: taxData, isLoading: taxLoading } = useQuery({
    queryKey: QUERY_KEYS.taxSummary(taxYear),
    queryFn: () => fetchTaxSummary(taxYear),
    staleTime: STALE_TIME.LONG,
    enabled: showTax,
  });

  const { data: positionsData, isLoading: posLoading } = useQuery({
    queryKey: QUERY_KEYS.overseasPositionsTax,
    queryFn: fetchOverseasPositionsTax,
    staleTime: STALE_TIME.MEDIUM,
    enabled: showTax,
  });

  return {
    currentYear,
    taxYear,
    setTaxYear,
    showTax,
    setShowTax,
    taxData,
    taxLoading,
    positionsData,
    posLoading,
  };
}
