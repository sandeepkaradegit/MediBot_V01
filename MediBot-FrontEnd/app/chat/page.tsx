"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth-context";
import { chatRequest, collectionsRequest } from "@/lib/api";
import Sidebar from "@/components/Sidebar";
import MessageBubble, { Message } from "@/components/MessageBubble";

export default function ChatPage() {
  const { token, role, username, loading, logout } = useAuth();
  const router = useRouter();
  const [collections, setCollections] = useState<string[]>([]);
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (loading) return;
    if (!token || !role) {
      router.replace("/login");
      return;
    }
    collectionsRequest(token, role)
      .then((res) => setCollections(res.collections))
      .catch(() => setCollections([]));
  }, [token, role, loading, router]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  async function handleSend() {
    if (!input.trim() || !token) return;
    const question = input.trim();
    setMessages((prev) => [...prev, { sender: "user", text: question }]);
    setInput("");
    setSending(true);
    try {
      const res = await chatRequest(token, question);
      setMessages((prev) => [...prev, { sender: "bot", text: res.answer, data: res }]);
    } catch (e: any) {
      setMessages((prev) => [
        ...prev,
        { sender: "bot", text: `Error: ${e.message || "Something went wrong"}` },
      ]);
    } finally {
      setSending(false);
    }
  }

  if (loading || !token) return null;

  return (
    <div className="flex h-screen">
      <Sidebar username={username} role={role} collections={collections} onLogout={() => { logout(); router.push("/login"); }} />

      <main className="flex-1 flex flex-col">
        <div className="flex-1 overflow-y-auto p-6 space-y-4">
          {messages.length === 0 && (
            <p className="text-sm text-slate-400 text-center mt-20">
              Ask MediBot about protocols, dosages, equipment, or billing data — access is scoped to your role.
            </p>
          )}
          {messages.map((m, i) => (
            <MessageBubble key={i} message={m} />
          ))}
          {sending && <p className="text-xs text-slate-400">MediBot is thinking...</p>}
          <div ref={bottomRef} />
        </div>

        <div className="border-t p-4 flex gap-2">
          <input
            className="flex-1 border rounded-lg px-3 py-2 text-sm"
            placeholder="Ask a question..."
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleSend()}
            disabled={sending}
          />
          <button
            onClick={handleSend}
            disabled={sending || !input.trim()}
            className="bg-slate-800 text-white rounded-lg px-4 py-2 text-sm disabled:opacity-50"
          >
            Send
          </button>
        </div>
      </main>
    </div>
  );
}
