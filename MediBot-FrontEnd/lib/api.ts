const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";

export interface Source {
  source_document: string;
  section_title: string;
  collection: string;
}

export interface ChatResponse {
  answer: string;
  sources: Source[];
  retrieval_type: "hybrid_rag" | "sql_rag";
  role: string;
}

export interface LoginResponse {
  access_token: string;
  token_type: string;
  role: string;
}

async function handleResponse<T>(res: Response): Promise<T> {
  if (!res.ok) {
    const body = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(body.detail || "Request failed");
  }
  return res.json();
}

export async function loginRequest(username: string, password: string): Promise<LoginResponse> {
  const body = new URLSearchParams({ username, password });
  const res = await fetch(`${API_URL}/login`, {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body,
  });
  return handleResponse<LoginResponse>(res);
}

export async function chatRequest(token: string, question: string): Promise<ChatResponse> {
  const res = await fetch(`${API_URL}/chat`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify({ question }),
  });
  return handleResponse<ChatResponse>(res);
}

export async function collectionsRequest(token: string, role: string): Promise<{ role: string; collections: string[] }> {
  const res = await fetch(`${API_URL}/collections/${role}`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  return handleResponse(res);
}
