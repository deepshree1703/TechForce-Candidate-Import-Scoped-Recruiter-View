// The shapes of the data the API sends, and of the filters the page sends back.

export const STATUSES = ["active", "screening", "interviewing", "withdrawn"] as const;

export type Status = (typeof STATUSES)[number];

/** A recruiter as listed in the dropdown. */
export interface Recruiter {
  recruiter_id: string;
  full_name: string;
  role: string;
}

/** One candidate row of the list. */
export interface Candidate {
  candidate_id: string;
  first_name: string;
  last_name: string;
  email: string;
  region_code: string;
  desired_role: string | null;
  status: Status;
  applied_date: string | null; // YYYY-MM-DD
}

/** One page of candidates plus the total number of matches. */
export interface CandidatePage {
  items: Candidate[];
  total: number;
  page: number;
  page_size: number;
}

/** The filters and page the user has chosen. */
export interface CandidateQuery {
  search: string;
  status: Status | "";
  page: number;
}