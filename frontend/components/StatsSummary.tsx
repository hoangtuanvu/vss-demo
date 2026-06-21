import { Incident } from "../lib/api";

export default function StatsSummary({ incidents }: { incidents: Incident[] }) {
  const counts: Record<string, number> = {};
  for (const incident of incidents) {
    const key = `${incident.hazard_type}:${incident.severity}`;
    counts[key] = (counts[key] || 0) + 1;
  }
  const rows = Object.entries(counts);

  return (
    <div className="border border-paper/15 bg-panel p-4">
      <p className="font-mono text-xs uppercase tracking-widest text-paper/50">Shift report</p>
      <table data-testid="stats-table" className="mt-3 w-full">
        <tbody>
          {rows.length === 0 && (
            <tr>
              <td colSpan={2} className="py-4 text-center text-sm text-paper/40">
                No incidents recorded this shift.
              </td>
            </tr>
          )}
          {rows.map(([key, count]) => (
            <tr key={key} className="border-b border-paper/10 odd:bg-panel/50">
              <td className="py-1.5 font-mono text-sm">{key}</td>
              <td className="py-1.5 text-right font-mono text-sm">{count}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
