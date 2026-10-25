export type PosRelease = {
  channel: 'uat'; package_id: string; version_code: number; version_name: string;
  apk_url: string; apk_sha256: string; published_at: string; signature: string;
};
// Public verification key only. Private signing key stays outside the repository.
const publicKey = `MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEArTt35w1dFjDGComfIODo
iH2isyuNJkkJoSiiFWMSZpn+igk4e6RsRt00kygb3g5HltidxdDMYyy0rPiPyVFa
MglvCuiYoItTsJrmcRtWs61SuRJ37951iB8K/pQqYAWi6az2wDlp1sLMok4taGj3
zsAlR6VTke2Vp3FV8PouSxl5/xW4viZxOn0lXfZ20MuPlGdOLm+n85NV1e0yQs+H
5NOSA2tX+zThjTWja881KrP3006/EzLaCF33HeD1dpYsQ94ae2Hhh6XFt/SmmB7L
n05kHQ9nFQ0vcuxbOV6lfmHMbLF7z12d3ZmJIwPUHNO/wZ17mdMGF9qeOgLKQ0Jo
oQIDAQAB`;
export function releasePayload(m: PosRelease): string {
  return JSON.stringify({apk_sha256:m.apk_sha256, apk_url:m.apk_url, channel:m.channel, package_id:m.package_id,
    published_at:m.published_at, version_code:m.version_code, version_name:m.version_name});
}
function bytes(value:string): ArrayBuffer { return Uint8Array.from(atob(value.replace(/\s/g,'')), c=>c.charCodeAt(0)).buffer as ArrayBuffer; }
export async function verifyPosRelease(value: unknown, product: string): Promise<PosRelease> {
  const m=value as PosRelease;
  if (!['retail','restaurant'].includes(product) || !m || m.channel!=='uat'
      || m.package_id!==`com.foodchainservice.${product}.uat` || !Number.isSafeInteger(m.version_code) || m.version_code<1
      || typeof m.version_name!=='string' || !/^\d+\.\d+\.\d+-uat\.\d+$/.test(m.version_name)
      || !/^[a-f0-9]{64}$/.test(m.apk_sha256) || !Number.isFinite(Date.parse(m.published_at))) throw Error('ข้อมูลอัปเดตไม่ตรงกับแอป');
  const host=product==='retail'?'uat-retail':'uat-pos';
  if(m.apk_url!==`https://${host}.foodchainservice.com/downloads/native-pos-${m.version_name}/foodchainservice-${product}-${m.version_name}.apk`) throw Error('ลิงก์อัปเดตไม่ได้รับอนุญาต');
  const key=await crypto.subtle.importKey('spki',bytes(publicKey),{name:'RSASSA-PKCS1-v1_5',hash:'SHA-256'},false,['verify']);
  if (!await crypto.subtle.verify('RSASSA-PKCS1-v1_5',key,bytes(m.signature),new TextEncoder().encode(releasePayload(m)))) throw Error('ลายเซ็นข้อมูลอัปเดตไม่ถูกต้อง');
  return m;
}
