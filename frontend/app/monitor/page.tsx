"use client";
import { useEffect, useState } from "react";

import ChatPanel from "../../components/ChatPanel";
import { Incident, subscribeToAlerts } from "../../lib/api";

const SEVERITY: Record<string, { label: string; border: string; text: string }> = {
  critical: { label: "Critical", border: "border-alarm", text: "text-alarm" },
  warning: { label: "Caution", border: "border-caution", text: "text-caution" },
  info: { label: "Clear", border: "border-signal", text: "text-signal" },
};

export default function MonitorPage() {
  const [incidents, setIncidents] = useState<Incident[]>([]);

  useEffect(() => {
    const source = subscribeToAlerts((incident) => {
      setIncidents((prev) => [incident, ...prev.filter((i) => i.id !== incident.id)]);
    });
    return () => source.close();
  }, []);

  return (
    <main className="min-h-screen">
      <div className="hazard-tape h-2 w-full" aria-hidden="true" />
      <div className="mx-auto max-w-5xl px-6 py-16">
        <div className="flex items-baseline justify-between">
          <div>
            <p className="font-mono text-xs uppercase tracking-[0.3em] text-caution">Live ops console</p>
            <h1 className="mt-4 font-display text-3xl">Live Monitor</h1>
          </div>
          <span className="flex items-center gap-2 font-mono text-xs uppercase tracking-widest text-alarm">
            <span className="h-2 w-2 rounded-full bg-alarm" aria-hidden="true" />
            Recording
          </span>
        </div>

        <div className="mt-8 grid gap-8 lg:grid-cols-[2fr_1fr]">
          <ul data-testid="incident-list" className="space-y-2">
            {incidents.length === 0 && (
              <li className="border border-paper/15 bg-panel p-4 text-sm text-paper/50">
                No alerts yet. The floor is clear.
              </li>
            )}
            {incidents.map((incident) => {
              const severity = SEVERITY[incident.severity] ?? SEVERITY.info;
              return (
                <li
                  key={incident.id}
                  className={`border-l-2 ${severity.border} bg-panel p-4`}
                >
                  <span className={`font-mono text-xs uppercase tracking-widest ${severity.text}`}>
                    {severity.label}
                  </span>
                  <p className="mt-1 text-sm">
                    <span className="font-mono text-paper/50">{incident.hazard_type}</span>: {incident.caption}
                  </p>
                </li>
              );
            })}
          </ul>

          <aside className="border border-paper/15 bg-panel p-4">
            <p className="font-mono text-xs uppercase tracking-widest text-paper/50">Ask the floor</p>
            <ChatPanel />
          </aside>
        </div>
      </div>
    </main>
  );
}
