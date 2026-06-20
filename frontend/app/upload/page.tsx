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
    <main className="min-h-screen">
      <div className="hazard-tape h-2 w-full" aria-hidden="true" />
      <div className="mx-auto max-w-2xl px-6 py-16">
        <p className="font-mono text-xs uppercase tracking-[0.3em] text-caution">Intake</p>
        <h1 className="mt-4 font-display text-3xl">Upload Video</h1>
        <p className="mt-2 text-sm text-paper/60">
          The clip is replayed on a loop through the warehouse's RTSP feed, as if it were a live
          camera.
        </p>

        <form onSubmit={handleSubmit} className="mt-8 border border-paper/15 bg-panel p-6">
          <label htmlFor="file" className="block font-mono text-xs uppercase tracking-widest text-paper/50">
            Clip
          </label>
          <input
            id="file"
            type="file"
            name="file"
            accept="video/*"
            data-testid="file-input"
            className="mt-3 block w-full text-sm text-paper/80 file:mr-4 file:border file:border-paper/20 file:bg-ink file:px-4 file:py-2 file:text-sm file:text-paper file:transition-colors hover:file:border-caution"
          />
          <button
            type="submit"
            className="mt-5 border border-caution bg-caution px-5 py-2 font-mono text-sm uppercase tracking-widest text-ink transition-colors hover:bg-ink hover:text-caution"
          >
            Upload
          </button>
        </form>

        {status && (
          <p data-testid="upload-status" className="mt-6 border-l-2 border-signal pl-3 font-mono text-sm text-signal">
            {status}
          </p>
        )}
        {error && (
          <p data-testid="upload-error" className="mt-6 border-l-2 border-alarm pl-3 font-mono text-sm text-alarm">
            {error}
          </p>
        )}
      </div>
    </main>
  );
}
