export type SupplyChainReleaseCheckState = "pass" | "pending" | "hold";

export type SupplyChainReleaseCheck = {
  key: string;
  label: string;
  state: SupplyChainReleaseCheckState;
  detail: string;
};

export type SupplyChainRelease = {
  release_stage: "read_only" | "uat_canary";
  writes_enabled: boolean;
  generated_at: string;
  stale_after_seconds: number;
  hard_holds: string[];
  checks: SupplyChainReleaseCheck[];
};
