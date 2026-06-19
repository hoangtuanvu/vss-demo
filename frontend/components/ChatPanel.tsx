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
    <div>
      <ul data-testid="chat-history">
        {messages.map((message, index) => (
          <li key={index}>
            {message.role}: {message.text}
          </li>
        ))}
      </ul>
      <input data-testid="chat-input" value={input} onChange={(event) => setInput(event.target.value)} />
      <button onClick={handleSend}>Send</button>
    </div>
  );
}
