import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

vi.mock("../lib/api", () => ({ sendChatMessage: vi.fn() }));

import ChatPanel from "../components/ChatPanel";
import { sendChatMessage } from "../lib/api";

describe("ChatPanel", () => {
  it("sends a message and renders the reply", async () => {
    (sendChatMessage as any).mockResolvedValue({ answer: "Two PPE violations today." });
    render(<ChatPanel />);

    fireEvent.change(screen.getByTestId("chat-input"), { target: { value: "how many ppe violations today?" } });
    fireEvent.click(screen.getByText("Send"));

    await waitFor(() => {
      expect(screen.getByTestId("chat-history").textContent).toContain("Two PPE violations today.");
    });
  });

  it("renders markdown in assistant replies", async () => {
    (sendChatMessage as any).mockResolvedValue({ answer: "**Two** PPE violations today." });
    render(<ChatPanel />);

    fireEvent.change(screen.getByTestId("chat-input"), { target: { value: "how many ppe violations today?" } });
    fireEvent.click(screen.getByText("Send"));

    await waitFor(() => {
      const history = screen.getByTestId("chat-history");
      expect(history.querySelector("strong")?.textContent).toBe("Two");
    });
  });

  it("does not markdown-render the user's own message", async () => {
    (sendChatMessage as any).mockResolvedValue({ answer: "ok" });
    render(<ChatPanel />);

    fireEvent.change(screen.getByTestId("chat-input"), { target: { value: "**not markdown**" } });
    fireEvent.click(screen.getByText("Send"));

    await waitFor(() => {
      const history = screen.getByTestId("chat-history");
      expect(history.textContent).toContain("**not markdown**");
      expect(history.querySelector("strong")).toBeNull();
    });
  });
});
