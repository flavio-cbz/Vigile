import { Component, type ReactNode, type ErrorInfo } from 'react';
import { t } from '../../i18n';
import { AlertTriangle, RefreshCw } from 'lucide-react';

interface Props {
  children: ReactNode;
  fallback?: ReactNode;
  onRetry?: () => void;
}

interface State {
  hasError: boolean;
  error: Error | null;
}

export class ErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error('[ErrorBoundary]', error, info.componentStack);
  }

  handleRetry = () => {
    this.setState({ hasError: false, error: null });
    this.props.onRetry?.();
  };

  render() {
    if (this.state.hasError) {
      if (this.props.fallback) return this.props.fallback;

      return (
        <div className="card border-danger/20 p-6 flex flex-col items-center text-center gap-3">
          <AlertTriangle className="w-8 h-8 text-danger" />
          <div>
            <p className="text-sm font-semibold text-ink-primary">
              {t('error_boundary.title')}
            </p>
            <p className="text-xs text-ink-secondary mt-1">
              {this.state.error?.message ||
                t('error_boundary.description')}
            </p>
          </div>
          {this.props.onRetry && (
            <button
              onClick={this.handleRetry}
              className="btn btn-secondary text-xs py-1 px-3"
            >
              <RefreshCw className="w-3.5 h-3.5" />
              {t('error_boundary.retry')}
            </button>
          )}
        </div>
      );
    }

    return this.props.children;
  }
}
