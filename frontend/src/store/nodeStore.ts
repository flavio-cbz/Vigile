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
}

interface NodeState {
  nodes: Node[];
  selectedNodeId: string | null;
  selectedNode: Node | null;
  isLoading: boolean;
  error: string | null;
  setNodes: (nodes: Node[]) => void;
  selectNode: (nodeId: string | null) => void;
  fetchNodes: () => Promise<void>;
}

export const useNodeStore = create<NodeState>((set, get) => ({
  nodes: [],
  selectedNodeId: 'all',
  selectedNode: null,
  isLoading: false,
  error: null,
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
    } catch (err: any) {
      set({ error: err.message, isLoading: false });
    }
  }
}));
