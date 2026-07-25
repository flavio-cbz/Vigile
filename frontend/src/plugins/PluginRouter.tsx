import React, { Suspense, useEffect, useState } from 'react';
import { Route, Routes, useNavigate, useParams } from 'react-router';
import { usePluginStore } from '../store/pluginStore';
import { useAuthStore } from '../store/authStore';
import { RestrictedPluginAPI } from './PluginAPI';
import type { PluginPageEntry } from '../types/plugins';

type PluginComponentProps = {
  api: RestrictedPluginAPI;
  routeParams: Record<string, string | undefined>;
};

// Static registry of compiled first-party plugin components (Option A)
const PLUGIN_COMPONENTS: Record<string, Record<string, React.ComponentType<PluginComponentProps>>> = {
  docker: {
    DockerContainers: React.lazy(() => import('./docker/pages/DockerContainers')),
    DockerContainerDetail: React.lazy(() => import('./docker/pages/DockerContainerDetail')),
  },
  systemd: {
    SystemdServices: React.lazy(() => import('./systemd/pages/SystemdServices')),
  },
  metrics: {
    MetricsHistory: React.lazy(() => import('./metrics/pages/MetricsHistory')),
  },
  plex: {
    PlexAdmin: React.lazy(() => import('./plex/pages/PlexAdmin')),
  },
};

interface PluginWrapperProps {
  page: PluginPageEntry;
}

const PluginWrapper: React.FC<PluginWrapperProps> = ({ page }) => {
  const navigate = useNavigate();
  const params = useParams();
  const [apiInstance, setApiInstance] = useState<RestrictedPluginAPI | null>(null);

  // Instanciate the restricted API with plugin configuration and context
  useEffect(() => {
    // In a future sprint, plugin config could be fetched or read from a state
    const api = new RestrictedPluginAPI(
      page.plugin_id,
      page.title,
      {}, // Pass empty config for now, will be populated if needed
      navigate
    );
    setApiInstance(api);
  }, [page, navigate]);

  const pluginGroup = PLUGIN_COMPONENTS[page.plugin_id];
  const Component = pluginGroup ? pluginGroup[page.component] : null;

  if (!Component) {
    return (
      <div className="flex flex-col items-center justify-center h-[50vh] text-center p-6 bg-zinc-900/40 rounded-xl border border-zinc-800">
        <h3 className="text-xl font-bold text-zinc-300 mb-2">Composant non compilé</h3>
        <p className="text-zinc-500 max-w-md">
          Le composant <code>{page.component}</code> du plugin <code>{page.plugin_id}</code> n'est pas disponible dans cette version du frontend.
        </p>
      </div>
    );
  }

  if (!apiInstance) {
    return (
      <div className="flex items-center justify-center h-[50vh]">
        <div className="animate-spin rounded-full h-8 w-8 border-t-2 border-orange-500 border-zinc-800"></div>
      </div>
    );
  }

  return (
    <Suspense
      fallback={
        <div className="flex items-center justify-center h-[50vh]">
          <div className="animate-spin rounded-full h-8 w-8 border-t-2 border-orange-500 border-zinc-800"></div>
        </div>
      }
    >
      <Component api={apiInstance} routeParams={params} />
    </Suspense>
  );
};

export const PluginRouter: React.FC = () => {
  const { pages, fetchPluginPages, loading } = usePluginStore();
  const { user } = useAuthStore();
  const userRole = user?.role || 'viewer';

  // Load active plugin pages on mount
  useEffect(() => {
    fetchPluginPages();
  }, []);

  const allowedPages = React.useMemo(() => {
    const roleIndex = { viewer: 0, operator: 1, admin: 2 } as Record<string, number>;
    const userLevel = roleIndex[userRole] ?? 0;
    return pages.filter((page) => {
      const pageRoles = page.roles || ['viewer'];
      const pageLevel = Math.min(...pageRoles.map((r) => roleIndex[r] ?? 0));
      return userLevel >= pageLevel;
    });
  }, [pages, userRole]);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-screen">
        <div className="animate-spin rounded-full h-12 w-12 border-t-2 border-orange-500 border-zinc-800"></div>
      </div>
    );
  }

  return (
    <Routes>
      {allowedPages.map((page) => {
        // Map dynamic React-Router route pattern
        // Example: /plugins/docker/containers/:containerId
        const relativePath = page.route.replace('/plugins/', '');
        return (
          <Route
            key={`${page.plugin_id}-${page.id}`}
            path={relativePath}
            element={<PluginWrapper page={page} />}
          />
        );
      })}
    </Routes>
  );
};
