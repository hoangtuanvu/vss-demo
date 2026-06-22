"use client";
import { useState } from "react";
import ReactMarkdown from "react-markdown";

import { sendChatMessage } from "../lib/api";

interface Message {
  role: "user" | "assistant";
  text: string;
}

const QUICK_ACTIONS: { label: string; prompt: string }[] = [
  { label: "Summarize today", prompt: "Summarize today's incidents." },
  { label: "Search: forklift", prompt: "Search the archive for forklift proximity incidents." },
  { label: "Search: spill", prompt: "Search the archive for spill incidents." },
];

export default function ChatPanel() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");

  async function sendMessage(text: string) {
    if (!text.trim()) return;
    const userMessage: Message = { role: "user", text };
    setMessages((prev) => [...prev, userMessage]);
    setInput("");
    const result = await sendChatMessage(text);
    setMessages((prev) => [...prev, { role: "assistant", text: result.answer }]);
  }

  return (
    <div className="mt-3 flex flex-col">
      <div className="mb-2 flex flex-wrap gap-2">
        {QUICK_ACTIONS.map((action) => (
          <button
            key={action.label}
            type="button"
            onClick={() => sendMessage(action.prompt)}
            className="border border-paper/20 px-2 py-1 font-mono text-xs uppercase tracking-widest text-paper/60 hover:border-caution hover:text-caution"
          >
            {action.label}
          </button>
        ))}
      </div>
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
            {message.role === "assistant" ? (
              <ReactMarkdown>{message.text}</ReactMarkdown>
            ) : (
              message.text
            )}
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
          onClick={() => sendMessage(input)}
          className="border border-caution px-4 py-2 font-mono text-xs uppercase tracking-widest text-caution transition-colors hover:bg-caution hover:text-ink"
        >
          Send
        </button>
      </div>
    </div>
  );
}
