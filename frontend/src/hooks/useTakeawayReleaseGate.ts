import { useQuery } from "@tanstack/react-query";
import { takeawayApi } from "@/lib/takeawayApi";

export function useTakeawayReleaseGate() {
  const query = useQuery({
    queryKey: ["takeaway", "status"],
    queryFn: async () => (await takeawayApi.status()).data.data,
    staleTime: 30_000,
  });
  return {
    ...query,
    writesEnabled: Boolean(query.data?.enabled && query.data.writes_enabled),
  };
}
