// The candidate table, with its loading, error and empty states.
import type { Load } from "../hooks";
import type { CandidatePage } from "../types";

/** Show a page of candidates, or the message that fits the current state. */
export function CandidateTable({ load }: { load: Load<CandidatePage> }) {
  if (load.state === "loading") {
    return <p role="status">Loading candidates…</p>;
  }
  if (load.state === "error") {
    return (
      <p role="alert" className="error">
        {load.message}
      </p>
    );
  }
  if (load.data.items.length === 0) {
    return <p role="status">No candidates match.</p>;
  }

  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            <th scope="col">Name</th>
            <th scope="col">Email</th>
            <th scope="col">Region</th>
            <th scope="col">Role</th>
            <th scope="col">Status</th>
            <th scope="col">Applied</th>
          </tr>
        </thead>
        <tbody>
          {load.data.items.map((candidate) => (
            <tr key={candidate.candidate_id}>
              <td>
                {candidate.first_name} {candidate.last_name}
              </td>
              <td>{candidate.email}</td>
              <td>{candidate.region_code}</td>
              <td>{candidate.desired_role ?? "—"}</td>
              <td className="status">{candidate.status}</td>
              <td>{candidate.applied_date ?? "—"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}