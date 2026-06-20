"use client";
import { useEffect, useState } from "react";

import { Incident, fetchIncident } from "../../../lib/api";

const SEVERITY_BORDER: Record<string, string> = {
  critical: "border-alarm",
  warning: "border-caution",
  info: "border-signal",
};

export default function IncidentDetailPage({ params }: { params: { id: string } }) {
  const [incident, setIncident] = useState<Incident | null>(null);

  useEffect(() => {
    fetchIncident(Number(params.id)).then(setIncident);
  }, [params.id]);

  if (!incident) {
    return (
      <main className="flex min-h-screen items-center justify-center font-mono text-sm text-paper/50">
        Loading...
      </main>
    );
  }

  const borderColor = SEVERITY_BORDER[incident.severity] ?? "border-paper/20";

  return (
    <main className="min-h-screen">
      <div className="hazard-tape h-2 w-full" aria-hidden="true" />
      <div className="mx-auto max-w-2xl px-6 py-16">
        <div className={`border-l-4 ${borderColor} border-y border-r border-paper/15 bg-panel p-6`}>
          <div className="flex items-baseline justify-between font-mono text-xs uppercase tracking-widest">
            <span data-testid="incident-severity" className="text-paper">
              {incident.severity}
            </span>
            <span data-testid="incident-status" className="text-paper/50">
              {incident.status}
            </span>
          </div>
          <h1 className="mt-3 font-display text-2xl">Incident #{incident.id}</h1>
          <dl className="mt-2 font-mono text-xs text-paper/50">
            <dt className="inline">Zone </dt>
            <dd className="inline">{incident.zone}</dd>
          </dl>
          <p data-testid="incident-caption" className="mt-4 text-lg">
            {incident.caption}
          </p>

          {incident.report_text && (
            <div className="mt-6 border-t border-paper/15 pt-4">
              <p className="font-mono text-xs uppercase tracking-widest text-paper/50">Report</p>
              <p data-testid="incident-report" className="mt-2 text-sm text-paper/80">
                {incident.report_text}
              </p>
            </div>
          )}
        </div>
      </div>
    </main>
  );
}
