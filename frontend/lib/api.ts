const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";

export interface Incident {
  id: number;
  hazard_type: string;
  severity: string;
  status: string;
  zone: string;
  caption: string;
  report_text: string | null;
  created_at: string;
  updated_at: string;
}

export async function uploadVideo(file: File): Promise<{ stream_url: string }> {
  const formData = new FormData();
  formData.append("file", file);
  const res = await fetch(`${API_BASE_URL}/upload`, { method: "POST", body: formData });
  if (!res.ok) throw new Error("upload failed");
  return res.json();
}

export async function fetchIncidents(): Promise<Incident[]> {
  const res = await fetch(`${API_BASE_URL}/incidents`);
  if (!res.ok) throw new Error("failed to fetch incidents");
  return res.json();
}

export async function fetchIncident(id: number): Promise<Incident> {
  const res = await fetch(`${API_BASE_URL}/incidents/${id}`);
  if (!res.ok) throw new Error("failed to fetch incident");
  return res.json();
}

export async function sendChatMessage(message: string): Promise<{ answer: string }> {
  const res = await fetch(`${API_BASE_URL}/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message }),
  });
  if (!res.ok) throw new Error("chat failed");
  return res.json();
}

export function subscribeToAlerts(onIncident: (incident: Incident) => void): EventSource {
  const source = new EventSource(`${API_BASE_URL}/alerts/stream`);
  source.addEventListener("incident", (event) => {
    onIncident(JSON.parse((event as MessageEvent).data));
  });
  return source;
}
