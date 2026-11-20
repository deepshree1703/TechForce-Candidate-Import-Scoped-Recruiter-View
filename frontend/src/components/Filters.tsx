// The search box and the status filter.
import { STATUSES } from "../types";
import type { Status } from "../types";

interface Props {
  search: string;
  status: Status | "";
  onSearchChange: (text: string) => void;
  onStatusChange: (status: Status | "") => void;
}

/** Turn the select's text back into a status, or "" for "all". */
function toStatus(value: string): Status | "" {
  return STATUSES.find((status) => status === value) ?? "";
}

/** Search by name, email or role, and filter by status. */
export function Filters({ search, status, onSearchChange, onStatusChange }: Props) {
  return (
    <div className="filters">
      <label className="field grow">
        Search
        <input
          type="search"
          value={search}
          maxLength={100}
          placeholder="Name, email or role"
          onChange={(event) => onSearchChange(event.target.value)}
        />
      </label>
      <label className="field">
        Status
        <select value={status} onChange={(event) => onStatusChange(toStatus(event.target.value))}>
          <option value="">All statuses</option>
          {STATUSES.map((value) => (
            <option key={value} value={value}>
              {value}
            </option>
          ))}
        </select>
      </label>
    </div>
  );
}