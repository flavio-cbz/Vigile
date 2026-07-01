import { useNodeStore, type Node as BaseNode } from './nodeStore';
import { api } from '../hooks/useApi';

export interface NodeWithMeta extends BaseNode {
  group: string | null;
  disabled: boolean;
  enrolled_recently: boolean;
}

export interface RegenerateTokenResult {
  node_id: string;
  token: string;
  curl_command: string;
  expires_in: number;
}

interface NodeStateWithActions {
  nodes: BaseNode[];
  renameNode?: (id: string, name: string) => Promise<void>;
  setNodeGroup?: (id: string, group: string) => Promise<void>;
  setNodeDisabled?: (id: string, disabled: boolean) => Promise<void>;
  deleteNode?: (id: string) => Promise<void>;
  regenerateToken?: (id: string) => Promise<RegenerateTokenResult>;
  updateWorker?: (id: string) => Promise<void>;
}

function patchNodes(updater: (nodes: BaseNode[]) => BaseNode[]) {
  const state = useNodeStore.getState();
  const next = updater(state.nodes);
  state.setNodes(next);
}

function asNode(n: BaseNode): NodeWithMeta {
  const extra = n as NodeWithMeta;
  if (typeof extra.disabled !== 'boolean') extra.disabled = false;
  if (typeof extra.enrolled_recently !== 'boolean') extra.enrolled_recently = false;
  if (extra.group === undefined) extra.group = null;
  return extra;
}

function tryStoreAction<T>(name: keyof NodeStateWithActions, args: unknown[], fallback: () => Promise<T>): Promise<T> {
  const state = useNodeStore.getState() as unknown as NodeStateWithActions;
  const fn = state[name];
  if (typeof fn === 'function') {
    return (fn as unknown as (...a: unknown[]) => Promise<T>).apply(state, args) as unknown as Promise<T>;
  }
  return fallback();
}

async function renameNode(id: string, name: string): Promise<void> {
  await tryStoreAction<void>('renameNode', [id, name], async () => {
    await api(`/api/nodes/${id}`, {
      method: 'PATCH',
      body: JSON.stringify({ name }),
    });
    patchNodes((nodes) => nodes.map((n) => (n.id === id ? { ...n, name } : n)));
  });
}

async function setNodeGroup(id: string, group: string): Promise<void> {
  await tryStoreAction<void>('setNodeGroup', [id, group], async () => {
    await api(`/api/nodes/${id}`, {
      method: 'PATCH',
      body: JSON.stringify({ group: group.trim() === '' ? null : group }),
    });
    patchNodes((nodes) => nodes.map((n) => (n.id === id ? asNode({ ...n, group }) : n)));
  });
}

async function setNodeDisabled(id: string, disabled: boolean): Promise<void> {
  await tryStoreAction<void>('setNodeDisabled', [id, disabled], async () => {
    await api(`/api/nodes/${id}`, {
      method: 'PATCH',
      body: JSON.stringify({ disabled }),
    });
    patchNodes((nodes) => nodes.map((n) => (n.id === id ? asNode({ ...n, disabled }) : n)));
  });
}

async function deleteNode(id: string): Promise<void> {
  await tryStoreAction<void>('deleteNode', [id], async () => {
    try {
      await api(`/api/nodes/${id}`, { method: 'DELETE' });
    } catch (err) {
      // 404 means another tab/operator already deleted the node — treat as success
      // (idempotent). Surface other errors normally.
      const msg = err instanceof Error ? err.message.toLowerCase() : String(err).toLowerCase();
      if (!msg.includes('not found') && !msg.includes('404')) {
        throw err;
      }
    }
    patchNodes((nodes) => nodes.filter((n) => n.id !== id));
  });
}

async function regenerateToken(id: string): Promise<RegenerateTokenResult> {
  const fallback = async () => {
    const data = await api<RegenerateTokenResult>(`/api/nodes/${id}/regenerate-token`, {
      method: 'POST',
    });
    if (!data) throw new Error('Échec de la régénération du jeton');
    return data;
  };
  return tryStoreAction<RegenerateTokenResult>('regenerateToken', [id], fallback);
}

async function updateWorker(id: string): Promise<void> {
  const fallback = async () => {
    await api(`/api/nodes/${id}/update`, {
      method: 'POST',
    });
  };
  return tryStoreAction<void>('updateWorker', [id], fallback);
}

export const nodeMutations = {
  renameNode,
  setNodeGroup,
  setNodeDisabled,
  deleteNode,
  regenerateToken,
  updateWorker,
  asNode,
};
