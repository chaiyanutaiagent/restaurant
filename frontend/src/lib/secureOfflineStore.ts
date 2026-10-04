import { db, type EncryptedOfflineData } from "@/lib/db";

const KEY_ID = "restaurant-offline-aes-gcm-v1";
const encoder = new TextEncoder();
const decoder = new TextDecoder();

function toBase64(bytes: Uint8Array): string {
  let binary = "";
  for (const byte of bytes) binary += String.fromCharCode(byte);
  return btoa(binary);
}

function fromBase64(value: string): ArrayBuffer {
  const binary = atob(value);
  const bytes = new Uint8Array(binary.length);
  for (let index = 0; index < binary.length; index += 1) bytes[index] = binary.charCodeAt(index);
  return bytes.buffer;
}

async function encryptionKey(): Promise<CryptoKey> {
  const stored = await db.offlineKeys.get(KEY_ID);
  if (stored?.crypto_key) return stored.crypto_key;
  const cryptoKey = await crypto.subtle.generateKey(
    { name: "AES-GCM", length: 256 },
    false,
    ["encrypt", "decrypt"],
  );
  await db.offlineKeys.put({ key: KEY_ID, crypto_key: cryptoKey, created_at: Date.now() });
  return cryptoKey;
}

export async function encryptOfflineValue(value: unknown, associatedId: string): Promise<EncryptedOfflineData> {
  const iv = crypto.getRandomValues(new Uint8Array(12));
  const ciphertext = await crypto.subtle.encrypt(
    { name: "AES-GCM", iv, additionalData: encoder.encode(associatedId), tagLength: 128 },
    await encryptionKey(),
    encoder.encode(JSON.stringify(value)),
  );
  return {
    version: 1,
    iv: toBase64(iv),
    ciphertext: toBase64(new Uint8Array(ciphertext)),
  };
}

export async function decryptOfflineValue<T>(
  encrypted: EncryptedOfflineData,
  associatedId: string,
): Promise<T> {
  if (encrypted.version !== 1) throw new Error("unsupported_encryption_version");
  const plaintext = await crypto.subtle.decrypt(
    {
      name: "AES-GCM",
      iv: fromBase64(encrypted.iv),
      additionalData: encoder.encode(associatedId),
      tagLength: 128,
    },
    await encryptionKey(),
    fromBase64(encrypted.ciphertext),
  );
  return JSON.parse(decoder.decode(plaintext)) as T;
}

export async function clearOfflineEncryptionKeyWhenSafe(): Promise<void> {
  const active = await db.restaurantPendingOrders
    .filter((row) => row.status !== "reconciled" && row.status !== "rejected")
    .count();
  if (active === 0) {
    await db.transaction(
      "rw",
      db.restaurantPendingOrders,
      db.restaurantMenuSnapshots,
      db.offlineKeys,
      async () => {
        await db.restaurantPendingOrders.clear();
        await db.restaurantMenuSnapshots.clear();
        await db.offlineKeys.delete(KEY_ID);
      },
    );
  }
}
