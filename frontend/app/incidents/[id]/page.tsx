"use client";
import { useEffect, useState } from "react";

import { Incident, fetchIncident } from "../../../lib/api";

export default function IncidentDetailPage({ params }: { params: { id: string } }) {
  const [incident, setIncident] = useState<Incident | null>(null);

  useEffect(() => {
    fetchIncident(Number(params.id)).then(setIncident);
  }, [params.id]);

  if (!incident) return <p>Loading...</p>;

  return (
    <main>
      <h1>Incident #{incident.id}</h1>
      <p data-testid="incident-caption">{incident.caption}</p>
      <p data-testid="incident-severity">{incident.severity}</p>
      <p data-testid="incident-status">{incident.status}</p>
      {incident.report_text && <p data-testid="incident-report">{incident.report_text}</p>}
    </main>
  );
}
