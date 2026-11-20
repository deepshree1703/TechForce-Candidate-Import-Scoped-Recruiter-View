// The whole page: load the recruiters, then show the candidates of the chosen recruiter.
import { useState } from "react";

import { PAGE_SIZE, getCandidates, getRecruiters } from "./api";
import { CandidateTable } from "./components/CandidateTable";
import { Filters } from "./components/Filters";
import { Pagination } from "./components/Pagination";
import { RecruiterSwitcher } from "./components/RecruiterSwitcher";
import { useDebounced, useLoad } from "./hooks";
import type { Recruiter, Status } from "./types";

const SEARCH_DELAY_MS = 300;

/** The candidates area: header, filters, table and pages for one chosen recruiter. */
function CandidateView({ recruiters }: { recruiters: Recruiter[] }) {
  const [selectedId, setSelectedId] = useState(recruiters[0].recruiter_id);
  const [searchText, setSearchText] = useState("");
  const [status, setStatus] = useState<Status | "">("");

  // The request waits until the user stops typing.
  const search = useDebounced(searchText.trim(), SEARCH_DELAY_MS);

  // The page number belongs to one combination of recruiter, search and status.
  // When that combination changes, the page falls back to 1 without any extra request.
  const filterKey = JSON.stringify([selectedId, search, status]);
  const [pageState, setPageState] = useState({ key: filterKey, page: 1 });
  const page = pageState.key === filterKey ? pageState.page : 1;

  const candidates = useLoad(
    (signal) => getCandidates(selectedId, { search, status, page }, signal),
    JSON.stringify([filterKey, page]),
  );

  const current = recruiters.find((recruiter) => recruiter.recruiter_id === selectedId) ?? recruiters[0];
  const scope = current.role === "admin" ? "admin, all regions" : "recruiter, assigned regions only";

  return (
    <>
      <header className="page-header">
        <div>
          <h1>Candidates</h1>
          <p>
            Viewing as <strong>{current.full_name}</strong> ({scope})
          </p>
        </div>
        <RecruiterSwitcher recruiters={recruiters} value={selectedId} onChange={setSelectedId} />
      </header>

      <Filters search={searchText} status={status} onSearchChange={setSearchText} onStatusChange={setStatus} />
      <CandidateTable load={candidates} />
      {candidates.state === "ready" && candidates.data.total > 0 && (
        <Pagination
          page={page}
          pageSize={PAGE_SIZE}
          total={candidates.data.total}
          onChange={(next) => setPageState({ key: filterKey, page: next })}
        />
      )}
    </>
  );
}

/** Loads the recruiters first, then shows the candidates. */
export default function App() {
  const recruiters = useLoad(getRecruiters, "recruiters");

  return (
    <main>
      {recruiters.state === "loading" && <p role="status">Loading recruiters…</p>}
      {recruiters.state === "error" && (
        <p role="alert" className="error">
          {recruiters.message} Reload the page to try again.
        </p>
      )}
      {recruiters.state === "ready" && recruiters.data.length === 0 && <p role="status">No recruiters found.</p>}
      {recruiters.state === "ready" && recruiters.data.length > 0 && <CandidateView recruiters={recruiters.data} />}
    </main>
  );
}