"use client";
import { useEffect, useState } from "react";

import ChatPanel from "../../components/ChatPanel";
import { Incident, subscribeToAlerts } from "../../lib/api";

const SEVERITY_COLORS: Record<string, string> = {
  critical: "red",
  warning: "orange",
  info: "gray",
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
    <main>
      <h1>Live Monitor</h1>
      <ul data-testid="incident-list">
        {incidents.map((incident) => (
          <li key={incident.id} style={{ color: SEVERITY_COLORS[incident.severity] }}>
            {incident.hazard_type}: {incident.caption}
          </li>
        ))}
      </ul>
      <ChatPanel />
    </main>
  );
}
