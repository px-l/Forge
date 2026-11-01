/** getRandomValues is available on HTTP; randomUUID requires a secure context. */
export function createPreviewToken(source: Pick<Crypto, 'getRandomValues'> = globalThis.crypto): string {
  if (!source?.getRandomValues) throw new Error('当前浏览器不支持安全随机数，请升级浏览器后重试。');
  const bytes = source.getRandomValues(new Uint8Array(32));
  return Array.from(bytes, byte => byte.toString(16).padStart(2, '0')).join('');
}

export async function copyText(text: string): Promise<boolean> {
  try {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(text);
      return true;
    }
  } catch { /* HTTP or clipboard permission restrictions: use the legacy path. */ }
  const previous = document.activeElement as HTMLElement | null;
  const selection = document.getSelection();
  const ranges = selection ? Array.from({length:selection.rangeCount},(_,i)=>selection.getRangeAt(i).cloneRange()) : [];
  const input = document.createElement('textarea');
  input.value = text;
  input.setAttribute('readonly', '');
  input.style.cssText = 'position:fixed;left:-9999px;top:0;opacity:0;';
  document.body.append(input);
  try {
    input.focus(); input.select();
    return document.execCommand('copy');
  } catch { return false; }
  finally {
    input.remove(); previous?.focus();
    if(selection){selection.removeAllRanges();for(const range of ranges)selection.addRange(range);}
  }
}
