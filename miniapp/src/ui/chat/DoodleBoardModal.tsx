import React, { useEffect, useRef, useState } from "react";

const CANVAS_WIDTH = 720;
const CANVAS_HEIGHT = 960;
const PAPER_COLOR = "#fffdf8";
const BRUSH_COLORS = ["#111827", "#ef4444", "#f59e0b", "#22c55e", "#38bdf8", "#a855f7"];
const BRUSH_SIZES = [4, 8, 14, 22];
const MAX_HISTORY = 10;

type DoodleTool = "brush" | "eraser";

type DoodleBoardModalProps = {
  open: boolean;
  disabled?: boolean;
  onClose: () => void;
  onSend: (file: File) => Promise<boolean>;
};

type Point = {
  x: number;
  y: number;
};

export function DoodleBoardModal({ open, disabled = false, onClose, onSend }: DoodleBoardModalProps) {
  const modalRef = useRef<HTMLDivElement | null>(null);
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const historyRef = useRef<ImageData[]>([]);
  const drawingRef = useRef(false);
  const lastPointRef = useRef<Point | null>(null);
  const [tool, setTool] = useState<DoodleTool>("brush");
  const [color, setColor] = useState(BRUSH_COLORS[0]);
  const [size, setSize] = useState(8);
  const [canUndo, setCanUndo] = useState(false);
  const [hasInk, setHasInk] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [error, setError] = useState("");

  function getContext() {
    return canvasRef.current?.getContext("2d", { willReadFrequently: true }) || null;
  }

  function updateUndoState() {
    setCanUndo(historyRef.current.length > 1);
  }

  function pushSnapshot() {
    const ctx = getContext();
    if (!ctx) return;
    const snapshot = ctx.getImageData(0, 0, CANVAS_WIDTH, CANVAS_HEIGHT);
    historyRef.current = [...historyRef.current.slice(-(MAX_HISTORY - 1)), snapshot];
    updateUndoState();
  }

  function resetCanvas() {
    const ctx = getContext();
    if (!ctx) return;
    ctx.save();
    ctx.globalCompositeOperation = "source-over";
    ctx.fillStyle = PAPER_COLOR;
    ctx.fillRect(0, 0, CANVAS_WIDTH, CANVAS_HEIGHT);
    ctx.restore();
    historyRef.current = [];
    pushSnapshot();
    setHasInk(false);
    setError("");
  }

  useEffect(() => {
    if (!open) {
      historyRef.current = [];
      drawingRef.current = false;
      lastPointRef.current = null;
      setCanUndo(false);
      setHasInk(false);
      setExporting(false);
      setError("");
      return;
    }
    const timer = window.setTimeout(() => {
      resetCanvas();
      modalRef.current?.focus({ preventScroll: true });
    }, 0);
    return () => window.clearTimeout(timer);
  }, [open]);

  if (!open) return null;

  function canvasPoint(event: React.PointerEvent<HTMLCanvasElement>): Point {
    const canvas = canvasRef.current;
    const rect = canvas?.getBoundingClientRect();
    if (!rect || rect.width <= 0 || rect.height <= 0) return { x: 0, y: 0 };
    return {
      x: Math.max(0, Math.min(CANVAS_WIDTH, ((event.clientX - rect.left) / rect.width) * CANVAS_WIDTH)),
      y: Math.max(0, Math.min(CANVAS_HEIGHT, ((event.clientY - rect.top) / rect.height) * CANVAS_HEIGHT)),
    };
  }

  function drawSegment(from: Point, to: Point) {
    const ctx = getContext();
    if (!ctx) return;
    const width = tool === "eraser" ? size * 2 : size;
    ctx.save();
    ctx.globalCompositeOperation = "source-over";
    ctx.strokeStyle = tool === "eraser" ? PAPER_COLOR : color;
    ctx.fillStyle = tool === "eraser" ? PAPER_COLOR : color;
    ctx.lineWidth = width;
    ctx.lineCap = "round";
    ctx.lineJoin = "round";
    ctx.beginPath();
    ctx.moveTo(from.x, from.y);
    ctx.lineTo(to.x, to.y);
    ctx.stroke();
    ctx.beginPath();
    ctx.arc(to.x, to.y, width / 2, 0, Math.PI * 2);
    ctx.fill();
    ctx.restore();
  }

  function handlePointerDown(event: React.PointerEvent<HTMLCanvasElement>) {
    if (disabled || exporting) return;
    event.preventDefault();
    const point = canvasPoint(event);
    drawingRef.current = true;
    lastPointRef.current = point;
    setError("");
    try {
      event.currentTarget.setPointerCapture?.(event.pointerId);
    } catch {}
    drawSegment(point, point);
    setHasInk(true);
  }

  function handlePointerMove(event: React.PointerEvent<HTMLCanvasElement>) {
    if (!drawingRef.current) return;
    event.preventDefault();
    const nextPoint = canvasPoint(event);
    const lastPoint = lastPointRef.current || nextPoint;
    drawSegment(lastPoint, nextPoint);
    lastPointRef.current = nextPoint;
  }

  function finishStroke(event?: React.PointerEvent<HTMLCanvasElement>) {
    if (!drawingRef.current) return;
    drawingRef.current = false;
    lastPointRef.current = null;
    try {
      if (event) event.currentTarget.releasePointerCapture?.(event.pointerId);
    } catch {}
    pushSnapshot();
  }

  function undo() {
    const ctx = getContext();
    if (!ctx || historyRef.current.length <= 1) return;
    historyRef.current = historyRef.current.slice(0, -1);
    const previous = historyRef.current[historyRef.current.length - 1];
    ctx.putImageData(previous, 0, 0);
    setHasInk(historyRef.current.length > 1);
    updateUndoState();
  }

  async function exportAndSend() {
    const canvas = canvasRef.current;
    if (!canvas || disabled || exporting || !hasInk) return;
    setExporting(true);
    setError("");
    try {
      const blob = await new Promise<Blob>((resolve, reject) => {
        canvas.toBlob((result) => {
          if (result) resolve(result);
          else reject(new Error("涂鸦导出失败"));
        }, "image/png");
      });
      const file = new File([blob], `doodle-${Date.now()}.png`, { type: "image/png" });
      const sent = await onSend(file);
      if (sent) onClose();
      else setError("涂鸦没发出去，等一下再试。");
    } catch (e: any) {
      setError(String(e?.message || e || "涂鸦导出失败"));
    } finally {
      setExporting(false);
    }
  }

  return (
    <div className="fixed inset-0 z-[80] flex items-end justify-center bg-black/24 px-3 pb-[calc(env(safe-area-inset-bottom,0px)+12px)] pt-10 backdrop-blur-[2px]">
      <button type="button" className="absolute inset-0 cursor-default" aria-label="关闭画板" onClick={onClose} />
      <div
        ref={modalRef}
        role="dialog"
        aria-modal="true"
        aria-label="画画"
        tabIndex={-1}
        className="relative z-10 w-full max-w-[440px] overflow-hidden rounded-[30px] border border-white/70 bg-[#fffaf2]/95 p-3 shadow-[0_18px_60px_rgba(15,23,42,0.22)] outline-none"
        onKeyDown={(event) => {
          if (event.key === "Escape") onClose();
        }}
      >
        <div className="mb-2 flex items-center justify-between px-1">
          <div>
            <div className="text-[15px] font-semibold text-gray-900">画画</div>
            <div className="text-[11px] font-medium text-gray-400">随便涂两笔就能发给渡</div>
          </div>
          <button
            type="button"
            className="flex h-8 w-8 items-center justify-center rounded-full bg-white/70 text-[20px] leading-none text-gray-400 active:bg-white active:text-gray-700"
            onClick={onClose}
            aria-label="关闭"
            title="关闭"
          >
            ×
          </button>
        </div>

        <div className="overflow-hidden rounded-[24px] border border-[#eadfce] bg-white shadow-inner">
          <canvas
            ref={canvasRef}
            width={CANVAS_WIDTH}
            height={CANVAS_HEIGHT}
            className="block aspect-[3/4] w-full touch-none bg-[#fffdf8]"
            onPointerDown={handlePointerDown}
            onPointerMove={handlePointerMove}
            onPointerUp={finishStroke}
            onPointerCancel={finishStroke}
            onLostPointerCapture={finishStroke}
          />
        </div>

        <div className="mt-3 space-y-3">
          <div className="flex items-center justify-between gap-2">
            <div className="flex rounded-full bg-white/65 p-1">
              <button
                type="button"
                className={`rounded-full px-3 py-1 text-[12px] font-semibold ${tool === "brush" ? "bg-gray-900 text-white" : "text-gray-500"}`}
                onClick={() => setTool("brush")}
              >
                画笔
              </button>
              <button
                type="button"
                className={`rounded-full px-3 py-1 text-[12px] font-semibold ${tool === "eraser" ? "bg-gray-900 text-white" : "text-gray-500"}`}
                onClick={() => setTool("eraser")}
              >
                橡皮
              </button>
            </div>
            <div className="flex items-center gap-1.5">
              {BRUSH_SIZES.map((item) => (
                <button
                  key={item}
                  type="button"
                  className={`flex h-8 w-8 items-center justify-center rounded-full bg-white/70 ${size === item ? "ring-2 ring-gray-900/70" : ""}`}
                  onClick={() => setSize(item)}
                  aria-label={`笔粗 ${item}`}
                  title={`笔粗 ${item}`}
                >
                  <span className="rounded-full bg-gray-700" style={{ width: Math.max(4, item), height: Math.max(4, item) }} />
                </button>
              ))}
            </div>
          </div>

          <div className="flex items-center justify-between gap-2">
            <div className="flex items-center gap-1.5">
              {BRUSH_COLORS.map((item) => (
                <button
                  key={item}
                  type="button"
                  className={`h-8 w-8 rounded-full border border-white shadow-sm ${tool === "brush" && color === item ? "ring-2 ring-gray-900/70 ring-offset-2 ring-offset-[#fffaf2]" : ""}`}
                  style={{ backgroundColor: item }}
                  onClick={() => {
                    setTool("brush");
                    setColor(item);
                  }}
                  aria-label={`颜色 ${item}`}
                  title={`颜色 ${item}`}
                />
              ))}
            </div>
            <div className="flex items-center gap-1.5">
              <button
                type="button"
                className="rounded-full bg-white/65 px-3 py-1.5 text-[12px] font-semibold text-gray-500 active:bg-white disabled:opacity-35"
                onClick={undo}
                disabled={!canUndo || disabled || exporting}
              >
                撤回
              </button>
              <button
                type="button"
                className="rounded-full bg-white/65 px-3 py-1.5 text-[12px] font-semibold text-gray-500 active:bg-white disabled:opacity-35"
                onClick={resetCanvas}
                disabled={disabled || exporting}
              >
                清空
              </button>
            </div>
          </div>

          <button
            type="button"
            className="h-11 w-full rounded-full bg-gray-900 text-[14px] font-semibold text-white shadow-[0_10px_26px_rgba(15,23,42,0.22)] active:scale-[0.99] disabled:bg-gray-300 disabled:shadow-none"
            onClick={() => void exportAndSend()}
            disabled={!hasInk || disabled || exporting}
          >
            {exporting ? "发送中..." : "发送涂鸦"}
          </button>
          {error ? <div className="px-2 text-center text-[12px] font-medium text-rose-500">{error}</div> : null}
        </div>
      </div>
    </div>
  );
}
