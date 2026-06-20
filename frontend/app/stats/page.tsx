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
  const rows = Object.entries(counts);

  return (
    <main className="min-h-screen">
      <div className="hazard-tape h-2 w-full" aria-hidden="true" />
      <div className="mx-auto max-w-3xl px-6 py-16">
        <p className="font-mono text-xs uppercase tracking-[0.3em] text-caution">Shift report</p>
        <h1 className="mt-4 font-display text-3xl">Stats</h1>

        <table data-testid="stats-table" className="mt-8 w-full border border-paper/15">
          <thead>
            <tr className="border-b border-paper/15 bg-panel">
              <th className="px-4 py-2 text-left font-mono text-xs uppercase tracking-widest text-paper/50">
                Hazard:Severity
              </th>
              <th className="px-4 py-2 text-right font-mono text-xs uppercase tracking-widest text-paper/50">
                Count
              </th>
            </tr>
          </thead>
          <tbody>
            {rows.length === 0 && (
              <tr>
                <td colSpan={2} className="px-4 py-6 text-center text-sm text-paper/40">
                  No incidents recorded this shift.
                </td>
              </tr>
            )}
            {rows.map(([key, count]) => (
              <tr key={key} className="border-b border-paper/10 odd:bg-panel/50">
                <td className="px-4 py-2 font-mono text-sm">{key}</td>
                <td className="px-4 py-2 text-right font-mono text-sm">{count}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </main>
  );
}
