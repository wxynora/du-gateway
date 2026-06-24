export type AvatarCropRect = {
  sx: number;
  sy: number;
  size: number;
};

export async function fileToDataUrl(file: File): Promise<string> {
  return await new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result || ""));
    reader.onerror = () => reject(new Error("图片读取失败"));
    reader.readAsDataURL(file);
  });
}

export async function buildAnthropicImageDataUrlFromDataUrl(src: string): Promise<string> {
  const img = await loadImageElement(src);
  const maxLongEdge = 1568;
  const maxPixels = 1_150_000;
  const width = Math.max(1, img.naturalWidth || img.width || 1);
  const height = Math.max(1, img.naturalHeight || img.height || 1);
  const scale = Math.min(
    1,
    maxLongEdge / Math.max(width, height),
    Math.sqrt(maxPixels / Math.max(1, width * height)),
  );
  const outWidth = Math.max(1, Math.floor(width * scale));
  const outHeight = Math.max(1, Math.floor(height * scale));
  const canvas = document.createElement("canvas");
  canvas.width = outWidth;
  canvas.height = outHeight;
  const ctx = canvas.getContext("2d");
  if (!ctx) throw new Error("图片处理失败");
  ctx.fillStyle = "#fff";
  ctx.fillRect(0, 0, outWidth, outHeight);
  ctx.drawImage(img, 0, 0, outWidth, outHeight);
  return canvas.toDataURL("image/jpeg", 0.86);
}

export async function buildAnthropicImageDataUrl(file: File): Promise<string> {
  return buildAnthropicImageDataUrlFromDataUrl(await fileToDataUrl(file));
}

export async function loadImageElement(src: string): Promise<HTMLImageElement> {
  return await new Promise((resolve, reject) => {
    const img = new Image();
    img.onload = () => resolve(img);
    img.onerror = () => reject(new Error("图片加载失败"));
    img.src = src;
  });
}

export async function buildAvatarDataUrl(file: File): Promise<string> {
  const src = await fileToDataUrl(file);
  const img = await loadImageElement(src);
  const minSide = Math.min(img.width, img.height);
  return buildAvatarDataUrlFromCrop(src, {
    sx: (img.width - minSide) / 2,
    sy: (img.height - minSide) / 2,
    size: minSide,
  });
}

export async function buildAvatarDataUrlFromCrop(src: string, crop: AvatarCropRect): Promise<string> {
  const img = await loadImageElement(src);
  const size = 256;
  const canvas = document.createElement("canvas");
  canvas.width = size;
  canvas.height = size;
  const ctx = canvas.getContext("2d");
  if (!ctx) throw new Error("图片处理失败");
  const maxSize = Math.min(img.width, img.height);
  const cropSize = Math.max(1, Math.min(Number(crop.size) || maxSize, maxSize));
  const sx = Math.max(0, Math.min(Number(crop.sx) || 0, img.width - cropSize));
  const sy = Math.max(0, Math.min(Number(crop.sy) || 0, img.height - cropSize));
  ctx.drawImage(img, sx, sy, cropSize, cropSize, 0, 0, size, size);
  return canvas.toDataURL("image/jpeg", 0.9);
}

export async function buildBackgroundDataUrl(file: File): Promise<string> {
  const src = await fileToDataUrl(file);
  const img = await loadImageElement(src);
  const maxWidth = 1280;
  const scale = Math.min(1, maxWidth / img.width);
  const width = Math.max(1, Math.round(img.width * scale));
  const height = Math.max(1, Math.round(img.height * scale));
  const canvas = document.createElement("canvas");
  canvas.width = width;
  canvas.height = height;
  const ctx = canvas.getContext("2d");
  if (!ctx) throw new Error("图片处理失败");
  ctx.drawImage(img, 0, 0, width, height);
  return canvas.toDataURL("image/jpeg", 0.82);
}
