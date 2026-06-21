"use client";
import { useEffect, useState } from "react";

import ChatPanel from "../components/ChatPanel";
import IncidentFeed from "../components/IncidentFeed";
import StatsSummary from "../components/StatsSummary";
import UploadBar from "../components/UploadBar";
import { Incident, fetchIncidents, subscribeToAlerts } from "../lib/api";

export default function Home() {
  const [incidents, setIncidents] = useState<Incident[]>([]);

  useEffect(() => {
    fetchIncidents().then(setIncidents);
  }, []);

  useEffect(() => {
    const source = subscribeToAlerts((incident) => {
      setIncidents((prev) => [incident, ...prev.filter((i) => i.id !== incident.id)]);
    });
    return () => source.close();
  }, []);

  return (
    <main className="min-h-screen">
      <div className="hazard-tape h-2 w-full" aria-hidden="true" />
      <div className="mx-auto max-w-6xl px-6 py-12">
        <div className="flex flex-wrap items-baseline justify-between gap-4">
          <div>
            <p className="font-mono text-xs uppercase tracking-[0.3em] text-caution">Live ops console</p>
            <h1 className="mt-4 font-display text-3xl sm:text-4xl">Warehouse Safety Monitor</h1>
          </div>
          <span className="flex items-center gap-2 font-mono text-xs uppercase tracking-widest text-alarm">
            <span className="h-2 w-2 rounded-full bg-alarm" aria-hidden="true" />
            Recording
          </span>
        </div>

        <div className="mt-6">
          <UploadBar />
        </div>

        <div className="mt-8 grid gap-8 lg:grid-cols-[2fr_1fr]">
          <IncidentFeed incidents={incidents} />
          <aside className="space-y-8">
            <div className="border border-paper/15 bg-panel p-4">
              <p className="font-mono text-xs uppercase tracking-widest text-paper/50">Ask the floor</p>
              <ChatPanel />
            </div>
            <StatsSummary incidents={incidents} />
          </aside>
        </div>
      </div>
    </main>
  );
}
