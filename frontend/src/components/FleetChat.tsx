import { useState, useRef, useEffect } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { BarChart, Bar, LineChart, Line, PieChart, Pie, Cell, ResponsiveContainer, XAxis, YAxis, Tooltip } from 'recharts'
import {
  Activity,
  AlertTriangle,
  Bot,
  Brain,
  Gauge,
  Route,
  Send,
  Settings,
  ShieldCheck,
  Sparkles,
  Truck,
  User
} from 'lucide-react'
import AISettingsModal from './AISettingsModal'

interface Message {
  id: string
  type: 'user' | 'assistant'
  content: string
  timestamp: Date
  data?: any
  chart?: 'bar' | 'line' | 'pie'
  model?: string
  isAIPowered?: boolean
  isStreaming?: boolean
}

interface Props {
  isOpen: boolean
  onClose: () => void
}

const quickQueries = [
  { text: "Summarize current fleet status", Icon: Activity },
  { text: "Which vehicles are active right now?", Icon: Truck },
  { text: "Show offline vehicles and risk", Icon: AlertTriangle },
  { text: "What changed in today's trips?", Icon: Route },
  { text: "Which safety scores need attention?", Icon: ShieldCheck },
  { text: "Explain current utilization", Icon: Gauge }
]

interface AIConfig {
  ai_enabled: boolean
  model?: string
  provider: string
  provider_name?: string
}

