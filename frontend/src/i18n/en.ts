export const en = {
  // Navigation
  "nav.dashboard": "Dashboard",
  "nav.chat": "AI Chat",
  "nav.proposals": "Proposals",
  "nav.servers": "Servers",
  "nav.admin": "ADMINISTRATION",
  "nav.plugins": "Plugins",
  "nav.audit": "Audit",
  "nav.settings": "Settings",
  "nav.profile": "Profile",

  // Login
  "login.title": "Sign in to Vigile",
  "login.subtitle": "Secure Autonomous Fleet Management",
  "login.username": "Username",
  "login.password": "Password",
  "login.btn": "Sign In",
  "login.error": "Invalid credentials",
  "login.success_password_change": "Password updated successfully!",

  // Dashboard General
  "dash.all_operational": "All systems operational",
  "dash.servers_online": "{online}/{total} servers online",
  "dash.servers_offline_banner": "{count} server(s) offline: {names}",
  "dash.last_updated": "Last updated {time}s ago",
  "dash.stale_warning": "Stale data (last update >60s ago)",
  "dash.view_all": "View all",
  "dash.empty_state": "No data available",

  // Swimlanes
  "swim.servers": "Servers",
  "swim.containers": "Containers",
  "swim.insights": "AI Insights",
  "swim.activity": "Recent Activity",
  "swim.trends": "Uptime & Trends",

  // Cards
  "card.cpu": "CPU",
  "card.ram": "RAM",
  "card.disk": "Disk",
  "card.uptime": "Uptime",
  "card.restart": "Restart",
  "card.restarting": "Restarting...",
  "btn.refresh": "Refresh",
  "card.status.running": "Running",
  "card.status.stopped": "Stopped",
  "card.status.restarting": "Restarting",
  "card.analyze_ai": "Analyze with AI →",

  // Proposals
  "prop.title": "Action Proposals",
  "prop.risk": "Risk Level",
  "prop.reasoning": "Reasoning",
  "prop.action": "Action",
  "prop.status.pending": "Pending",
  "prop.status.approved": "Approved",
  "prop.status.rejected": "Rejected",
  "prop.status.executed": "Executed",
  "prop.status.failed": "Failed",
  "prop.btn.approve": "Approve",
  "prop.btn.reject": "Reject",
  "prop.reject_reason_title": "Rejection Reason",
  "prop.reject_reason_placeholder": "Explain why you reject this proposal...",

  // Audit
  "audit.title": "Immutable Audit Log",
  "audit.subtitle": "Secure SHA256 chain log integrity",
  "audit.user": "User",
  "audit.action": "Action",
  "audit.node": "Server",
  "audit.timestamp": "Timestamp",
  "audit.hash": "Signature chain hash",
  "audit.verified": "Audit chain validated cryptographically",

  // Settings
  "settings.title": "Vigile Settings",
  "settings.language": "Interface Language",
  "settings.lang_fr": "Français",
  "settings.lang_en": "English",
  "settings.theme": "Visual Theme",
  "settings.save": "Save Changes",

  // Plugins
  "plugins.title": "Plugins Directory",
  "plugins.status.active": "Active",
  "plugins.status.stale": "Stale",
  "plugins.status.inactive": "Inactive",
  "plugins.confirm_uninstall": "Are you sure you want to uninstall this plugin?",

  // Add Server Modal
  "add_node.title": "Add a server",
  "add_node.name_label": "Server Name",
  "add_node.name_placeholder": "e.g. media-server",
  "add_node.generate_token": "Generate Token",
  "add_node.waiting": "⏳ Waiting for Worker connection...",
  "add_node.token_created": "Enrollment token generated. Execute this command on your server:",
  "add_node.success": "Server successfully connected!",

  // Error States
  "error.network": "Network error communicating with the API.",
  "error.retry": "Retry",
  "error.load_data": "Unable to load data.",

  // Chat
  "chat.welcome": "Hello! I am Vigile Copilot. I can help you monitor your server and run secure commands. Ask me anything!",
  "chat.welcome_multi": "Hello! I am Vigile Copilot in fullscreen mode. I can help you monitor your servers and run secure commands. Select an associated server or ask a global question.",
  "chat.loading": "Loading conversation...",
  "chat.placeholder": "Ask a question, request a metrics report, or execute a command...",
  "chat.shift_enter": "Shift+Enter for new line",
  "chat.associate": "Associate with:",
  "chat.all_servers": "All Servers (Global)",
  "chat.title_edit": "Edit title",
  "chat.title_new": "New conversation",
  "chat.user": "You",
  "chat.copilot": "Vigile Copilot",
  "chat.proposal_title": "Action Proposal",
  "chat.risk_level": "Risk: {level}",
  "chat.btn.approve": "Approve & Execute",
  "chat.btn.reject": "Reject",
  "chat.btn.approved": "Approved",
  "chat.btn.rejected": "Rejected",
  "chat.copy": "Copy",
  "chat.copied": "Copied!",
  "chat.error_communication": "Sorry, an error occurred while communicating with the assistant.",
};
