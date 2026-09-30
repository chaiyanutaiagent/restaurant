export function validReleaseChannel(packageId: string, channel: string): boolean;
export function validReleaseUrl(value: string, channel: string, extension?: string): boolean;
export function validReleaseManifest(value: unknown, requireSignature?: boolean): boolean;
export function canonicalReleasePayload(manifest: object): string;
