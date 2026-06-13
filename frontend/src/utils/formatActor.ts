/**
 * Maps a demo user ID or raw UUID to a friendly display name.
 * In demo mode, "demo-user" maps to "guest".
 * Other UUIDs are truncated to first 8 chars.
 */
export function formatActorName(userId: string | null | undefined): string {
  if (!userId) return 'système';
  if (userId === 'demo-user') return 'guest';
  if (userId.includes('-') && userId.length > 12) {
    return userId.substring(0, 8) + '…';
  }
  return userId;
}
