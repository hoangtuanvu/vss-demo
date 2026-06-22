import Link from "next/link";

import { Incident } from "../lib/api";

const SEVERITY: Record<string, { label: string; border: string; text: string }> = {
  critical: { label: "Critical", border: "border-alarm", text: "text-alarm" },
  warning: { label: "Caution", border: "border-caution", text: "text-caution" },
  info: { label: "Clear", border: "border-signal", text: "text-signal" },
};

export default function IncidentFeed({
  incidents,
  onPlayClip,
}: {
  incidents: Incident[];
  onPlayClip?: (offsetSeconds: number) => void;
}) {
  return (
    <ul data-testid="incident-list" className="space-y-2">
      {incidents.length === 0 && (
        <li className="border border-paper/15 bg-panel p-4 text-sm text-paper/50">
          No alerts yet. The floor is clear.
        </li>
      )}
      {incidents.map((incident) => {
        const severity = SEVERITY[incident.severity] ?? SEVERITY.info;
        return (
          <li key={incident.id} className={`border-l-2 ${severity.border} bg-panel`}>
            <Link href={`/incidents/${incident.id}`} className="block p-4 hover:bg-ink/40">
              <span className={`font-mono text-xs uppercase tracking-widest ${severity.text}`}>
                {severity.label}
              </span>
              <p className="mt-1 text-sm">
                <span className="font-mono text-paper/50">{incident.hazard_type}</span>: {incident.caption}
              </p>
            </Link>
            {incident.video_offset_seconds != null && (
              <button
                type="button"
                onClick={(event) => {
                  event.preventDefault();
                  event.stopPropagation();
                  onPlayClip?.(incident.video_offset_seconds as number);
                }}
                className="mb-3 ml-4 font-mono text-xs uppercase tracking-widest text-signal hover:underline"
              >
                Play clip
              </button>
            )}
          </li>
        );
      })}
    </ul>
  );
}
