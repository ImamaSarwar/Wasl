import { useEffect, useState } from "react";
import { onApiCall } from "../api.js";

// Dev-only helper: shows the most recent API calls and their raw JSON, so you can
// test the backend and the UI side by side. Remove or hide before the final demo.
export default function DebugPanel() {
  const [calls, setCalls] = useState([]);

  useEffect(() => onApiCall((c) => setCalls((prev) => [c, ...prev].slice(0, 12))), []);

  return (
    <details className="card debug">
      <summary>Debug: last API calls ({calls.length})</summary>
      {calls.map((c, i) => (
        <details key={i} className="call">
          <summary>
            <code>{c.method} {decodeURIComponent(c.path)}</code> - {c.status} - {c.ms} ms
          </summary>
          <pre>{JSON.stringify(c.data, null, 2).slice(0, 4000)}</pre>
        </details>
      ))}
    </details>
  );
}
