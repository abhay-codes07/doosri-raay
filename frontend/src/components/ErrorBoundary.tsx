import { Component, type ErrorInfo, type ReactNode } from 'react';
import { S } from '../i18n/strings';

interface Props {
  children: ReactNode;
  /** When this changes (e.g. the route path) a previous error is cleared. */
  resetKey?: string;
}

interface State {
  error: Error | null;
}

/**
 * Calm bilingual crash screen. Wraps every route so a rendering error in one page can never leave
 * the whole app blank. Hindi first, one big button: reload.
 */
export class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    console.error('Route crashed', error, info.componentStack);
  }

  componentDidUpdate(prev: Props): void {
    if (prev.resetKey !== this.props.resetKey && this.state.error) this.setState({ error: null });
  }

  render(): ReactNode {
    if (!this.state.error) return this.props.children;
    return (
      <div className="page page-narrow parent-mode crash" role="alert">
        <section className="card tone-amber" style={{ textAlign: 'center' }}>
          <p style={{ fontSize: '3em', margin: '8px 0' }} aria-hidden="true">
            🙏
          </p>
          <h1 lang="hi" style={{ fontSize: '1.6em', margin: '8px 0' }}>
            {S.crashTitle.hi}
          </h1>
          <p lang="en" className="muted" style={{ margin: '0 0 8px' }}>
            {S.crashTitle.en}
          </p>
          <p lang="hi">{S.crashBody.hi}</p>
          <button type="button" className="btn btn-primary btn-big btn-block" onClick={() => window.location.reload()}>
            <span className="bi">
              <span className="bi-hi" lang="hi">
                {S.reload.hi}
              </span>
              <span className="bi-en" lang="en">
                {S.reload.en}
              </span>
            </span>
          </button>
        </section>
      </div>
    );
  }
}
