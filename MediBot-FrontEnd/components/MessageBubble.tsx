"use client";

import { ChatResponse } from "@/lib/api";

const COLLECTION_COLORS: Record<string, string> = {
  general: "bg-slate-200 text-slate-700",
  clinical: "bg-blue-100 text-blue-800",
  nursing: "bg-pink-100 text-pink-800",
  billing: "bg-amber-100 text-amber-800",
  equipment: "bg-purple-100 text-purple-800",
};

export interface Message {
  sender: "user" | "bot";
  text: string;
  data?: ChatResponse;
}

export default function MessageBubble({ message }: { message: Message }) {
  if (message.sender === "user") {
    return (
      <div className="flex justify-end">
        <div className="bg-slate-800 text-white rounded-2xl rounded-br-sm px-4 py-2 max-w-lg text-sm">
          {message.text}
        </div>
      </div>
    );
  }

  const data = message.data;
  const isBlocked = data && data.sources.length === 0 && data.retrieval_type === "hybrid_rag";

  return (
    <div className="flex justify-start">
      <div
        className={`rounded-2xl rounded-bl-sm px-4 py-3 max-w-xl text-sm space-y-2 ${
          isBlocked ? "bg-amber-50 border border-amber-200" : "bg-white border"
        }`}
      >
        {data && (
          <span
            className={`inline-block text-xs px-2 py-0.5 rounded-full font-medium ${
              data.retrieval_type === "sql_rag"
                ? "bg-indigo-100 text-indigo-800"
                : "bg-teal-100 text-teal-800"
            }`}
          >
            {data.retrieval_type === "sql_rag" ? "SQL RAG" : "Hybrid RAG"}
          </span>
        )}

        <p className="whitespace-pre-wrap text-slate-800">{message.text}</p>

        {data && data.sources.length > 0 && (
          <div className="pt-2 border-t space-y-1">
            <p className="text-xs text-slate-400">Sources</p>
            {data.sources.map((s, i) => (
              <div key={i} className="flex items-center gap-2 text-xs">
                <span
                  className={`px-1.5 py-0.5 rounded-md font-medium ${
                    COLLECTION_COLORS[s.collection] || "bg-slate-100 text-slate-700"
                  }`}
                >
                  {s.collection}
                </span>
                <span className="text-slate-600">
                  {s.source_document} — {s.section_title}
                </span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
