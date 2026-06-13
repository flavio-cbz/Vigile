import { useEffect } from 'react';

const BASE_TITLE = 'Vigile';

export function usePageTitle(pageTitle?: string) {
  useEffect(() => {
    document.title = pageTitle ? `${pageTitle} — ${BASE_TITLE}` : BASE_TITLE;
  }, [pageTitle]);
}
