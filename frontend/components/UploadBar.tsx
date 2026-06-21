"use client";
import { useState } from "react";

import { uploadVideo } from "../lib/api";

export default function UploadBar() {
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
    <div className="border border-paper/15 bg-panel p-4">
      <form onSubmit={handleSubmit} className="flex flex-wrap items-center gap-3">
        <label htmlFor="file" className="font-mono text-xs uppercase tracking-widest text-paper/50">
          New clip
        </label>
        <input
          id="file"
          type="file"
          name="file"
          accept="video/*"
          data-testid="file-input"
          className="block text-sm text-paper/80 file:mr-4 file:border file:border-paper/20 file:bg-ink file:px-3 file:py-1.5 file:text-sm file:text-paper file:transition-colors hover:file:border-caution"
        />
        <button
          type="submit"
          className="border border-caution bg-caution px-4 py-1.5 font-mono text-xs uppercase tracking-widest text-ink transition-colors hover:bg-ink hover:text-caution"
        >
          Upload
        </button>
      </form>
      {status && (
        <p data-testid="upload-status" className="mt-3 border-l-2 border-signal pl-3 font-mono text-sm text-signal">
          {status}
        </p>
      )}
      {error && (
        <p data-testid="upload-error" className="mt-3 border-l-2 border-alarm pl-3 font-mono text-sm text-alarm">
          {error}
        </p>
      )}
    </div>
  );
}
