import { SecureStorage } from '@aparajita/capacitor-secure-storage';
import { nativeProduct } from './config';
import { useAuthStore } from '@/stores/auth.store';

export function nativeScope() {
  const s = useAuthStore.getState();
  return [s.companyId, s.brandId, s.branchId, s.user?.id, s.businessType].join(':');
}
export const cartKey = (scope: string) => `foodchainservice.${nativeProduct}.uat.cart.${scope}`;
let writes = Promise.resolve();
export function writeNativeCart(scope: string, value: unknown) {
  writes = writes.then(() => SecureStorage.setItem(cartKey(scope), JSON.stringify(value))).then(() => undefined);
  return writes.catch(error => { window.dispatchEvent(new Event('native-pos-storage-error')); throw error; });
}
export async function readNativeCart(scope: string) {
  await writes;
  const value = await SecureStorage.getItem(cartKey(scope));
  return typeof value === 'string' ? JSON.parse(value) : null;
}
export async function clearNativeCart(scope: string) {
  writes = writes.then(() => SecureStorage.removeItem(cartKey(scope))).then(() => undefined);
  await writes;
  window.dispatchEvent(new CustomEvent('native-pos-cart-settled', { detail: scope }));
}
