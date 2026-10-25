import { Capacitor, registerPlugin } from '@capacitor/core';

const documents = registerPlugin<{
  shareCsv(options: { filename: string; content: string }): Promise<{ opened: boolean }>;
}>('NativeDocumentPrinter');

export async function saveCsv(filename: string, csv: string): Promise<'share-opened' | 'download'> {
  const content = '\uFEFF' + csv;
  if (Capacitor.isNativePlatform()) {
    const result = await documents.shareCsv({ filename, content });
    if (!result.opened) throw new Error('Unable to open Android share menu');
    return 'share-opened';
  }
  const url = URL.createObjectURL(new Blob([content], { type: 'text/csv;charset=utf-8' }));
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  try { link.click(); } finally {
    link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 60_000);
  }
  return 'download';
}
