import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

vi.mock("../lib/api", () => ({ uploadVideo: vi.fn() }));

import UploadBar from "../components/UploadBar";
import { uploadVideo } from "../lib/api";

describe("UploadBar", () => {
  it("shows the stream status after a successful upload", async () => {
    (uploadVideo as any).mockResolvedValue({ stream_url: "rtsp://localhost:8554/cam1" });
    render(<UploadBar />);

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
    render(<UploadBar />);

    const file = new File(["fake"], "clip.mp4", { type: "video/mp4" });
    const input = screen.getByTestId("file-input") as HTMLInputElement;
    fireEvent.change(input, { target: { files: [file] } });
    fireEvent.click(screen.getByText("Upload"));

    await waitFor(() => {
      expect(screen.getByTestId("upload-error")).toBeTruthy();
    });
  });

  it("calls onUploaded with the returned filename", async () => {
    (uploadVideo as any).mockResolvedValue({ stream_url: "rtsp://localhost:8554/cam1", filename: "cam1.mp4" });
    const onUploaded = vi.fn();
    render(<UploadBar onUploaded={onUploaded} />);

    const file = new File(["fake"], "cam1.mp4", { type: "video/mp4" });
    const input = screen.getByTestId("file-input") as HTMLInputElement;
    fireEvent.change(input, { target: { files: [file] } });
    fireEvent.click(screen.getByText("Upload"));

    await waitFor(() => {
      expect(onUploaded).toHaveBeenCalledWith("cam1.mp4");
    });
  });
});
