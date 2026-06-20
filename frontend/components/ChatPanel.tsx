"use client";
import { useState } from "react";

import { sendChatMessage } from "../lib/api";

interface Message {
  role: "user" | "assistant";
  text: string;
}

export default function ChatPanel() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");

  async function handleSend() {
    if (!input.trim()) return;
    const userMessage: Message = { role: "user", text: input };
    setMessages((prev) => [...prev, userMessage]);
    setInput("");
    const result = await sendChatMessage(userMessage.text);
    setMessages((prev) => [...prev, { role: "assistant", text: result.answer }]);
  }

  return (
    <div className="mt-3 flex flex-col">
      <ul data-testid="chat-history" className="flex max-h-64 flex-col gap-2 overflow-y-auto text-sm">
        {messages.length === 0 && (
          <li className="text-paper/40">Ask about a hazard, a zone, or how to prevent the next one.</li>
        )}
        {messages.map((message, index) => (
          <li
            key={index}
            className={message.role === "user" ? "text-paper" : "border-l-2 border-signal pl-2 text-paper/80"}
          >
            <span className="font-mono text-xs uppercase tracking-widest text-paper/40">{message.role}</span>
            <br />
            {message.text}
          </li>
        ))}
      </ul>
      <div className="mt-3 flex gap-2">
        <input
          data-testid="chat-input"
          value={input}
          onChange={(event) => setInput(event.target.value)}
          placeholder="Ask the floor…"
          className="flex-1 border border-paper/20 bg-ink px-3 py-2 text-sm text-paper outline-none focus-visible:border-caution"
        />
        <button
          onClick={handleSend}
          className="border border-caution px-4 py-2 font-mono text-xs uppercase tracking-widest text-caution transition-colors hover:bg-caution hover:text-ink"
        >
          Send
        </button>
      </div>
    </div>
  );
}
