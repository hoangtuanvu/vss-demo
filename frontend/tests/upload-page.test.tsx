import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

vi.mock("../lib/api", () => ({ uploadVideo: vi.fn() }));

import UploadPage from "../app/upload/page";
import { uploadVideo } from "../lib/api";

describe("UploadPage", () => {
  it("shows the stream status after a successful upload", async () => {
    (uploadVideo as any).mockResolvedValue({ stream_url: "rtsp://localhost:8554/cam1" });
    render(<UploadPage />);

    const file = new File(["fake"], "clip.mp4", { type: "video/mp4" });
    const input = screen.getByTestId("file-input") as HTMLInputElement;
    fireEvent.change(input, { target: { files: [file] } });
    fireEvent.click(screen.getByText("Upload"));

    await waitFor(() => {
      expect(screen.getByTestId("upload-status").textContent).toContain("rtsp://localhost:8554/cam1");
    });
  });

  it("shows an error message when the upload fails", async () => {
    (uploadVideo as any).mockRejectedValue(new Error("boom"));
    render(<UploadPage />);

    const file = new File(["fake"], "clip.mp4", { type: "video/mp4" });
    const input = screen.getByTestId("file-input") as HTMLInputElement;
    fireEvent.change(input, { target: { files: [file] } });
    fireEvent.click(screen.getByText("Upload"));

    await waitFor(() => {
      expect(screen.getByTestId("upload-error")).toBeTruthy();
    });
  });
});
