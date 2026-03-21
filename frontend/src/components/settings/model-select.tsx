import { AlertTriangle } from "lucide-react";
import type { ModelOption } from "@/types/settings";

interface ModelSelectProps {
  id: string;
  label: string;
  value: string;
  onChange: (value: string) => void;
  groups: { provider: string; items: ModelOption[] }[];
  disabled: boolean;
  warningText: string | null;
}

const selectClassName =
  "w-full h-12 rounded-xl px-4 text-sm text-foreground outline-none focus:ring-2 focus:ring-primary/50 transition-all appearance-none cursor-pointer";
const selectStyle = {
  background: "var(--surface-container-high)",
  border: "1px solid var(--outline-variant)",
};

export function ModelSelect({ id, label, value, onChange, groups, disabled, warningText }: ModelSelectProps) {
  return (
    <div className="space-y-1.5">
      <label htmlFor={id} className="block text-sm font-medium" style={{ color: "var(--on-surface-variant)" }}>
        {label}
      </label>
      <select
        id={id}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className={selectClassName}
        style={selectStyle}
        disabled={disabled}
      >
        {groups.map(({ provider, items }) => (
          <optgroup key={provider} label={provider}>
            {items.map((m) => (
              <option key={m.model_id} value={m.model_id}>
                {m.label}
              </option>
            ))}
          </optgroup>
        ))}
      </select>
      {warningText && (
        <div className="flex items-center gap-1.5 text-xs" style={{ color: "var(--warning)" }}>
          <AlertTriangle className="size-3.5" />
          {warningText}
        </div>
      )}
    </div>
  );
}
