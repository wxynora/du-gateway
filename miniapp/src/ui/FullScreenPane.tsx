import React, { useRef } from "react";
import { ChevronLeftIcon } from "./icons";

export function FullScreenPane({
  title,
  accent,
  onBack,
  headerMode = "default",
  edgeSwipeBack = false,
  children,
}: {
  title: string;
  accent: "du" | "wenyou" | "neutral";
  onBack: () => void;
  headerMode?: "default" | "simple";
  edgeSwipeBack?: boolean;
  children: React.ReactNode;
}) {
  const swipeRef = useRef({ tracking: false, startX: 0, startY: 0, latestX: 0, latestY: 0 });

  function handleTouchStart(e: React.TouchEvent<HTMLDivElement>) {
    if (!edgeSwipeBack) return;
    const touch = e.touches[0];
    if (!touch || touch.clientX > 36) {
      swipeRef.current.tracking = false;
      return;
    }
    swipeRef.current = {
      tracking: true,
      startX: touch.clientX,
      startY: touch.clientY,
      latestX: touch.clientX,
      latestY: touch.clientY,
    };
  }

  function handleTouchMove(e: React.TouchEvent<HTMLDivElement>) {
    if (!swipeRef.current.tracking) return;
    const touch = e.touches[0];
    if (!touch) return;
    swipeRef.current.latestX = touch.clientX;
    swipeRef.current.latestY = touch.clientY;
  }

  function handleTouchEnd() {
    const swipe = swipeRef.current;
    swipeRef.current.tracking = false;
    if (!edgeSwipeBack || !swipe.tracking) return;
    const dx = swipe.latestX - swipe.startX;
    const dy = Math.abs(swipe.latestY - swipe.startY);
    if (dx >= 72 && dx > dy * 1.5) {
      onBack();
    }
  }

  return (
    <div
      className="absolute inset-0 z-30 flex w-full max-w-full flex-col overflow-x-hidden bg-[#FDFDFD]"
      onTouchStart={handleTouchStart}
      onTouchMove={handleTouchMove}
      onTouchEnd={handleTouchEnd}
      onTouchCancel={() => {
        swipeRef.current.tracking = false;
      }}
    >
      {headerMode === "simple" ? (
        <div className="border-b border-gray-100/50 bg-white px-4 pb-3 pt-[calc(env(safe-area-inset-top,0px)+12px)]">
          <button className="flex items-center gap-2 text-gray-900" onClick={onBack}>
            <ChevronLeftIcon />
            <span className="text-[15px] font-medium">{title}</span>
          </button>
        </div>
      ) : (
        <div className="absolute top-0 z-20 flex w-full items-center border-b border-gray-100/50 bg-white/80 px-3 pb-3 pt-[calc(env(safe-area-inset-top,0px)+12px)] backdrop-blur-md">
          <button className="rounded-full p-2 text-gray-500 transition-colors active:bg-gray-100" onClick={onBack}>
            <ChevronLeftIcon />
          </button>
          <div className="ml-2 text-[15px] font-medium text-gray-900">{title}</div>
        </div>
      )}
      <div className={`min-h-0 w-full max-w-full flex-1 overflow-x-hidden overflow-y-auto px-3.5 pb-4 ${headerMode === "simple" ? "pt-0" : "pt-[82px]"}`}>{children}</div>
    </div>
  );
}
