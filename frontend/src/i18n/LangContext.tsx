import { createContext, useCallback, useContext, useMemo, type ReactNode } from 'react';
import { S, interpolate, type Lang, type StringKey } from './strings';

interface LangCtx {
  lang: Lang;
  setLang: (l: Lang) => void;
}

const LangContext = createContext<LangCtx>({ lang: 'hi', setLang: () => undefined });

export function LangProvider({ lang, setLang, children }: LangCtx & { children: ReactNode }) {
  const value = useMemo(() => ({ lang, setLang }), [lang, setLang]);
  return <LangContext.Provider value={value}>{children}</LangContext.Provider>;
}

export function useLang(): LangCtx {
  return useContext(LangContext);
}

/** t(key) in the current language; tb(key) returns both. */
export function useT() {
  const { lang } = useLang();
  const tt = useCallback(
    (key: StringKey, vars?: Record<string, string | number>) => interpolate(S[key][lang], vars),
    [lang],
  );
  const tb = useCallback(
    (key: StringKey, vars?: Record<string, string | number>) => ({
      hi: interpolate(S[key].hi, vars),
      en: interpolate(S[key].en, vars),
    }),
    [],
  );
  return { t: tt, tb, lang };
}

/** Hindi first, English secondary — the parent-screen text pattern. */
export function Bi({
  k,
  vars,
  as: Tag = 'span',
  className = '',
}: {
  k: StringKey;
  vars?: Record<string, string | number>;
  as?: 'span' | 'p' | 'h1' | 'h2' | 'h3' | 'div';
  className?: string;
}) {
  const hi = interpolate(S[k].hi, vars);
  const en = interpolate(S[k].en, vars);
  return (
    <Tag className={`bi ${className}`.trim()}>
      <span className="bi-hi" lang="hi">
        {hi}
      </span>
      {en !== hi && (
        <span className="bi-en" lang="en">
          {en}
        </span>
      )}
    </Tag>
  );
}
