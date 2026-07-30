import type { User } from "@/types/user";

export interface LoginRequest {
  username: string;
  password: string;
  company_id?: string;
  branch_id?: string;
}

export interface TokenResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
  expires_in: number;
  user: User;
}

export interface MeResponse {
  user: User;
  company_id: string;
  branch_id: string | null;
  permissions: string[];
}
