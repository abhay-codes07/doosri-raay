import { createContext, useContext, useMemo, type ReactNode } from 'react';
import type { Circle, CircleMember, Profile } from './api/types';
import { useProfile } from './hooks/useProfile';

export interface Session {
  sub: string;
  email?: string;
  profile: Profile | null;
  circle: Circle | null;
  parent: CircleMember | null;
  guardians: CircleMember[];
  hasCircle: boolean;
  isParent: boolean;
  loading: boolean;
  error: string | null;
  reload: () => Promise<void>;
  signOut: () => void;
}

const SessionContext = createContext<Session | null>(null);

export function SessionProvider({
  sub,
  email,
  signOut,
  children,
}: {
  sub: string;
  email?: string;
  signOut: () => void;
  children: ReactNode;
}) {
  const { data, loading, error, reload } = useProfile(true);
  const value = useMemo<Session>(() => {
    const profile = data?.profile ?? null;
    const circle = data?.circle ?? null;
    const members = circle?.members ?? [];
    const parent = members.find((m) => m.role === 'parent') ?? null;
    const guardians = members.filter((m) => m.role === 'guardian1' || m.role === 'guardian2');
    const hasCircle = Boolean(profile?.circleId ?? circle?.circleId);
    return {
      sub,
      email,
      profile,
      circle,
      parent,
      guardians,
      hasCircle,
      isParent: profile?.role === 'parent',
      loading,
      error,
      reload,
      signOut,
    };
  }, [data, loading, error, reload, sub, email, signOut]);
  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>;
}

export function useSession(): Session {
  const s = useContext(SessionContext);
  if (!s) throw new Error('useSession outside SessionProvider');
  return s;
}
