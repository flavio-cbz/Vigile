/**
 * Vigile — Copilot Chat via SSE
 *
 * Handles the EventSource connection for the copilot panel.
 * Messages are streamed from POST /chat/stream (frontend route).
 */

let copilotAbortController = null;
let copilotStreaming = false;

/**
 * Send a message to the copilot and stream the response.
 */
async function sendCopilotMessage(event) {
  event.preventDefault();

  const input = document.getElementById('copilot-input');
  const messages = document.getElementById('copilot-messages');
  const text = input.value.trim();
  if (!text || copilotStreaming) return;

  input.value = '';
  input.disabled = true;
  copilotStreaming = true;

  // Add user message
  appendCopilotMessage('user', text, null);

  // Add AI placeholder
  const aiMsgDiv = document.createElement('div');
  aiMsgDiv.className = 'copilot-msg text-sm px-3 py-2 rounded-lg';
  aiMsgDiv.style.background = 'rgba(45, 212, 191, 0.08)';
  aiMsgDiv.innerHTML = [
    '<div class="flex items-center gap-2 mb-1">',
    '  <i class="ti ti-robot text-xs" style="color: var(--accent);"></i>',
    '  <span class="text-xs font-medium" style="color: var(--accent);">Vigile</span>',
    '</div>',
    '<div class="typing-indicator flex gap-1 py-1">',
    '  <span class="typing-dot w-1.5 h-1.5 rounded-full" style="background: var(--ink-muted);"></span>',
    '  <span class="typing-dot w-1.5 h-1.5 rounded-full" style="background: var(--ink-muted);"></span>',
    '  <span class="typing-dot w-1.5 h-1.5 rounded-full" style="background: var(--ink-muted);"></span>',
    '</div>',
  ].join('');
  aiMsgDiv.id = 'copilot-ai-msg';
  messages.appendChild(aiMsgDiv);
  messages.scrollTop = messages.scrollHeight;

  // Get node_id from URL if on a node page
  const pathParts = window.location.pathname.split('/');
  const nodeId = pathParts[1] === 'nodes' && pathParts[2] ? pathParts[2] : null;

  // Determine if there's an active copilot context (previous proposals)
  const proposalButtons = document.querySelectorAll('[data-proposal-id]');
  const history = [];

  try {
    copilotAbortController = new AbortController();

    const resp = await fetch('/chat/stream', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        message: text,
        node_id: nodeId,
        history: history,
      }),
      signal: copilotAbortController.signal,
    });

    if (!resp.ok) {
      throw new Error('Server returned ' + resp.status);
    }

    const reader = resp.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    let fullText = '';
    let proposalReceived = null;

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n');
      buffer = lines.pop() || '';

      for (const line of lines) {
        if (!line.startsWith('data: ')) continue;
        const data = line.slice(6).trim();
        if (!data) continue;

        try {
          const event = JSON.parse(data);

          if (event.type === 'token') {
            fullText += event.content;
            updateCopilotText(aiMsgDiv, fullText);
          } else if (event.type === 'proposal') {
            proposalReceived = event;
          } else if (event.type === 'error') {
            updateCopilotText(aiMsgDiv, 'Error: ' + (event.detail || 'Unknown error'));
          }
          // 'done' type — handled by stream ending
        } catch (e) {
          // skip malformed JSON
        }
      }
    }

    // If we got a proposal, show action buttons
    if (proposalReceived) {
      appendProposalButtons(messages, proposalReceived);
    }

    // If no tokens streamed but no error, show a fallback
    if (!fullText && !proposalReceived) {
      updateCopilotText(aiMsgDiv, 'No response — the LLM may not be configured.');
    }
  } catch (err) {
    if (err.name !== 'AbortError') {
      updateCopilotText(aiMsgDiv, 'Connection error: ' + err.message);
    }
  } finally {
    input.disabled = false;
    input.focus();
    copilotStreaming = false;
    copilotAbortController = null;
    messages.scrollTop = messages.scrollHeight;
  }

  return false;
}

/**
 * Append a message bubble to the copilot panel.
 */
function appendCopilotMessage(role, text, meta) {
  const messages = document.getElementById('copilot-messages');
  const div = document.createElement('div');
  div.className = 'copilot-msg text-sm px-3 py-2 rounded-lg';

  if (role === 'user') {
    div.style.background = 'rgba(255, 255, 255, 0.04)';
    div.style.marginLeft = '24px';
    div.innerHTML = [
      '<div class="flex items-center gap-2 mb-1">',
      '  <i class="ti ti-user text-xs" style="color: var(--ink-dim);"></i>',
      '  <span class="text-xs font-medium" style="color: var(--ink-dim);">You</span>',
      '</div>',
      '<p style="color: var(--ink);">' + escapeHtml(text) + '</p>',
    ].join('');
  } else {
    div.style.background = 'rgba(45, 212, 191, 0.08)';
    div.innerHTML = [
      '<div class="flex items-center gap-2 mb-1">',
      '  <i class="ti ti-robot text-xs" style="color: var(--accent);"></i>',
      '  <span class="text-xs font-medium" style="color: var(--accent);">Vigile</span>',
      '</div>',
      '<p style="color: var(--ink);">' + escapeHtml(text) + '</p>',
    ].join('');
  }

  messages.appendChild(div);
  messages.scrollTop = messages.scrollHeight;
}

