"use client";

import { createContext, useContext, useEffect, useState, ReactNode } from "react";

interface AuthState {
  token: string | null;
  role: string | null;
  username: string | null;
  loading: boolean;
  login: (token: string, role: string, username: string) => void;
  logout: () => void;
}

const AuthContext = createContext<AuthState | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [token, setToken] = useState<string | null>(null);
  const [role, setRole] = useState<string | null>(null);
  const [username, setUsername] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setToken(localStorage.getItem("medibot_token"));
    setRole(localStorage.getItem("medibot_role"));
    setUsername(localStorage.getItem("medibot_username"));
    setLoading(false);
  }, []);

  function login(newToken: string, newRole: string, newUsername: string) {
    localStorage.setItem("medibot_token", newToken);
    localStorage.setItem("medibot_role", newRole);
    localStorage.setItem("medibot_username", newUsername);
    setToken(newToken);
    setRole(newRole);
    setUsername(newUsername);
  }

  function logout() {
    localStorage.removeItem("medibot_token");
    localStorage.removeItem("medibot_role");
    localStorage.removeItem("medibot_username");
    setToken(null);
    setRole(null);
    setUsername(null);
  }

  return (
    <AuthContext.Provider value={{ token, role, username, loading, login, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