export default function FleetChat({ isOpen, onClose }: Props) {
  const [messages, setMessages] = useState<Message[]>([])
  const [inputValue, setInputValue] = useState('')
  const [isTyping, setIsTyping] = useState(false)
  const [isStreaming, setIsStreaming] = useState(false)
  const [showSettings, setShowSettings] = useState(false)
  const [aiConfig, setAiConfig] = useState<AIConfig | null>(null)
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLInputElement>(null)
  const streamingMessageRef = useRef<string>('')

  const aiProviderLabel = aiConfig?.provider_name || (aiConfig?.provider === 'openrouter' ? 'OpenRouter AI' : 'AI')

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }

  useEffect(() => {
    scrollToBottom()
  }, [messages])

  useEffect(() => {
    if (isOpen && inputRef.current) {
      inputRef.current.focus()
    }
  }, [isOpen])

  // Fetch AI config and initialize welcome message
  useEffect(() => {
    if (isOpen && messages.length === 0) {
      fetchAIConfig()
      initializeChat()
    }
  }, [isOpen])

  const fetchAIConfig = async () => {
    try {
      const response = await fetch('/api/ai/config')
      if (response.ok) {
        const config = await response.json()
        setAiConfig(config)
      }
    } catch (error) {
      console.error('Failed to fetch AI config:', error)
    }
  }

  const initializeChat = () => {
    const welcomeMessage: Message = {
      id: '1',
      type: 'assistant',
      content: "Hello. I can answer questions using live FleetPulse fleet context. If a metric is not available from the connected telemetry, I will say that instead of guessing.",
      timestamp: new Date(),
      model: 'welcome',
      isAIPowered: false
    }
    setMessages([welcomeMessage])
  }

  const generateStreamingResponse = async (userMessage: string): Promise<void> => {
    if (!aiConfig?.ai_enabled) {
      // For non-AI, use regular response
      return generateNonStreamingResponse(userMessage)
    }

    const conversationHistory = messages.slice(1, -1).map(msg => ({
      type: msg.type,
      content: msg.content
    }))

    try {
      const response = await fetch('/api/ai/chat/stream', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          message: userMessage,
          conversation_history: conversationHistory
        })
      })

      if (!response.ok) {
        throw new Error('Failed to start streaming')
      }

      const reader = response.body?.getReader()
      if (!reader) {
        throw new Error('No response body')
      }

      // Create initial streaming message
      const streamingMessageId = (Date.now() + 1).toString()
      const streamingMessage: Message = {
        id: streamingMessageId,
        type: 'assistant',
        content: '',
        timestamp: new Date(),
        isStreaming: true,
        model: aiConfig?.model || 'streaming',
        isAIPowered: true
      }

      setMessages(prev => [...prev, streamingMessage])
      setIsStreaming(true)
      streamingMessageRef.current = ''

      const decoder = new TextDecoder()

      try {
        while (true) {
          const { done, value } = await reader.read()
          
          if (done) break

          const chunk = decoder.decode(value, { stream: true })
          const lines = chunk.split('\n')

          for (const line of lines) {
            if (line.startsWith('data: ')) {
              try {
                const data = JSON.parse(line.slice(6))
                
                if (data.chunk && data.type === 'text') {
                  // Update streaming content
                  streamingMessageRef.current += data.chunk
                  
                  setMessages(prev => prev.map(msg => 
                    msg.id === streamingMessageId 
                      ? { ...msg, content: streamingMessageRef.current }
                      : msg
                  ))
                } else if (data.type === 'complete') {
                  // Finalize message with chart data and insights
                  setMessages(prev => prev.map(msg => 
                    msg.id === streamingMessageId 
                      ? { 
                          ...msg, 
                          content: streamingMessageRef.current,
                          data: data.data,
                          chart: data.chart_type,
                          isStreaming: false,
                          model: data.model,
                          isAIPowered: data.is_ai_powered
                        }
                      : msg
                  ))
                  
                  // Add insights as separate messages
                  if (data.insights && data.insights.length > 0) {
                    setTimeout(() => {
                      const insightMessages = data.insights.map((insight: string, index: number) => ({
                        id: (Date.now() + 2 + index).toString(),
                        type: 'assistant' as const,
                        content: `AI Insight: ${insight}`,
                        timestamp: new Date(),
                        model: data.model,
                        isAIPowered: true
                      }))
                      
                      setMessages(prev => [...prev, ...insightMessages])
                    }, 1000)
                  }
                } else if (data.error) {
                  throw new Error(data.error)
                }
              } catch (parseError) {
                console.error('Error parsing SSE data:', parseError)
              }
            }
          }
        }
      } finally {
        setIsStreaming(false)
      }

    } catch (error) {
      console.error('Streaming error:', error)
      setIsStreaming(false)
      
      // Remove failed streaming message and fall back to regular response
      setMessages(prev => prev.filter(msg => !msg.isStreaming))
      return generateNonStreamingResponse(userMessage)
    }
  }

  const generateNonStreamingResponse = async (userMessage: string): Promise<void> => {
    const conversationHistory = messages.slice(1, -1).map(msg => ({
      type: msg.type,
      content: msg.content
    }))

    try {
      // Use new /api/ai/chat endpoint
      const response = await fetch('/api/ai/chat', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          message: userMessage,
          conversation_history: conversationHistory
        })
      })

      if (!response.ok) {
        throw new Error('Failed to get AI response')
      }

      const data = await response.json()
      
      const assistantMessage: Message = {
        id: (Date.now() + 1).toString(),
        type: 'assistant',
        content: data.response,
        timestamp: new Date(),
        data: data.data,
        chart: data.chart_type,
        model: data.model,
        isAIPowered: data.is_ai_powered
      }

      setMessages(prev => [...prev, assistantMessage])
      
      // Add insights as follow-up messages if available
      if (data.insights && data.insights.length > 0) {
        setTimeout(() => {
          const insightMessages = data.insights.map((insight: string, index: number) => ({
            id: (Date.now() + 2 + index).toString(),
            type: 'assistant' as const,
            content: `AI Insight: ${insight}`,
            timestamp: new Date(),
            model: data.model,
            isAIPowered: data.is_ai_powered
          }))
          
          setMessages(prev => [...prev, ...insightMessages])
        }, 1000)
      }

    } catch (error) {
      console.error('Error getting AI response:', error)
      
      const errorMessage: Message = {
        id: (Date.now() + 1).toString(),
        type: 'assistant',
        content: "I could not reach the AI service right now. Please try again, or ask a live fleet status question after the service is back online.",
        timestamp: new Date(),
        model: 'error-fallback',
        isAIPowered: false
      }
      
      setMessages(prev => [...prev, errorMessage])
    }
  }

  const handleSend = async () => {
    if (!inputValue.trim() || isTyping || isStreaming) return

    const userMessage: Message = {
      id: Date.now().toString(),
      type: 'user',
      content: inputValue,
      timestamp: new Date()
    }

    const messageText = inputValue
    setMessages(prev => [...prev, userMessage])
    setInputValue('')
    setIsTyping(true)

    try {
      // Use streaming when the backend AI provider is enabled.
      if (aiConfig?.ai_enabled) {
        await generateStreamingResponse(messageText)
      } else {
        await generateNonStreamingResponse(messageText)
      }
    } catch (error) {
      console.error('Error processing message:', error)
    } finally {
      setIsTyping(false)
    }
  }

  const handleQuickQuery = (query: string) => {
    setInputValue(query)
  }

  const renderChart = (message: Message) => {
    if (!message.data || !message.chart) return null

    const chartProps = {
      width: "100%",
      height: 200,
      data: message.data
    }

    switch (message.chart) {
      case 'bar':
        return (
          <ResponsiveContainer {...chartProps}>
            <BarChart data={message.data}>
              <XAxis dataKey="location" stroke="#9ca3af" fontSize={12} angle={-45} textAnchor="end" height={60} />
              <YAxis stroke="#9ca3af" fontSize={12} />
              <Tooltip 
                contentStyle={{ backgroundColor: '#1f2937', border: 'none', borderRadius: '8px' }}
                labelStyle={{ color: '#f3f4f6' }}
              />
              <Bar dataKey="score" radius={[4, 4, 0, 0]} fill="#3b82f6" />
              <Bar dataKey="minutes" radius={[4, 4, 0, 0]} fill="#3b82f6" />
            </BarChart>
          </ResponsiveContainer>
        )
      
      case 'line':
        return (
          <ResponsiveContainer {...chartProps}>
            <LineChart data={message.data}>
              <XAxis dataKey="day" stroke="#9ca3af" fontSize={12} />
              <XAxis dataKey="hour" stroke="#9ca3af" fontSize={12} />
              <YAxis stroke="#9ca3af" fontSize={12} />
              <Tooltip 
                contentStyle={{ backgroundColor: '#1f2937', border: 'none', borderRadius: '8px' }}
                labelStyle={{ color: '#f3f4f6' }}
              />
              <Line type="monotone" dataKey="efficiency" stroke="#10b981" strokeWidth={3} dot={{ fill: '#10b981', strokeWidth: 2, r: 4 }} />
              <Line type="monotone" dataKey="rate" stroke="#3b82f6" strokeWidth={3} dot={{ fill: '#3b82f6', strokeWidth: 2, r: 4 }} />
            </LineChart>
          </ResponsiveContainer>
        )
      
      case 'pie':
        return (
          <ResponsiveContainer {...chartProps}>
            <PieChart>
              <Pie
                data={message.data}
                cx="50%"
                cy="50%"
                outerRadius={80}
                innerRadius={30}
                paddingAngle={2}
                dataKey="savings"
                nameKey="category"
              >
                {message.data.map((entry: any, index: number) => (
                  <Cell key={`cell-${index}`} fill={entry.color} />
                ))}
              </Pie>
              <Pie
                data={message.data}
                cx="50%"
                cy="50%"
                outerRadius={80}
                innerRadius={30}
                paddingAngle={2}
                dataKey="count"
                nameKey="priority"
              >
                {message.data.map((entry: any, index: number) => (
                  <Cell key={`cell-${index}`} fill={entry.color} />
                ))}
              </Pie>
              <Tooltip 
                contentStyle={{ backgroundColor: '#1f2937', border: 'none', borderRadius: '8px' }}
                labelStyle={{ color: '#f3f4f6' }}
              />
            </PieChart>
          </ResponsiveContainer>
        )
      
      default:
        return null
    }
  }

  if (!isOpen) return null

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      className="fixed inset-0 bg-black/50 backdrop-blur-sm z-50 flex items-center justify-center p-4"
      onClick={onClose}
    >
      <motion.div
        initial={{ opacity: 0, scale: 0.9, y: 20 }}
        animate={{ opacity: 1, scale: 1, y: 0 }}
        exit={{ opacity: 0, scale: 0.9, y: 20 }}
        className="bg-gray-900 rounded-xl shadow-2xl border border-gray-800 w-full max-w-2xl h-[600px] flex flex-col"
        onClick={e => e.stopPropagation()}
      >
        {/* Header */}
        <div className="p-4 border-b border-gray-800 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className={`p-2 bg-gradient-to-r rounded-lg ${
              aiConfig?.ai_enabled 
                ? 'from-purple-500 to-pink-600' 
                : 'from-blue-500 to-purple-600'
            }`}>
              {aiConfig?.ai_enabled ? (
                <Brain className="w-5 h-5 text-white" />
              ) : (
                <Bot className="w-5 h-5 text-white" />
              )}
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h3 className="font-semibold">Fleet Intelligence Assistant</h3>
                {aiConfig?.ai_enabled && (
                  <div className="flex items-center gap-1 px-2 py-1 bg-purple-900/30 border border-purple-500/30 rounded-full">
                    <Sparkles className="w-3 h-3 text-purple-400" />
                    <span className="text-xs text-purple-300">AI Powered</span>
                  </div>
                )}
              </div>
              <p className="text-xs text-gray-400">
                {aiConfig?.ai_enabled 
                  ? `${aiProviderLabel} • ${aiConfig.model}`
                  : 'AI unavailable • Live data only'
                }
              </p>
            </div>
          </div>
          
          <div className="flex items-center gap-2">
            <button
              onClick={() => setShowSettings(true)}
              className="p-2 text-gray-400 hover:text-white hover:bg-gray-800 rounded-lg transition-colors"
              title="AI Settings"
            >
              <Settings className="w-4 h-4" />
            </button>
            <button
              onClick={onClose}
              className="p-2 text-gray-400 hover:text-white hover:bg-gray-800 rounded-lg transition-colors"
            >
              ✕
            </button>
          </div>
        </div>

        {/* Messages */}
        <div className="flex-1 overflow-y-auto p-4 space-y-4">
          <AnimatePresence>
            {messages.map((message, index) => (
              <motion.div
                key={message.id}
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -20 }}
                transition={{ delay: index * 0.1 }}
                className={`flex gap-3 ${message.type === 'user' ? 'flex-row-reverse' : ''}`}
              >
                <div className={`flex-shrink-0 w-8 h-8 rounded-full flex items-center justify-center ${
                  message.type === 'user' 
                    ? 'bg-blue-600' 
                    : 'bg-gradient-to-r from-purple-500 to-pink-600'
                }`}>
                  {message.type === 'user' ? (
                    <User className="w-4 h-4 text-white" />
                  ) : (
                    <Bot className="w-4 h-4 text-white" />
                  )}
                </div>
                <div className={`flex-1 ${message.type === 'user' ? 'text-right' : ''}`}>
                  <div className={`inline-block p-3 rounded-xl max-w-[80%] relative ${
                    message.type === 'user'
                      ? 'bg-blue-600 text-white'
                      : 'bg-gray-800 text-gray-100'
                  }`}>
                    <div className="whitespace-pre-wrap">{message.content}</div>
                    {message.data && message.chart && (
                      <div className="mt-3 p-2 bg-gray-700/50 rounded-lg">
                        {renderChart(message)}
                      </div>
                    )}
                    
                    {/* AI Status Badge */}
                    {message.type === 'assistant' && message.model && message.model !== 'welcome' && (
                      <div className="absolute -top-2 -right-2">
                        {message.isAIPowered ? (
                          <div className="flex items-center gap-1 px-2 py-1 bg-purple-600 text-white text-xs rounded-full">
                            <Brain className="w-3 h-3" />
                            AI
                          </div>
                        ) : (
                          <div className="flex items-center gap-1 px-2 py-1 bg-gray-600 text-white text-xs rounded-full">
                            <Bot className="w-3 h-3" />
                            Offline
                          </div>
                        )}
                      </div>
                    )}
                    
                    {/* Streaming Indicator */}
                    {message.isStreaming && (
                      <div className="mt-2 flex items-center gap-2 text-xs text-gray-400">
                        <div className="w-1 h-1 bg-purple-400 rounded-full animate-pulse" />
                        <span>Streaming response...</span>
                      </div>
                    )}
                  </div>
                  <div className="text-xs text-gray-500 mt-1 flex items-center gap-2">
                    {message.timestamp.toLocaleTimeString()}
                    {message.model && message.model !== 'welcome' && (
                      <span className="text-gray-600">
                        • {message.isAIPowered ? message.model : 'Service unavailable'}
                      </span>
                    )}
                  </div>
                </div>
              </motion.div>
            ))}
          </AnimatePresence>

          {(isTyping || isStreaming) && (
            <motion.div
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              className="flex gap-3"
            >
              <div className={`flex-shrink-0 w-8 h-8 rounded-full flex items-center justify-center ${
                aiConfig?.ai_enabled 
                  ? 'bg-gradient-to-r from-purple-500 to-pink-600' 
                  : 'bg-gradient-to-r from-blue-500 to-purple-600'
              }`}>
                {aiConfig?.ai_enabled ? (
                  <Brain className="w-4 h-4 text-white" />
                ) : (
                  <Bot className="w-4 h-4 text-white" />
                )}
              </div>
              <div className="bg-gray-800 rounded-xl p-3">
                <div className="flex items-center gap-2">
                  <div className="flex gap-1">
                    <div className="w-2 h-2 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: '0ms' }} />
                    <div className="w-2 h-2 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: '150ms' }} />
                    <div className="w-2 h-2 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: '300ms' }} />
                  </div>
                  <span className="text-xs text-gray-400">
                    {isStreaming ? 'AI is thinking...' : 'Processing...'}
                  </span>
                </div>
              </div>
            </motion.div>
          )}
          <div ref={messagesEndRef} />
        </div>

        {/* Quick Query Buttons */}
        <div className="p-4 border-t border-gray-800">
          <p className="text-xs text-gray-400 mb-3">Starter prompts:</p>
          <div className="grid grid-cols-2 gap-2 mb-4">
            {quickQueries.map((query, index) => {
              const PromptIcon = query.Icon
              return (
                <button
                  key={index}
                  onClick={() => handleQuickQuery(query.text)}
                  className="text-xs p-2 bg-gray-800 hover:bg-gray-700 rounded-lg text-left transition-colors flex items-center gap-2"
                >
                  <PromptIcon className="w-3.5 h-3.5 flex-shrink-0 text-blue-300" />
                  <span className="truncate">{query.text}</span>
                </button>
              )
            })}
          </div>

          {/* Input */}
          <div className="flex gap-2">
            <input
              ref={inputRef}
              type="text"
              value={inputValue}
              onChange={(e) => setInputValue(e.target.value)}
              onKeyPress={(e) => e.key === 'Enter' && handleSend()}
              placeholder={
                aiConfig?.ai_enabled 
                  ? "Ask me anything about your fleet..."
                  : "AI is offline; retry after configuration is restored"
              }
              disabled={isTyping || isStreaming}
              className="flex-1 bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-blue-500 transition-colors disabled:opacity-50"
            />
            <button
              onClick={handleSend}
              disabled={!inputValue.trim() || isTyping || isStreaming}
              className="bg-blue-600 hover:bg-blue-500 disabled:bg-gray-600 disabled:cursor-not-allowed text-white p-2 rounded-lg transition-colors"
            >
              <Send className="w-4 h-4" />
            </button>
          </div>
          
          {/* Status Message */}
          {aiConfig && (
            <div className="text-center">
              <p className="text-xs text-gray-500">
                {aiConfig.ai_enabled 
                  ? `Enhanced with ${aiProviderLabel} • ${aiConfig.model}`
                  : 'AI provider unavailable'
                }
              </p>
            </div>
          )}
        </div>
      </motion.div>
      
      {/* AI Settings Modal */}
      <AISettingsModal
        isOpen={showSettings}
        onClose={() => setShowSettings(false)}
        onConfigChange={() => {
          fetchAIConfig()
          // Optionally refresh the chat or show a notification
        }}
      />
    </motion.div>
  )
}
