import { BottomNavIcon } from "./icons";

export type MainTab = "chats" | "daily" | "tools" | "settings";

export function BottomNav({
  current,
  onChange,
  hasAppBackground = false,
  darkBackground = false,
}: {
  current: MainTab;
  onChange: (tab: MainTab) => void;
  hasAppBackground?: boolean;
  darkBackground?: boolean;
}) {
  const items: Array<{ id: MainTab; label: string }> = [
    { id: "chats", label: "会话" },
    { id: "daily", label: "日常" },
    { id: "tools", label: "工具" },
    { id: "settings", label: "设置" },
  ];
  return (
    <nav
      className="pointer-events-none fixed inset-x-0 bottom-0 z-40 px-6 pb-[calc(env(safe-area-inset-bottom,0px)+12px)]"
      aria-label="主导航"
    >
      <div
        className={`pointer-events-auto mx-auto grid w-full max-w-[292px] grid-cols-4 gap-1 rounded-full px-1.5 py-1.5 shadow-[0_12px_28px_rgba(31,41,55,0.14),0_2px_8px_rgba(31,41,55,0.08),inset_0_1px_0_rgba(255,255,255,0.45)] ${
          hasAppBackground
            ? darkBackground
              ? "border border-white/18 bg-black/36"
              : "border border-white/75 bg-white/76"
            : "border border-white/75 bg-[rgba(250,250,252,0.78)] backdrop-blur-2xl"
        }`}
      >
        {items.map((item) => {
          const active = current === item.id;
          return (
            <button
              key={item.id}
              className={`group flex h-[44px] min-w-0 flex-col items-center justify-center rounded-full transition-[background-color,color,transform,box-shadow] duration-200 ease-out active:scale-95 ${
                active
                  ? darkBackground && hasAppBackground
                    ? "bg-white/18 text-white shadow-[0_5px_14px_rgba(0,0,0,0.18),inset_0_1px_0_rgba(255,255,255,0.18)]"
                    : "bg-white text-gray-950 shadow-[0_5px_14px_rgba(31,41,55,0.12),inset_0_1px_0_rgba(255,255,255,0.96)]"
                  : darkBackground && hasAppBackground
                    ? "text-white/62 hover:bg-white/12 hover:text-white"
                    : "text-gray-400 hover:bg-white/55 hover:text-gray-700"
              }`}
              onClick={() => onChange(item.id)}
              aria-current={active ? "page" : undefined}
            >
              <BottomNavIcon id={item.id} className={`h-[20px] w-[20px] transition-transform duration-200 ${active ? "scale-105" : "group-hover:scale-105"}`} />
              <span className={`mt-0.5 text-[10px] font-semibold leading-none ${active ? "opacity-100" : "opacity-70"}`}>{item.label}</span>
            </button>
          );
        })}
      </div>
    </nav>
  );
}