/**
 * Update the AI message text in-place (for streaming).
 */
function updateCopilotText(div, text) {
  const inner = div.querySelector('p') || div;
  if (inner.tagName === 'DIV') {
    // First update — replace typing indicator
    div.innerHTML = [
      '<div class="flex items-center gap-2 mb-1">',
      '  <i class="ti ti-robot text-xs" style="color: var(--accent);"></i>',
      '  <span class="text-xs font-medium" style="color: var(--accent);">Vigile</span>',
      '</div>',
      '<p style="color: var(--ink);"></p>',
    ].join('');
  }
  const p = div.querySelector('p');
  if (p) {
    // Render markdown-ish: bold, code, newlines
    const rendered = escapeHtml(text)
      .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
      .replace(/`(.+?)`/g, '<code style="background: rgba(255,255,255,0.06); padding: 1px 4px; border-radius: 3px; font-size: 11px;">$1</code>')
      .replace(/\n/g, '<br>');
    p.innerHTML = rendered;
  }
}

/**
 * Append proposal approve/reject buttons.
 */
function appendProposalButtons(container, proposal) {
  const div = document.createElement('div');
  div.className = 'copilot-msg text-sm px-3 py-2 rounded-lg mt-2';
  div.style.background = 'rgba(245, 158, 11, 0.1)';
  div.style.border = '1px solid rgba(245, 158, 11, 0.2)';
  div.innerHTML = [
    '<div class="flex items-center gap-2 mb-2">',
    '  <i class="ti ti-alert-triangle text-xs" style="color: #f59e0b;"></i>',
    '  <span class="text-xs font-medium" style="color: #f59e0b;">Proposal: ' + escapeHtml(proposal.action) + '</span>',
    '  <span class="ml-auto text-[10px] px-1.5 py-0.5 rounded font-medium uppercase" style="background: rgba(245,158,11,0.15); color: #f59e0b;">' + escapeHtml(proposal.risk_level) + '</span>',
    '</div>',
    '<p class="text-xs mb-2" style="color: var(--ink-dim);">' + escapeHtml(proposal.reasoning || '') + '</p>',
    '<div class="flex gap-2">',
    '  <button class="px-2.5 py-1 rounded text-xs font-medium transition" style="background: rgba(45,212,191,0.15); color: #2dd4bf; border: 1px solid rgba(45,212,191,0.2);" onclick="approveProposal(\'' + proposal.proposal_id + '\')">',
    '    <i class="ti ti-circle-check"></i> Approve',
    '  </button>',
    '  <button class="px-2.5 py-1 rounded text-xs font-medium transition" style="background: rgba(239,68,68,0.1); color: #ef4444; border: 1px solid rgba(239,68,68,0.2);" onclick="rejectProposal(\'' + proposal.proposal_id + '\')">',
    '    <i class="ti ti-circle-x"></i> Reject',
    '  </button>',
    '</div>',
  ].join('');
  container.appendChild(div);
  container.scrollTop = container.scrollHeight;
}

/**
 * Escape HTML special characters.
 */
function escapeHtml(str) {
  if (!str) return '';
  const div = document.createElement('div');
  div.textContent = str;
  return div.innerHTML;
}

/**
 * Read the JWT from the non-httpOnly auth_token cookie for Bearer auth.
 */
function getBearerToken() {
  const match = document.cookie.match(/(?:^|;\s*)auth_token=([^;]*)/);
  return match ? match[1] : null;
}

/**
 * Approve a proposal via API.
 */
async function approveProposal(id) {
  try {
    const token = getBearerToken();
    const headers = {'Content-Type': 'application/json'};
    if (token) headers['Authorization'] = 'Bearer ' + token;
    const resp = await fetch('/api/chat/proposals/' + id + '/approve', {
      method: 'POST', headers: headers
    });
    if (resp.ok) {
      appendCopilotMessage('system', 'Proposal approved and executed.', null);
    } else {
      const data = await resp.json();
      appendCopilotMessage('system', 'Failed: ' + (data.detail || resp.status), null);
    }
  } catch(e) {
    appendCopilotMessage('system', 'Error: ' + e.message, null);
  }
}

/**
 * Reject a proposal via API.
 */
async function rejectProposal(id) {
  const reason = prompt('Rejection reason (optional):');
  try {
    const token = getBearerToken();
    const headers = {'Content-Type': 'application/json'};
    if (token) headers['Authorization'] = 'Bearer ' + token;
    const resp = await fetch('/api/chat/proposals/' + id + '/reject', {
      method: 'POST', headers: headers,
      body: JSON.stringify({reason: reason || ''})
    });
    if (resp.ok) {
      appendCopilotMessage('system', 'Proposal rejected.', null);
    } else {
      appendCopilotMessage('system', 'Failed: ' + resp.status, null);
    }
  } catch(e) {
    appendCopilotMessage('system', 'Error: ' + e.message, null);
  }
}
