import { useEffect, useId, useState } from 'react';
import { useSources } from '../hooks/useSources';
import { normalizeUrl, sourceAnchor } from '../lib/sources';
import { useT } from '../i18n/LangContext';
import { formatTimeIST } from '../lib/dates';
import { formatBytes } from '../lib/validate';

/**
 * "Documents you can prove": every rule the case cards cite was fetched by the backend, hashed
 * and checked for the exact quotes the rules rely on. Collapsible; opens itself when the page is
 * navigated to one of its #src-… anchors.
 */
export function SourcesPanel({ defaultOpen = false }: { defaultOpen?: boolean }) {
  const { t, lang } = useT();
  const uid = useId();
  const { data, error, loading } = useSources();
  const [open, setOpen] = useState(defaultOpen);

  useEffect(() => {
    const onHash = () => {
      if (window.location.hash.startsWith('#src-')) setOpen(true);
    };
    onHash();
    window.addEventListener('hashchange', onHash);
    return () => window.removeEventListener('hashchange', onHash);
  }, []);

  // Scroll to the anchor once the panel has rendered its entries.
  useEffect(() => {
    if (!open || !data) return;
    const id = window.location.hash.slice(1);
    if (!id.startsWith('src-')) return;
    const el = document.getElementById(id);
    if (el) el.scrollIntoView({ block: 'start', behavior: 'smooth' });
  }, [open, data]);

  const sources = data?.sources ?? [];
  const okCount = sources.filter((s) => s.fetched && s.quotes.every((q) => q.found)).length;

  return (
    <section className="card sources" aria-labelledby={`${uid}-title`}>
      <button
        type="button"
        className="row spread sources-toggle"
        aria-expanded={open}
        aria-controls={`${uid}-body`}
        onClick={() => setOpen((v) => !v)}
      >
        <span>
          <h2 id={`${uid}-title`} style={{ fontSize: '1.15em', margin: 0 }}>
            {t('sourcesTitle')}
          </h2>
          <span className="small muted">{t('sourcesSub')}</span>
        </span>
        <span className="row">
          {data && (
            <span className={`badge ${okCount === sources.length && sources.length > 0 ? 'badge-ok' : 'badge-amber'}`}>
              {okCount}/{sources.length}
            </span>
          )}
          <span aria-hidden="true">{open ? '▴' : '▾'}</span>
        </span>
      </button>

      <div id={`${uid}-body`} hidden={!open}>
        {loading && !data && <p className="muted small">{t('loading')}</p>}
        {error && !data && <p className="muted small">{t('sourcesUnavailable')}</p>}
        {data && (
          <>
            {data.verifiedAt && (
              <p className="small muted" style={{ margin: '8px 0' }}>
                {t('sourcesVerifiedAt')}: {formatTimeIST(data.verifiedAt, lang)}
                {data.summary ? ` · ${data.summary}` : ''}
              </p>
            )}
            {sources.length === 0 && <p className="muted small">{t('sourcesNone')}</p>}
            <ul className="list-plain sources-list">
              {sources.map((src) => {
                const allFound = src.fetched && src.quotes.every((q) => q.found);
                const host = normalizeUrl(src.url).split('/')[0];
                return (
                  <li key={src.url} id={sourceAnchor(src)} className={`source ${allFound ? 'source-ok' : 'source-warn'}`}>
                    <div className="row spread">
                      <a href={src.url} target="_blank" rel="noreferrer" className="source-url">
                        {host}
                        <span className="muted small">{src.url.replace(/^https?:\/\/[^/]+/i, '')}</span>
                      </a>
                      <span className={`badge ${src.fetched ? 'badge-ok' : 'badge-red'}`}>{src.fetched ? t('sourceFetched') : t('sourceNotFetched')}</span>
                    </div>
                    <p className="small muted mono" style={{ margin: '4px 0' }}>
                      SHA-256 {src.sha256 ? src.sha256.slice(0, 16) : '—'}
                      {typeof src.bytes === 'number' ? ` · ${formatBytes(src.bytes)}` : ''}
                      {src.contentType ? ` · ${src.contentType}` : ''}
                      {src.fetchedAt ? ` · ${formatTimeIST(src.fetchedAt, lang)}` : ''}
                    </p>
                    {src.quotes.length > 0 && (
                      <ul className="list-plain small">
                        {src.quotes.map((q, i) => (
                          <li key={`${i}-${q.quote.slice(0, 20)}`} className={q.found ? 'quote-ok' : 'quote-missing'}>
                            <span aria-hidden="true">{q.found ? '✓' : '✗'}</span> <span className="sr-only">{q.found ? t('quoteFound') : t('quoteNotFound')}:</span>{' '}
                            <q>{q.quote}</q>
                          </li>
                        ))}
                      </ul>
                    )}
                  </li>
                );
              })}
            </ul>
          </>
        )}
      </div>
    </section>
  );
}
