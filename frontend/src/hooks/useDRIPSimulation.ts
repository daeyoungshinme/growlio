import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { fetchDRIPSimulation } from "@/api/dividends";

const YEARS_OPTIONS = [5, 10, 20, 30] as const;
export type DRIPYearsOption = (typeof YEARS_OPTIONS)[number];
export { YEARS_OPTIONS as DRIP_YEARS_OPTIONS };

export function useDRIPSimulation() {
  const [nYears, setNYears] = useState<DRIPYearsOption>(10);

  const { data, mutate, isPending } = useMutation({
    mutationFn: (years: number) => fetchDRIPSimulation({ n_years: years }),
  });

  const handleRun = (y: DRIPYearsOption) => {
    setNYears(y);
    mutate(y);
  };

  return { data, nYears, isPending, handleRun };
}
