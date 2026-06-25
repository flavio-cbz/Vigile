import { create } from 'zustand';
import { api } from '../hooks/useApi';

export interface Node {
  id: string;
  name: string;
  hostname: string | null;
  machine_id: string | null;
  arch: string | null;
  os: string | null;
  state: string;
  online: boolean;
  last_heartbeat: number | null;
  enrolled_at: number | null;
  created_at: number;
  updated_at: number;
  group: string | null;
  disabled: boolean;
  enrolled_recently: boolean;
}

export interface NodeStateChangeEvent {
  node_id: string;
  from_state: string | null;
  new_state: string;
  ts: number;
}

export interface NodeDeletedEvent {
  node_id: string;
  previous_state: string | null;
  ts: number;
}

export interface PendingConfiguration {
  id: string;
  hostname: string | null;
  name: string;
  group: string;
}

interface NodeState {
  nodes: Node[];
  selectedNodeId: string | null;
  selectedNode: Node | null;
  isLoading: boolean;
  error: string | null;
  pendingConfiguration: PendingConfiguration | null;
  setNodes: (nodes: Node[]) => void;
  selectNode: (nodeId: string | null) => void;
  fetchNodes: () => Promise<void>;
  applyEvent: (event: NodeStateChangeEvent) => void;
  applyDeletedEvent: (event: NodeDeletedEvent) => void;
  openServerConfig: (node: Node) => void;
  closeServerConfig: () => void;
  configureNode: (nodeId: string, name: string, group: string) => Promise<void>;
  renameNode: (id: string, name: string) => Promise<void>;
  setNodeGroup: (id: string, group: string) => Promise<void>;
  setNodeDisabled: (id: string, disabled: boolean) => Promise<void>;
  deleteNode: (id: string) => Promise<void>;
  regenerateToken: (id: string) => Promise<{ node_id: string; token: string; curl_command: string; expires_in: number }>;
}

export const useNodeStore = create<NodeState>((set, get) => ({
  nodes: [],
  selectedNodeId: 'all',
  selectedNode: null,
  isLoading: false,
  error: null,
  pendingConfiguration: null,
  setNodes: (nodes) => {
    const selectedId = get().selectedNodeId;
    let finalSelectedId: string;
    let finalSelectedNode: Node | null;

    if (nodes.length === 1) {
      finalSelectedId = nodes[0].id;
      finalSelectedNode = nodes[0];
    } else if (selectedId === 'all') {
      finalSelectedId = 'all';
      finalSelectedNode = null;
    } else {
      const found = nodes.find(n => n.id === selectedId);
      if (found) {
        finalSelectedNode = found;
        finalSelectedId = found.id;
      } else {
        finalSelectedId = 'all';
        finalSelectedNode = null;
      }
    }

    set({
      nodes,
      selectedNode: finalSelectedNode,
      selectedNodeId: finalSelectedId
    });
  },
  selectNode: (nodeId) => {
    const { nodes } = get();
    if (nodeId === 'all' || !nodeId) {
      set({ selectedNodeId: 'all', selectedNode: null });
    } else {
      const selected = nodes.find(n => n.id === nodeId) || null;
      set({ selectedNodeId: selected ? selected.id : 'all', selectedNode: selected });
    }
  },
  fetchNodes: async () => {
    set({ isLoading: true, error: null });
    try {
      const data = await api<Node[]>('/api/nodes');
      if (!data) return;

      const nodes: Node[] = data;
      const currentSelectedId = get().selectedNodeId;
      let newSelectedNode = null;
      let newSelectedId = 'all';

      if (nodes.length === 1) {
        newSelectedId = nodes[0].id;
        newSelectedNode = nodes[0];
      } else if (currentSelectedId !== 'all' && currentSelectedId) {
        const found = nodes.find(n => n.id === currentSelectedId);
        if (found) {
          newSelectedNode = found;
          newSelectedId = found.id;
        }
      }

      set({
        nodes,
        selectedNode: newSelectedNode,
        selectedNodeId: newSelectedId,
        isLoading: false
      });
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Erreur inconnue';
      set({ error: message, isLoading: false });
    }
  },
  applyEvent: (event) => {
    set((state) => {
      if (event.new_state === 'REVOKED') {
        return {
          nodes: state.nodes.filter((n) => n.id !== event.node_id),
        };
      }
      return {
        nodes: state.nodes.map((n) =>
          n.id === event.node_id ? { ...n, state: event.new_state } : n
        ),
      };
    });
  },
  applyDeletedEvent: (event) => {
    set((state) => {
      const remaining = state.nodes.filter((n) => n.id !== event.node_id);
      let newSelectedId = state.selectedNodeId;
      let newSelectedNode = state.selectedNode;
      if (state.selectedNodeId === event.node_id) {
        if (remaining.length === 1) {
          newSelectedId = remaining[0].id;
          newSelectedNode = remaining[0];
        } else {
          newSelectedId = 'all';
          newSelectedNode = null;
        }
      }
      return { nodes: remaining, selectedNodeId: newSelectedId, selectedNode: newSelectedNode };
    });
  },
  openServerConfig: (node) => {
    set({
      pendingConfiguration: {
        id: node.id,
        hostname: node.hostname,
        name: node.name,
        group: node.group ?? '',
      },
    });
  },
  closeServerConfig: () => {
    set({ pendingConfiguration: null });
  },
  configureNode: async (nodeId, name, group) => {
    const data = await api<Node>(`/api/nodes/${nodeId}/configure`, {
      method: 'POST',
      body: JSON.stringify({ name, group: group.trim() === '' ? null : group }),
    });
    if (!data) return;
    set((state) => ({
      nodes: state.nodes.map((n) => (n.id === nodeId ? { ...n, ...data } : n)),
      pendingConfiguration: null,
    }));
  },
  renameNode: async (id, name) => {
    await api(`/api/nodes/${id}`, {
      method: 'PATCH',
      body: JSON.stringify({ name }),
    });
    set((state) => ({
      nodes: state.nodes.map((n) => (n.id === id ? { ...n, name } : n)),
    }));
  },
  setNodeGroup: async (id, group) => {
    await api(`/api/nodes/${id}`, {
      method: 'PATCH',
      body: JSON.stringify({ group: group.trim() === '' ? null : group }),
    });
    set((state) => ({
      nodes: state.nodes.map((n) => (n.id === id ? { ...n, group } : n)),
    }));
  },
  setNodeDisabled: async (id, disabled) => {
    await api(`/api/nodes/${id}`, {
      method: 'PATCH',
      body: JSON.stringify({ disabled }),
    });
    set((state) => ({
      nodes: state.nodes.map((n) => (n.id === id ? { ...n, disabled } : n)),
    }));
  },
  deleteNode: async (id) => {
    await api(`/api/nodes/${id}`, { method: 'DELETE' });
    set((state) => ({
      nodes: state.nodes.filter((n) => n.id !== id),
    }));
  },
  regenerateToken: async (id) => {
    const data = await api<{ node_id: string; token: string; curl_command: string; expires_in: number }>(
      `/api/nodes/${id}/regenerate-token`,
      { method: 'POST' }
    );
    if (!data) throw new Error('Échec de la régénération du jeton');
    return data;
  },
}));
