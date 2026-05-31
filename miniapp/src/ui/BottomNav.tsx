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
    <nav
      className="pointer-events-none fixed inset-x-0 bottom-0 z-40 px-4 pb-[calc(env(safe-area-inset-bottom,0px)+14px)]"
      aria-label="主导航"
    >
      <div className="pointer-events-auto mx-auto grid w-full max-w-[360px] grid-cols-5 gap-1 rounded-[30px] border border-white/70 bg-[rgba(250,250,252,0.78)] px-2.5 py-2 shadow-[0_18px_38px_rgba(31,41,55,0.18),0_3px_10px_rgba(31,41,55,0.08),inset_0_1px_0_rgba(255,255,255,0.86)] backdrop-blur-2xl">
        {items.map((item) => {
          const active = current === item.id;
          return (
            <button
              key={item.id}
              className={`group flex h-[58px] min-w-0 flex-col items-center justify-center rounded-[22px] transition-[background-color,color,transform,box-shadow] duration-200 ease-out active:scale-95 ${
                active
                  ? "translate-y-[-3px] bg-white text-gray-950 shadow-[0_10px_20px_rgba(31,41,55,0.14),inset_0_1px_0_rgba(255,255,255,0.95)]"
                  : "text-gray-400 hover:bg-white/55 hover:text-gray-700"
              }`}
              onClick={() => onChange(item.id)}
              aria-current={active ? "page" : undefined}
            >
              <BottomNavIcon id={item.id} className={`h-[22px] w-[22px] transition-transform duration-200 ${active ? "scale-105" : "group-hover:scale-105"}`} />
              <span className={`mt-1 text-[10px] font-semibold leading-none ${active ? "opacity-100" : "opacity-70"}`}>{item.label}</span>
            </button>
          );
        })}
      </div>
    </nav>
  );
}
