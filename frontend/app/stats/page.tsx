"use client";
import { useEffect, useState } from "react";

import { Incident, fetchIncidents } from "../../lib/api";

export default function StatsPage() {
  const [incidents, setIncidents] = useState<Incident[]>([]);

  useEffect(() => {
    fetchIncidents().then(setIncidents);
  }, []);

  const counts: Record<string, number> = {};
  for (const incident of incidents) {
    const key = `${incident.hazard_type}:${incident.severity}`;
    counts[key] = (counts[key] || 0) + 1;
  }

  return (
    <main>
      <h1>Stats</h1>
      <table data-testid="stats-table">
        <tbody>
          {Object.entries(counts).map(([key, count]) => (
            <tr key={key}>
              <td>{key}</td>
              <td>{count}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </main>
  );
}
