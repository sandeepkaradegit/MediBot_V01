"use client";

const ROLE_COLORS: Record<string, string> = {
  doctor: "bg-blue-100 text-blue-800",
  nurse: "bg-pink-100 text-pink-800",
  billing_executive: "bg-amber-100 text-amber-800",
  technician: "bg-purple-100 text-purple-800",
  admin: "bg-emerald-100 text-emerald-800",
};

export default function Sidebar({
  username,
  role,
  collections,
  onLogout,
}: {
  username: string | null;
  role: string | null;
  collections: string[];
  onLogout: () => void;
}) {
  const badgeClass = role ? ROLE_COLORS[role] || "bg-slate-100 text-slate-800" : "";

  return (
    <aside className="w-64 border-r bg-white flex flex-col p-4 gap-6">
      <div>
        <h1 className="text-lg font-bold text-slate-800">MediBot</h1>
        <p className="text-xs text-slate-400">MediAssist Health Network</p>
      </div>

      <div className="space-y-1">
        <p className="text-xs text-slate-400">Signed in as</p>
        <p className="text-sm font-medium">{username}</p>
        {role && (
          <span className={`inline-block mt-1 text-xs px-2 py-1 rounded-full font-medium ${badgeClass}`}>
            {role}
          </span>
        )}
      </div>

      <div className="space-y-2">
        <p className="text-xs text-slate-400">Accessible collections</p>
        <div className="flex flex-col gap-1">
          {collections.map((c) => (
            <span key={c} className="text-xs bg-slate-100 rounded-md px-2 py-1">
              {c}
            </span>
          ))}
        </div>
      </div>

      <button
        onClick={onLogout}
        className="mt-auto text-xs text-red-600 border border-red-200 rounded-lg py-2 hover:bg-red-50"
      >
        Log out
      </button>
    </aside>
  );
}
