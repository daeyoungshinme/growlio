interface Props {
  onAdd: (delta: number) => void;
  className?: string;
}

const UNITS = [
  { label: "+1만", value: 10_000 },
  { label: "+10만", value: 100_000 },
  { label: "+100만", value: 1_000_000 },
  { label: "+1억", value: 100_000_000 },
];

export default function AmountUnitButtons({ onAdd, className = "" }: Props) {
  return (
    <div className={`flex gap-1.5 mt-1.5 ${className}`}>
      {UNITS.map(({ label, value }) => (
        <button
          key={label}
          type="button"
          onClick={() => onAdd(value)}
          className="text-xs py-1.5 px-2.5 bg-gray-100 dark:bg-gray-800 text-gray-600 dark:text-gray-400 hover:bg-blue-50 dark:hover:bg-blue-950 hover:text-blue-600 dark:hover:text-blue-400 rounded-full transition-colors"
        >
          {label}
        </button>
      ))}
    </div>
  );
}
