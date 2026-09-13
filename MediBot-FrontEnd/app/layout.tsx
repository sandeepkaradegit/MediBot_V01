import "./globals.css";
import { AuthProvider } from "@/lib/auth-context";

export const metadata = { title: "MediBot", description: "Hospital knowledge assistant" };

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="bg-slate-50 text-slate-900">
        <AuthProvider>{children}</AuthProvider>
      </body>
    </html>
  );
}
