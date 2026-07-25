import type { Message } from '../../store/chatStore';

/**
 * Group a flat message history into turns.
 *
 * Each user message starts a new turn. System/tool messages that appear BEFORE
 * the first user message are placed in a leading "preamble" turn so they remain
 * visible (e.g. contextual hints or tool bootstrap messages).
 */
export const groupByTurns = (history: Message[]): Message[][] => {
  if (!history.length) return [];
  const turns: Message[][] = [];
  let current: Message[] = [];

  for (const msg of history) {
    if (msg.role === 'user') {
      if (current.length) turns.push(current);
      current = [msg];
    } else {
      current.push(msg);
    }
  }
  if (current.length) turns.push(current);
  return turns;
};
