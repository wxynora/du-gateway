import { BottomNavIcon } from "./icons";

export type MainTab = "chats" | "daily" | "study" | "tools" | "settings";

export function BottomNav({
  current,
  onChange,
}: {
  current: MainTab;
  onChange: (tab: MainTab) => void;
}) {
  const items: Array<{ id: MainTab; label: string }> = [
    { id: "chats", label: "会话" },
    { id: "daily", label: "日常" },
    { id: "study", label: "学习" },
    { id: "tools", label: "工具" },
    { id: "settings", label: "设置" },
  ];
  return (
    <nav className="fixed inset-x-0 bottom-0 z-40 flex items-center justify-between border-t border-gray-100 bg-white/90 px-4 pb-[calc(env(safe-area-inset-bottom,20px))] pt-2 backdrop-blur-md">
      <div className="mx-auto flex w-full max-w-xl items-center justify-between">
        {items.map((item) => {
          const active = current === item.id;
          return (
            <button
              key={item.id}
              className={`flex flex-col items-center p-2 transition-colors ${active ? "text-gray-900" : "text-gray-400 hover:text-gray-600"}`}
              onClick={() => onChange(item.id)}
            >
              <BottomNavIcon id={item.id} />
              <span className="text-[10px] font-medium tracking-wide">{item.label}</span>
            </button>
          );
        })}
      </div>
    </nav>
  );
}
