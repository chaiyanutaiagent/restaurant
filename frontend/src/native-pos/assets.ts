// Root-relative uploads resolve against the API host, never Android's localhost.
export function nativeAssetUrls(value: unknown): any {
  if (Array.isArray(value)) return value.map(nativeAssetUrls);
  if (!value || typeof value !== 'object') return value;
  if (Object.getPrototypeOf(value) !== Object.prototype) return value; // Keep Blob/ArrayBuffer exports intact.
  return Object.fromEntries(Object.entries(value).map(([key, child]) => [key,
    typeof child === 'string' && /^(image_url|logo_url|receipt_logo_url|promptpay_qr_url|qr_image_url|photo_url)$/.test(key) && child.startsWith('/') && !child.startsWith('//')
      ? `${import.meta.env.VITE_API_BASE_URL}${child}` : nativeAssetUrls(child)]));
}
