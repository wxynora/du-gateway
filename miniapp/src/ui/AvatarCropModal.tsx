import React, { useEffect, useRef, useState } from "react";

import { buildAvatarDataUrlFromCrop, loadImageElement } from "./imageDataUrl";

type ImageSize = {
  width: number;
  height: number;
};

type Offset = {
  x: number;
  y: number;
};

type DragState = {
  pointerId: number;
  startX: number;
  startY: number;
  baseX: number;
  baseY: number;
};

function clamp(value: number, min: number, max: number) {
  return Math.max(min, Math.min(max, value));
}

function clampOffset(next: Offset, imageSize: ImageSize | null, viewport: number, zoom: number): Offset {
  if (!imageSize || viewport <= 0) return next;
  const baseScale = Math.max(viewport / imageSize.width, viewport / imageSize.height);
  const displayWidth = imageSize.width * baseScale * zoom;
  const displayHeight = imageSize.height * baseScale * zoom;
  const maxX = Math.max(0, (displayWidth - viewport) / 2);
  const maxY = Math.max(0, (displayHeight - viewport) / 2);
  return {
    x: clamp(next.x, -maxX, maxX),
    y: clamp(next.y, -maxY, maxY),
  };
}

export function AvatarCropModal({
  src,
  title,
  onCancel,
  onConfirm,
}: {
  src: string;
  title: string;
  onCancel: () => void;
  onConfirm: (dataUrl: string) => void;
}) {
  const viewportRef = useRef<HTMLDivElement | null>(null);
  const dragRef = useRef<DragState | null>(null);
  const [imageSize, setImageSize] = useState<ImageSize | null>(null);
  const [offset, setOffset] = useState<Offset>({ x: 0, y: 0 });
  const [zoom, setZoom] = useState(1);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;
    setImageSize(null);
    setOffset({ x: 0, y: 0 });
    setZoom(1);
    setError("");
    void loadImageElement(src)
      .then((img) => {
        if (!cancelled) setImageSize({ width: img.width, height: img.height });
      })
      .catch((e: any) => {
        if (!cancelled) setError(String(e?.message || e || "图片加载失败"));
      });
    return () => {
      cancelled = true;
    };
  }, [src]);

  const viewport = viewportRef.current?.clientWidth || 0;
  const baseScale = imageSize && viewport > 0 ? Math.max(viewport / imageSize.width, viewport / imageSize.height) : 1;
  const displayWidth = imageSize ? imageSize.width * baseScale * zoom : 0;
  const displayHeight = imageSize ? imageSize.height * baseScale * zoom : 0;

  function updateZoom(value: number) {
    const nextZoom = clamp(value, 1, 3);
    const size = viewportRef.current?.clientWidth || 0;
    setZoom(nextZoom);
    setOffset((current) => clampOffset(current, imageSize, size, nextZoom));
  }

  function updateOffset(next: Offset) {
    const size = viewportRef.current?.clientWidth || 0;
    setOffset(clampOffset(next, imageSize, size, zoom));
  }

  function startDrag(event: React.PointerEvent<HTMLDivElement>) {
    if (!imageSize) return;
    event.currentTarget.setPointerCapture(event.pointerId);
    dragRef.current = {
      pointerId: event.pointerId,
      startX: event.clientX,
      startY: event.clientY,
      baseX: offset.x,
      baseY: offset.y,
    };
  }

  function moveDrag(event: React.PointerEvent<HTMLDivElement>) {
    const drag = dragRef.current;
    if (!drag || drag.pointerId !== event.pointerId) return;
    updateOffset({
      x: drag.baseX + event.clientX - drag.startX,
      y: drag.baseY + event.clientY - drag.startY,
    });
  }

  function endDrag(event: React.PointerEvent<HTMLDivElement>) {
    if (dragRef.current?.pointerId === event.pointerId) {
      dragRef.current = null;
    }
  }

  async function confirmCrop() {
    if (!imageSize || saving) return;
    const size = viewportRef.current?.clientWidth || 0;
    if (size <= 0) return;
    setSaving(true);
    setError("");
    try {
      const scale = Math.max(size / imageSize.width, size / imageSize.height) * zoom;
      const left = (size - imageSize.width * scale) / 2 + offset.x;
      const top = (size - imageSize.height * scale) / 2 + offset.y;
      const cropSize = size / scale;
      const dataUrl = await buildAvatarDataUrlFromCrop(src, {
        sx: -left / scale,
        sy: -top / scale,
        size: cropSize,
      });
      onConfirm(dataUrl);
    } catch (e: any) {
      setError(String(e?.message || e || "图片处理失败"));
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="fixed inset-0 z-[80] flex items-end justify-center bg-black/35 px-4 pb-4 pt-[calc(env(safe-area-inset-top,0px)+16px)]" role="dialog" aria-modal="true">
      <button type="button" className="absolute inset-0 cursor-default" aria-label="关闭裁剪" onClick={onCancel} />
      <div className="relative z-10 w-full max-w-[380px] rounded-[28px] bg-[#FDFDFD] p-5 shadow-[0_22px_60px_rgba(15,23,42,0.24)]">
        <div className="mb-4 flex items-center justify-between gap-3">
          <div>
            <p className="text-[12px] font-semibold text-gray-400">头像</p>
            <h2 className="text-[18px] font-bold leading-6 text-gray-900">{title}</h2>
          </div>
          <button type="button" className="rounded-full px-3 py-1.5 text-[13px] font-semibold text-gray-500 active:bg-gray-100" onClick={onCancel}>
            取消
          </button>
        </div>

        <div className="mx-auto w-full max-w-[300px]">
          <div
            ref={viewportRef}
            className="relative aspect-square w-full touch-none select-none overflow-hidden rounded-full bg-gray-100 shadow-inner"
            onPointerDown={startDrag}
            onPointerMove={moveDrag}
            onPointerUp={endDrag}
            onPointerCancel={endDrag}
          >
            {imageSize ? (
              <img
                src={src}
                alt=""
                draggable={false}
                className="absolute left-1/2 top-1/2 max-w-none"
                style={{
                  width: `${displayWidth}px`,
                  height: `${displayHeight}px`,
                  transform: `translate(calc(-50% + ${offset.x}px), calc(-50% + ${offset.y}px))`,
                }}
              />
            ) : (
              <div className="flex h-full w-full items-center justify-center text-[13px] font-medium text-gray-400">
                {error || "读取中"}
              </div>
            )}
            <span className="pointer-events-none absolute inset-0 rounded-full ring-1 ring-black/10" aria-hidden="true" />
          </div>

          <label className="mt-5 block">
            <div className="mb-2 flex items-center justify-between text-[12px] font-semibold text-gray-500">
              <span>缩放</span>
              <span>{zoom.toFixed(1)}x</span>
            </div>
            <input
              type="range"
              min="1"
              max="3"
              step="0.01"
              value={zoom}
              disabled={!imageSize}
              onChange={(event) => updateZoom(Number(event.target.value))}
              className="h-6 w-full accent-gray-900"
            />
          </label>
        </div>

        {error ? <div className="mt-3 rounded-[14px] bg-rose-50 px-3 py-2 text-[12px] font-medium text-rose-600">{error}</div> : null}

        <button
          type="button"
          className="mt-5 h-12 w-full rounded-[18px] bg-gray-900 text-[15px] font-bold text-white transition-opacity active:opacity-80 disabled:opacity-45"
          disabled={!imageSize || saving}
          onClick={() => void confirmCrop()}
        >
          {saving ? "处理中" : "使用头像"}
        </button>
      </div>
    </div>
  );
}
