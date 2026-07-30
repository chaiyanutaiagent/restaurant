/// <reference lib="webworker" />

declare const self: ServiceWorkerGlobalScope;

self.addEventListener("message", (event: ExtendableMessageEvent) => {
  if (event.data && event.data.type === "SKIP_WAITING") {
    void self.skipWaiting();
  }
});

export {};
