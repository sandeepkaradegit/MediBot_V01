"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { loginRequest } from "../../lib/api";
import { useAuth } from "@/lib/auth-context";

const DEMO_ACCOUNTS = [
  { username: "dr.mehta", password: "doctor", label: "Doctor" },
  { username: "nurse.priya", password: "nurse", label: "Nurse" },
  { username: "billing.ravi", password: "billing_executive", label: "Billing Executive" },
  { username: "tech.anand", password: "technician", label: "Technician" },
  { username: "admin.sys", password: "admin", label: "Admin" },
];

export default function LoginPage() {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const { login } = useAuth();
  const router = useRouter();

  async function doLogin(u: string, p: string) {
    setError("");
    setSubmitting(true);
    try {
      const res = await loginRequest(u, p);
      login(res.access_token, res.role, u);
      router.push("/chat");
    } catch (e: any) {
      setError(e.message || "Login failed");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main className="min-h-screen flex items-center justify-center p-6">
      <div className="w-full max-w-md bg-white rounded-2xl shadow-lg p-8 space-y-6">
        <div className="text-center">
          <h1 className="text-2xl font-bold text-slate-800">MediBot</h1>
          <p className="text-sm text-slate-500 mt-1">MediAssist Health Network — sign in</p>
        </div>

        <form
          onSubmit={(e) => {
            e.preventDefault();
            doLogin(username, password);
          }}
          className="space-y-3"
        >
          <input
            className="w-full border rounded-lg px-3 py-2 text-sm"
            placeholder="Username"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
          />
          <input
            className="w-full border rounded-lg px-3 py-2 text-sm"
            placeholder="Password"
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
          {error && <p className="text-sm text-red-600">{error}</p>}
          <button
            type="submit"
            disabled={submitting}
            className="w-full bg-slate-800 text-white rounded-lg py-2 text-sm font-medium disabled:opacity-50"
          >
            {submitting ? "Signing in..." : "Sign in"}
          </button>
        </form>

        <div>
          <p className="text-xs text-slate-400 mb-2 text-center">Quick demo login</p>
          <div className="grid grid-cols-2 gap-2">
            {DEMO_ACCOUNTS.map((acc) => (
              <button
                key={acc.username}
                onClick={() => doLogin(acc.username, acc.password)}
                disabled={submitting}
                className="text-xs border rounded-lg py-2 hover:bg-slate-100 disabled:opacity-50"
              >
                {acc.label}
              </button>
            ))}
          </div>
        </div>
      </div>
    </main>
  );
}
