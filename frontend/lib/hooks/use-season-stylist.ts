'use client';

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useSession } from 'next-auth/react';
import { api } from '@/lib/api';
import { applySessionToken, useSetTokenIfAvailable } from '@/lib/hooks/use-session-token';
import { queryKeys } from '@/lib/hooks/query-keys';
import type { WishlistEntry } from '@/lib/hooks/use-wishlist';
import type { Item } from '@/lib/types';

export interface SwapEntry {
  item: Item;
  reason: 'season' | 'last_year';
}

export interface SeasonSwap {
  current_season: string;
  upcoming_season: string;
  put_away: SwapEntry[];
  bring_out: SwapEntry[];
  stays: number;
}

export interface StylistTurn {
  role: 'user' | 'assistant';
  content: string;
}

export interface StylistReply {
  reply: string;
  items: Item[];
}

export function useSeasonSwap() {
  const { status } = useSession();
  useSetTokenIfAvailable();
  return useQuery({
    queryKey: queryKeys.seasonSwap,
    queryFn: () => api.get<SeasonSwap>('/season-swap'),
    enabled: status === 'authenticated',
  });
}

export function useStylist() {
  const { data: session } = useSession();
  return useMutation({
    mutationFn: async (messages: StylistTurn[]) => {
      applySessionToken(session);
      return api.post<StylistReply>('/stylist', { messages });
    },
  });
}

export function useCheckPrices() {
  const queryClient = useQueryClient();
  const { data: session } = useSession();
  return useMutation({
    mutationFn: async () => {
      applySessionToken(session);
      return api.post<WishlistEntry[]>('/wishlist/check-prices');
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: queryKeys.wishlist }),
  });
}
