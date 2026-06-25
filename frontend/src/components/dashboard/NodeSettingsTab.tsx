import { useState } from 'react';
import { useNavigate } from 'react-router';
import { RefreshCw, Check, X, Trash2, Power, KeyRound, AlertTriangle, Copy } from 'lucide-react';
import { type Node } from '../../store/nodeStore';
import { nodeMutations, type NodeWithMeta, type RegenerateTokenResult } from '../../store/nodeMutations';
import { useAuthStore } from '../../store/authStore';
import { useToastStore } from '../../store/useToastStore';
import { useLocale } from '../../i18n';
import { ConfirmDeleteModal } from '../modals/ConfirmDeleteModal';

type SaveState = 'idle' | 'saving' | 'ok' | 'error';

interface NodeSettingsTabProps {
  node: Node;
}

function castNode(node: Node): NodeWithMeta {
  const ext = node as NodeWithMeta;
  if (typeof ext.disabled !== 'boolean') ext.disabled = false;
  if (typeof ext.enrolled_recently !== 'boolean') ext.enrolled_recently = false;
  if (ext.group === undefined) ext.group = null;
  return ext;
}

export const NodeSettingsTab = ({ node }: NodeSettingsTabProps) => {
  const { t } = useLocale();
  const navigate = useNavigate();
  const role = useAuthStore((s) => s.user?.role);
  const isAdmin = role === 'admin';
  const addToast = useToastStore((s) => s.addToast);

  const n = castNode(node);
  const isPending = n.state === 'PENDING';

  const [name, setName] = useState(n.name || '');
  const [group, setGroup] = useState(n.group || '');
  const [nameState, setNameState] = useState<SaveState>('idle');
  const [groupState, setGroupState] = useState<SaveState>('idle');

  const [toggling, setToggling] = useState(false);

  const [regen, setRegen] = useState<RegenerateTokenResult | null>(null);
  const [regenLoading, setRegenLoading] = useState(false);
  const [copiedKey, setCopiedKey] = useState<string | null>(null);

  const [confirmDelete, setConfirmDelete] = useState(false);

  const handleCopy = (text: string, key: string) => {
    navigator.clipboard.writeText(text);
    setCopiedKey(key);
    window.setTimeout(() => setCopiedKey(null), 2000);
  };

  const saveField = async (
    stateSetter: (s: SaveState) => void,
    mutator: () => Promise<void>,
    successMsg: string,
  ) => {
    stateSetter('saving');
    try {
      await mutator();
      stateSetter('ok');
      addToast('success', t('settings.saved'), successMsg);
      window.setTimeout(() => stateSetter('idle'), 1500);
    } catch (err) {
      stateSetter('error');
      const msg = err instanceof Error ? err.message : String(err);
      addToast('error', t('settings.error'), msg);
    }
  };

  const handleNameBlur = () => {
    const trimmed = name.trim();
    if (trimmed === '' || trimmed === (n.name || '')) {
      setName(n.name || '');
      return;
    }
    void saveField(setNameState, async () => {
      await nodeMutations.renameNode(n.id, trimmed);
      n.name = trimmed;
    }, trimmed);
  };

  const handleGroupBlur = () => {
    const next = group.trim();
    const current = n.group || '';
    if (next === current) return;
    void saveField(setGroupState, async () => {
      await nodeMutations.setNodeGroup(n.id, next);
      n.group = next === '' ? null : next;
    }, next || '—');
  };

  const handleToggleDisabled = async () => {
    setToggling(true);
    try {
      const next = !n.disabled;
      await nodeMutations.setNodeDisabled(n.id, next);
      n.disabled = next;
      addToast(
        'success',
        next ? t('servers.toast.disabled') : t('servers.toast.enabled'),
        n.hostname || n.name,
      );
    } catch (err) {
      addToast('error', t('settings.error'), err instanceof Error ? err.message : String(err));
    } finally {
      setToggling(false);
    }
  };

  const handleRegenerate = async () => {
    setRegenLoading(true);
    setRegen(null);
    try {
      const data = await nodeMutations.regenerateToken(n.id);
      setRegen(data);
      addToast('success', t('settings.regenerate'), t('settings.regenerate.copied'));
    } catch (err) {
      addToast('error', t('settings.error'), err instanceof Error ? err.message : String(err));
    } finally {
      setRegenLoading(false);
    }
  };

  const handleRevoke = async () => {
    await nodeMutations.deleteNode(n.id);
    addToast('success', t('servers.toast.deleted'), n.hostname || n.name);
    navigate('/nodes');
  };

  const renderFieldStatus = (state: SaveState) => {
    if (state === 'saving') return <RefreshCw className="w-3.5 h-3.5 text-text-3 animate-spin" />;
    if (state === 'ok') return <Check className="w-3.5 h-3.5 text-severity-ok" />;
    if (state === 'error') return <X className="w-3.5 h-3.5 text-red-500" />;
    return null;
  };

  return (
    <div className="space-y-6">
      <div className="p-5 border border-border rounded-xl bg-surface space-y-4 shadow">
        <h3 className="text-xs font-interface font-bold uppercase tracking-widest text-text-1 border-b border-border pb-2">
          {t('settings.general')}
        </h3>

        <div className="space-y-1">
          <label className="block text-[0.5625rem] font-bold text-ink-secondary uppercase tracking-wider">
            {t('settings.field.name')}
          </label>
          <div className="flex items-center gap-2">
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              onBlur={handleNameBlur}
              className="input flex-1"
            />
            <span className="shrink-0 w-5 flex justify-center">{renderFieldStatus(nameState)}</span>
          </div>
        </div>

        <div className="space-y-1">
          <label className="block text-[0.5625rem] font-bold text-ink-secondary uppercase tracking-wider">
            {t('settings.field.group')}
          </label>
          <div className="flex items-center gap-2">
            <input
              type="text"
              value={group}
              onChange={(e) => setGroup(e.target.value)}
              onBlur={handleGroupBlur}
              placeholder="—"
              className="input flex-1"
            />
            <span className="shrink-0 w-5 flex justify-center">{renderFieldStatus(groupState)}</span>
          </div>
        </div>
      </div>

      {isPending && (
        <div className="p-5 border border-border rounded-xl bg-surface space-y-4 shadow">
          <h3 className="text-xs font-interface font-bold uppercase tracking-widest text-text-1 border-b border-border pb-2 flex items-center gap-2">
            <KeyRound className="w-3.5 h-3.5" />
            {t('settings.token_section')}
          </h3>

          <button
            type="button"
            onClick={handleRegenerate}
            disabled={regenLoading}
            className="btn btn-secondary py-2 text-[0.625rem]"
          >
            {regenLoading ? (
              <RefreshCw className="w-3.5 h-3.5 animate-spin" />
            ) : (
              <>
                <RefreshCw className="w-3.5 h-3.5" />
                <span>{t('settings.regenerate')}</span>
              </>
            )}
          </button>

          {regen && (
            <div className="space-y-3 animate-fade-in">
              <div className="space-y-1">
                <div className="flex justify-between items-center">
                  <span className="text-[0.5rem] font-bold text-text-2 uppercase tracking-wider">{t('settings.token_label')}</span>
                  <button
                    onClick={() => handleCopy(regen.token, 'token')}
                    className="text-ink-secondary hover:text-accent-primary flex items-center gap-0.5 text-[0.625rem] font-bold cursor-pointer"
                  >
                    {copiedKey === 'token' ? <Check className="w-3 h-3 text-success" /> : <Copy className="w-3 h-3" />}
                    <span>{copiedKey === 'token' ? t('settings.regenerate.copied') : t('settings.copy_button')}</span>
                  </button>
                </div>
                <div className="p-2 rounded-lg bg-surface-1 border border-border font-mono text-[0.5625rem] text-ink-primary break-all select-all">
                  {regen.token}
                </div>
              </div>

              <div className="space-y-1">
                <div className="flex justify-between items-center">
                  <span className="text-[0.5rem] font-bold text-text-2 uppercase tracking-wider">{t('settings.command_label')}</span>
                  <button
                    onClick={() => handleCopy(regen.curl_command, 'curl')}
                    className="text-ink-secondary hover:text-accent-primary flex items-center gap-0.5 text-[0.625rem] font-bold cursor-pointer"
                  >
                    {copiedKey === 'curl' ? <Check className="w-3 h-3 text-success" /> : <Copy className="w-3 h-3" />}
                    <span>{copiedKey === 'curl' ? t('settings.regenerate.copied') : t('settings.copy_button')}</span>
                  </button>
                </div>
                <div className="p-2 rounded-lg bg-surface-1 border border-border font-mono text-[0.5625rem] text-ink-primary whitespace-pre-wrap break-all select-all">
                  {regen.curl_command}
                </div>
              </div>
            </div>
          )}
        </div>
      )}

      {isAdmin && (
        <div className="p-5 border border-red-500/20 rounded-xl bg-red-500/5 space-y-4 shadow">
          <h3 className="text-xs font-interface font-bold uppercase tracking-widest text-red-500 border-b border-red-500/20 pb-2 flex items-center gap-2">
            <AlertTriangle className="w-3.5 h-3.5" />
            {t('settings.danger_zone')}
          </h3>

          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              onClick={handleToggleDisabled}
              disabled={toggling}
              className="btn btn-secondary py-2 text-[0.625rem]"
            >
              {toggling ? (
                <RefreshCw className="w-3.5 h-3.5 animate-spin" />
              ) : (
                <>
                  <Power className="w-3.5 h-3.5" />
                  <span>{n.disabled ? t('settings.enable') : t('settings.disable')}</span>
                </>
              )}
            </button>

            <button
              type="button"
              onClick={() => setConfirmDelete(true)}
              className="btn btn-danger py-2 text-[0.625rem]"
            >
              <Trash2 className="w-3.5 h-3.5" />
              <span>{t('settings.revoke')}</span>
            </button>
          </div>
        </div>
      )}

      {confirmDelete && (
        <ConfirmDeleteModal
          title={t('settings.confirm.revoke_title')}
          message={t('settings.confirm.revoke_message')}
          confirmWord={n.hostname || n.name}
          confirmLabel={t('settings.confirm.revoke_action')}
          onClose={() => setConfirmDelete(false)}
          onConfirm={handleRevoke}
        />
      )}
    </div>
  );
};
