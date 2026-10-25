// Serialize drawer pulses and receipts on one Bluetooth transport. Never retry.
export function createPrinterQueue() {
  let tail: Promise<unknown> = Promise.resolve();
  return function enqueue<T>(send: () => Promise<T>): Promise<T> {
    const job = tail.then(send);
    tail = job.catch(() => undefined);
    return job;
  };
}
