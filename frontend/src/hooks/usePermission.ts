import { useAuthStore } from '../store/authStore';

type PermissionAction = 'add-server' | 'configure-llm' | 'view-audit' | 'view-plugins' | 'view-settings' | 'approve-action' | 'manage-users';

export function usePermission() {
  const user = useAuthStore((s) => s.user);
  const isGuest = user?.username === 'guest';
  const isAdmin = user?.role === 'admin' && !isGuest;
  const isOperator = user?.role === 'operator' && !isGuest;

  // Demo mode: guest with admin/operator role can approve actions
  const isDemoAdmin = isGuest && (user?.role === 'admin' || user?.role === 'operator');

  const can = (action: PermissionAction): boolean => {
    switch (action) {
    case 'add-server':
    case 'configure-llm':
    case 'manage-users':
      return isAdmin;
    case 'approve-action':
      // In demo mode, guest with admin/operator role can approve
      return isAdmin || isOperator || isDemoAdmin;
    case 'view-audit':
    case 'view-plugins':
    case 'view-settings':
      return isAdmin || isOperator || isDemoAdmin;
    default:
      return false;
    }
  };

  return { isAdmin, isOperator, isGuest, isDemoAdmin, can };
}
