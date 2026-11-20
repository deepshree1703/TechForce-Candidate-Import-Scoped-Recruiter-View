// A tiny helper for talking to the API. Every call goes to /api, which Vite forwards to the backend.
import type { CandidatePage, CandidateQuery, Recruiter } from "./types";

const API_BASE = "/api/v1";

/** How many candidates one page shows. The API accepts 1 to 100. */
export const PAGE_SIZE = 20;

/** An error answer from the API, with its HTTP status. */
export class ApiError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

/** Read the "detail" message of an error answer, or fall back to a generic one. */
async function readDetail(response: Response): Promise<string> {
  try {
    const body: unknown = await response.json();
    if (typeof body === "object" && body !== null && "detail" in body && typeof body.detail === "string") {
      return body.detail;
    }
  } catch {
    // The body was not JSON; use the generic message below.
  }
  return `Request failed (${response.status})`;
}

/** GET a path from the API as JSON, optionally as a given recruiter. */
async function request<T>(path: string, signal: AbortSignal, recruiterId?: string): Promise<T> {
  const headers: Record<string, string> = {};
  if (recruiterId) {
    headers["X-Recruiter-Id"] = recruiterId;
  }
  const response = await fetch(`${API_BASE}${path}`, { headers, signal });
  if (!response.ok) {
    throw new ApiError(response.status, await readDetail(response));
  }
  return (await response.json()) as T;
}

/** Turn any error into a short message for the screen. */
export function describeError(error: unknown): string {
  if (error instanceof ApiError) {
    return error.message;
  }
  return "Could not reach the server. Is the API running?";
}

/** The recruiters for the dropdown (needs no header). */
export function getRecruiters(signal: AbortSignal): Promise<Recruiter[]> {
  return request<Recruiter[]>("/recruiters", signal);
}

/** One page of candidates, as the given recruiter. The database decides which rows they see. */
export function getCandidates(recruiterId: string, query: CandidateQuery, signal: AbortSignal): Promise<CandidatePage> {
  const params = new URLSearchParams({ page: String(query.page), page_size: String(PAGE_SIZE) });
  if (query.search) {
    params.set("search", query.search);
  }
  if (query.status) {
    params.set("status", query.status);
  }
  return request<CandidatePage>(`/candidates?${params}`, signal, recruiterId);
}