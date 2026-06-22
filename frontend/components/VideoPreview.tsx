import { forwardRef } from "react";

const VideoPreview = forwardRef<HTMLVideoElement, { src: string }>(function VideoPreview(
  { src },
  ref
) {
  return (
    <video
      ref={ref}
      data-testid="video-preview"
      controls
      className="w-full border border-paper/15 bg-ink"
    >
      <source src={src} type="video/mp4" />
    </video>
  );
});

export default VideoPreview;
