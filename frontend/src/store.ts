import { create } from 'zustand'

export interface Agent {
  id: string
  name: string
  role: string
  status: string
  position: { x: number; y: number }
  thoughts: string
  task_count: number
  performance: {
    tasks_completed: number
    tasks_failed: number
    avg_task_time: number
    total_messages: number
  }
  office_id?: string
  office_name?: string
  office_type?: string
  worker_count?: number
  specialization?: string
}

export interface Office {
  id: string
  name: string
  type: string
  manager_id: string
  worker_ids: string[]
  file_count: number
}

export interface CompanyState {
  agents: Record<string, Agent>
  offices: Record<string, Office>
  agent_count: number
  max_agents: number
  running: boolean
}

export interface WalkEvent {
  agent_id: string
  target_id: string
  from_pos: { x: number; y: number }
  to_pos: { x: number; y: number }
}

export interface CommunicateEvent {
  source: string
  target: string
  message: string
}

interface AppState {
  // Connection
  connected: boolean
  ws: WebSocket | null
  token: string | null

  // Company state
  companyState: CompanyState | null

  // UI State
  showOnboarding: boolean
  showAgentModal: boolean
  selectedAgentId: string | null
  selectedAgent: Agent | null
  agentChatLog: Array<{ timestamp: string; from?: string; to?: string; message: string; response?: string }>
  agentTaskQueue: Array<{ type: string; description: string }>
  githubInviteUrl: string | null

  // Actions
  setConnected: (v: boolean) => void
  setWs: (ws: WebSocket | null) => void
  setToken: (t: string | null) => void
  setCompanyState: (s: CompanyState) => void
  setShowOnboarding: (v: boolean) => void
  setShowAgentModal: (v: boolean) => void
  setSelectedAgent: (id: string | null) => void
  setSelectedAgentData: (a: Agent | null) => void
  setAgentChatLog: (log: Array<any>) => void
  setAgentTaskQueue: (q: Array<any>) => void
  setGithubInviteUrl: (url: string | null) => void
}

export const useStore = create<AppState>((set) => ({
  connected: false,
  ws: null,
  token: null,
  companyState: null,
  showOnboarding: true,
  showAgentModal: false,
  selectedAgentId: null,
  selectedAgent: null,
  agentChatLog: [],
  agentTaskQueue: [],
  githubInviteUrl: null,

  setConnected: (v) => set({ connected: v }),
  setWs: (ws) => set({ ws }),
  setToken: (t) => set({ token: t }),
  setCompanyState: (s) => set({ companyState: s }),
  setShowOnboarding: (v) => set({ showOnboarding: v }),
  setShowAgentModal: (v) => set({ showAgentModal: v }),
  setSelectedAgent: (id) => set({ selectedAgentId: id }),
  setSelectedAgentData: (a) => set({ selectedAgent: a }),
  setAgentChatLog: (log) => set({ agentChatLog: log }),
  setAgentTaskQueue: (q) => set({ agentTaskQueue: q }),
  setGithubInviteUrl: (url) => set({ githubInviteUrl: url }),
}))
