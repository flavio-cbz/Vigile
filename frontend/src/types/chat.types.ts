export interface ToolResult {
  success: boolean;
  data: any;
  error?: string | null;
}

export interface ToolCall {
  id: string;
  name: string;
  arguments: Record<string, any>;
  status: 'pending' | 'executing' | 'completed' | 'failed';
  result?: ToolResult;
}

export interface ProposalData {
  id: string;
  action: string;
  risk_level: string;
  reasoning?: string;
  target?: string;
  status: 'PENDING' | 'APPROVED' | 'REJECTED' | 'EXECUTED' | 'FAILED';
  params?: Record<string, any>;
  result?: Record<string, any>;
}

export interface Message {
  role: 'system' | 'user' | 'assistant' | 'tool';
  content: string | null;
  tool_calls?: ToolCall[];
  tool_call_id?: string;
  name?: string;
  proposal?: ProposalData;
}

export interface ChatSession {
  id: string;
  user_id: string;
  node_id: string | null;
  title: string;
  history: Message[];
  created_at: number;
  updated_at: number;
}

export interface Proposal {
  id: string;
  node_id: string;
  action: string;
  params: Record<string, any>;
  reasoning: string;
  risk_level: string;
  status: 'PENDING' | 'APPROVED' | 'REJECTED' | 'EXECUTED' | 'FAILED';
  created_by: string;
  created_at: number;
}
