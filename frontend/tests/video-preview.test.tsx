import { render, screen } from "@testing-library/react";
import { createRef } from "react";
import { describe, expect, it } from "vitest";

import VideoPreview from "../components/VideoPreview";

describe("VideoPreview", () => {
  it("renders a video element pointed at the given src", () => {
    render(<VideoPreview src="http://localhost:8000/uploads/clip.mp4" />);
    const video = screen.getByTestId("video-preview") as HTMLVideoElement;
    expect(video.querySelector("source")?.getAttribute("src")).toBe(
      "http://localhost:8000/uploads/clip.mp4"
    );
  });

  it("forwards the ref to the underlying video element", () => {
    const ref = createRef<HTMLVideoElement>();
    render(<VideoPreview src="http://localhost:8000/uploads/clip.mp4" ref={ref} />);
    expect(ref.current).toBeInstanceOf(HTMLVideoElement);
  });
});
