// The dropdown that chooses who the page is viewed as.
import type { Recruiter } from "../types";

interface Props {
  recruiters: Recruiter[];
  value: string;
  onChange: (recruiterId: string) => void;
}

/** A labelled select of recruiters. */
export function RecruiterSwitcher({ recruiters, value, onChange }: Props) {
  return (
    <label className="field">
      View as
      <select value={value} onChange={(event) => onChange(event.target.value)}>
        {recruiters.map((recruiter) => (
          <option key={recruiter.recruiter_id} value={recruiter.recruiter_id}>
            {recruiter.full_name} ({recruiter.recruiter_id})
          </option>
        ))}
      </select>
    </label>
  );
}