"use client";
import { useState } from "react";

import { uploadVideo } from "../../lib/api";

export default function UploadPage() {
  const [status, setStatus] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const fileInput = event.currentTarget.elements.namedItem("file") as HTMLInputElement;
    const file = fileInput.files?.[0];
    if (!file) return;
    try {
      const result = await uploadVideo(file);
      setStatus(`Streaming at ${result.stream_url}`);
      setError(null);
    } catch {
      setError("Upload failed. Try again.");
      setStatus(null);
    }
  }

  return (
    <main>
      <h1>Upload Video</h1>
      <form onSubmit={handleSubmit}>
        <input type="file" name="file" accept="video/*" data-testid="file-input" />
        <button type="submit">Upload</button>
      </form>
      {status && <p data-testid="upload-status">{status}</p>}
      {error && <p data-testid="upload-error">{error}</p>}
    </main>
  );
}
