export interface User {
  uid: string
  email: string | null
}

export interface AuthPort {
  subscribe(listener: (user: User | null) => void): () => void
  signIn(): Promise<void>
  signOut(): Promise<void>
  token(): Promise<string>
}

export interface Citation {
  passage_id: string
  claim: string
  label: string
  url: string
}

export interface AskResponse {
  conversation_id: string
  message_id: string
  answer: string
  citations: Citation[]
  assumptions: string[]
  confidence: "high" | "medium" | "low"
  needs_clarification: boolean
  quota_remaining: number
  cache_status: "exact" | "semantic" | "miss" | "ineligible"
}

export interface ConversationSummary {
  id: string
  title: string
  updated_at: string
}

export interface ConversationMessage {
  id: string
  role: "user" | "assistant"
  content: string
  created_at: string
  citations: Citation[]
}

export interface ConversationDetail {
  id: string
  title: string
  messages: ConversationMessage[]
}

export interface ApiPort {
  ask(question: string, conversationId: string | undefined, requestId: string): Promise<AskResponse>
  publicAsk(question: string): Promise<AskResponse>
  conversations(): Promise<ConversationSummary[]>
  conversation(id: string): Promise<ConversationDetail>
  deleteConversation(id: string): Promise<void>
  feedback(messageId: string, rating: -1 | 1, comment?: string): Promise<void>
  deleteAccount(): Promise<void>
}

export interface InstallPort {
  available: boolean
  install(): Promise<boolean>
}
