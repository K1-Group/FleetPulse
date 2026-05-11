import { useState, useEffect } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { Settings, Key, Brain, ExternalLink, AlertCircle, CheckCircle, Loader, CreditCard, Zap, Bot } from 'lucide-react'

interface Props {
  isOpen: boolean
  onClose: () => void
  onConfigChange?: () => void
}

interface AIConfig {
  ai_enabled: boolean
  model?: string
  provider: 'anthropic' | 'openrouter' | 'demo'
  provider_name: string
}

type ProviderOption = 'anthropic' | 'openrouter' | 'demo'

export default function AISettingsModal({ isOpen, onClose, onConfigChange }: Props) {
  const [selectedProvider, setSelectedProvider] = useState<ProviderOption>('anthropic')
  const [apiKey, setApiKey] = useState('')
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState(false)
  const [aiConfig, setAiConfig] = useState<AIConfig | null>(null)

  // Fetch current AI config when modal opens
  useEffect(() => {
    if (isOpen) {
      fetchAIConfig()
    }
  }, [isOpen])

  const fetchAIConfig = async () => {
    try {
      const response = await fetch('/api/ai/config')
      if (response.ok) {
        const config = await response.json()
        setAiConfig(config)
        setSelectedProvider(config.provider || 'demo')
      }
    } catch (error) {
      console.error('Failed to fetch AI config:', error)
    }
  }

  const handleSaveKey = async () => {
    // Demo mode doesn't require an API key
    if (selectedProvider === 'demo') {
      setIsLoading(true)
      setError('')
      setSuccess(false)

      try {
        const response = await fetch('/api/ai/config', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({ api_key: '', provider: 'demo' }),
        })

        if (response.ok) {
          setSuccess(true)
          await fetchAIConfig() // Refresh config
          onConfigChange?.()
          setTimeout(() => setSuccess(false), 3000)
        } else {
          const error = await response.json()
          setError(error.detail || 'Failed to set demo mode')
        }
      } catch (error) {
        setError('Network error. Please try again.')
      } finally {
        setIsLoading(false)
      }
      return
    }

    // For API providers, require a key
    if (!apiKey.trim()) {
      setError('Please enter an API key')
      return
    }

    setIsLoading(true)
    setError('')
    setSuccess(false)

    try {
      const response = await fetch('/api/ai/config', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ 
          api_key: apiKey, 
          provider: selectedProvider 
        }),
      })

      if (response.ok) {
        const result = await response.json()
        setSuccess(true)
        setApiKey('') // Clear the input for security
        await fetchAIConfig() // Refresh config
        
        // Notify parent component
        onConfigChange?.()
        
        setTimeout(() => {
          setSuccess(false)
        }, 3000)
      } else {
        const error = await response.json()
        setError(error.detail || 'Failed to configure API key')
      }
    } catch (error) {
      setError('Network error. Please try again.')
    } finally {
      setIsLoading(false)
    }
  }

  const handleClose = () => {
    setApiKey('')
    setError('')
    setSuccess(false)
    onClose()
  }

  if (!isOpen) return null

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      className="fixed inset-0 bg-black/50 backdrop-blur-sm z-50 flex items-center justify-center p-4"
      onClick={handleClose}
    >
      <motion.div
        initial={{ opacity: 0, scale: 0.9, y: 20 }}
        animate={{ opacity: 1, scale: 1, y: 0 }}
        exit={{ opacity: 0, scale: 0.9, y: 20 }}
        className="bg-gray-900 rounded-xl shadow-2xl border border-gray-800 w-full max-w-2xl max-h-[90vh] overflow-y-auto"
        onClick={e => e.stopPropagation()}
      >
        {/* Header */}
        <div className="p-6 border-b border-gray-800 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-gradient-to-r from-purple-500 to-pink-600 rounded-lg">
              <Settings className="w-5 h-5 text-white" />
            </div>
            <div>
              <h3 className="font-semibold text-lg">AI Settings</h3>
              <p className="text-sm text-gray-400">Configure the fleet intelligence provider</p>
            </div>
          </div>
          <button
            onClick={handleClose}
            className="text-gray-400 hover:text-white transition-colors"
          >
            ✕
          </button>
        </div>

        {/* Content */}
        <div className="p-6 space-y-6">
          {/* Current Status */}
          <div className="bg-gray-800/50 rounded-lg p-4">
            <div className="flex items-center gap-3 mb-2">
              <Brain className="w-5 h-5 text-purple-400" />
              <span className="font-medium">Current Status</span>
            </div>
            
            {aiConfig ? (
              <div className="space-y-2 text-sm">
                <div className="flex items-center gap-2">
                  {aiConfig.ai_enabled ? (
                    <CheckCircle className="w-4 h-4 text-green-500" />
                  ) : (
                    <AlertCircle className="w-4 h-4 text-yellow-500" />
                  )}
                  <span>
                    {aiConfig.ai_enabled 
                      ? `Active (${aiConfig.model})` 
                      : 'AI unavailable'
                    }
                  </span>
                </div>
                <p className="text-gray-400">
                  Provider: {aiConfig.provider_name}
                </p>
              </div>
            ) : (
              <div className="flex items-center gap-2 text-sm text-gray-400">
                <Loader className="w-4 h-4 animate-spin" />
                Loading configuration...
              </div>
            )}
          </div>

          {/* Provider Options */}
          <div className="space-y-4">
            <div className="flex items-center gap-2">
              <Settings className="w-5 h-5 text-blue-400" />
              <label className="font-medium">Choose AI Provider</label>
            </div>
            
            {/* Anthropic API */}
            <div className={`border-2 rounded-lg p-4 cursor-pointer transition-all ${
              selectedProvider === 'anthropic' 
                ? 'border-blue-500 bg-blue-500/10' 
                : 'border-gray-700 hover:border-gray-600'
            }`} onClick={() => setSelectedProvider('anthropic')}>
              <div className="flex items-start gap-3">
                <input
                  type="radio"
                  checked={selectedProvider === 'anthropic'}
                  onChange={() => setSelectedProvider('anthropic')}
                  className="mt-1"
                />
                <div className="flex-1">
                  <div className="flex items-center gap-2 mb-2">
                    <CreditCard className="w-4 h-4 text-blue-400" />
                    <h4 className="font-medium text-white">Anthropic API</h4>
                  </div>
                  <p className="text-sm text-gray-400">
                    Direct API access, pay per use. Most reliable option.
                  </p>
                  <p className="text-xs text-gray-500 mt-1">
                    ~$3 per million input tokens • console.anthropic.com
                  </p>
                </div>
              </div>
            </div>

            {/* OpenRouter */}
            <div className={`border-2 rounded-lg p-4 cursor-pointer transition-all ${
              selectedProvider === 'openrouter' 
                ? 'border-green-500 bg-green-500/10' 
                : 'border-gray-700 hover:border-gray-600'
            }`} onClick={() => setSelectedProvider('openrouter')}>
              <div className="flex items-start gap-3">
                <input
                  type="radio"
                  checked={selectedProvider === 'openrouter'}
                  onChange={() => setSelectedProvider('openrouter')}
                  className="mt-1"
                />
                <div className="flex-1">
                  <div className="flex items-center gap-2 mb-2">
                    <Zap className="w-4 h-4 text-green-400" />
                    <h4 className="font-medium text-white">OpenRouter</h4>
                    <span className="px-2 py-1 bg-green-900/50 text-green-300 text-xs rounded-full">
                      Recommended
                    </span>
                  </div>
                  <p className="text-sm text-gray-400">
                    Use your Claude Max/Pro subscription. Free tier available.
                  </p>
                  <p className="text-xs text-gray-500 mt-1">
                    Connect subscription at openrouter.ai • Free credits included
                  </p>
                </div>
              </div>
            </div>

            {/* AI Disabled */}
            <div className={`border-2 rounded-lg p-4 cursor-pointer transition-all ${
              selectedProvider === 'demo' 
                ? 'border-gray-500 bg-gray-500/10' 
                : 'border-gray-700 hover:border-gray-600'
            }`} onClick={() => setSelectedProvider('demo')}>
              <div className="flex items-start gap-3">
                <input
                  type="radio"
                  checked={selectedProvider === 'demo'}
                  onChange={() => setSelectedProvider('demo')}
                  className="mt-1"
                />
                <div className="flex-1">
                  <div className="flex items-center gap-2 mb-2">
                    <Bot className="w-4 h-4 text-gray-400" />
                    <h4 className="font-medium text-white">AI Disabled</h4>
                  </div>
                  <p className="text-sm text-gray-400">
                    No API key needed. The chat will not fabricate fleet metrics.
                  </p>
                  <p className="text-xs text-gray-500 mt-1">
                    Use this when provider credentials are unavailable.
                  </p>
                </div>
              </div>
            </div>
          </div>

          {/* API Key Input (only for providers that need keys) */}
          {selectedProvider !== 'demo' && (
            <div className="space-y-4">
              <div className="flex items-center gap-2">
                <Key className="w-5 h-5 text-blue-400" />
                <label htmlFor="apiKey" className="font-medium">
                  {selectedProvider === 'anthropic' ? 'Anthropic API Key' : 'OpenRouter API Key'}
                </label>
              </div>
              
              <div className="space-y-2">
                <input
                  id="apiKey"
                  type="password"
                  value={apiKey}
                  onChange={(e) => setApiKey(e.target.value)}
                  placeholder={
                    aiConfig?.ai_enabled && aiConfig.provider === selectedProvider
                      ? "API key is configured" 
                      : selectedProvider === 'anthropic' 
                        ? "sk-ant-..." 
                        : "sk-or-..."
                  }
                  className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-blue-500 transition-colors"
                />
                
                {error && (
                  <div className="flex items-center gap-2 text-red-400 text-sm">
                    <AlertCircle className="w-4 h-4" />
                    {error}
                  </div>
                )}
                
                {success && (
                  <div className="flex items-center gap-2 text-green-400 text-sm">
                    <CheckCircle className="w-4 h-4" />
                    Configuration saved successfully!
                  </div>
                )}
              </div>
            </div>
          )}

          {/* Save Button */}
          <div>
            <button
              onClick={handleSaveKey}
              disabled={isLoading || (selectedProvider !== 'demo' && !apiKey.trim())}
              className="w-full bg-blue-600 hover:bg-blue-500 disabled:bg-gray-600 disabled:cursor-not-allowed text-white py-3 rounded-lg transition-colors flex items-center justify-center gap-2"
            >
              {isLoading ? (
                <>
                  <Loader className="w-4 h-4 animate-spin" />
                  {selectedProvider === 'demo' ? 'Setting up...' : 'Validating...'}
                </>
              ) : selectedProvider === 'demo' ? (
                'Disable AI'
              ) : (
                `Configure ${selectedProvider === 'anthropic' ? 'Anthropic' : 'OpenRouter'}`
              )}
            </button>
          </div>

          {/* Provider-specific Information */}
          {selectedProvider === 'anthropic' && (
            <div className="bg-blue-900/20 border border-blue-800/30 rounded-lg p-4">
              <h4 className="font-medium text-blue-300 mb-2 flex items-center gap-2">
                <CreditCard className="w-4 h-4" />
                How to get an Anthropic API key:
              </h4>
              <div className="space-y-2 text-sm text-blue-200">
                <p>1. Visit <a href="https://console.anthropic.com" target="_blank" rel="noopener noreferrer" className="underline inline-flex items-center gap-1">
                  console.anthropic.com <ExternalLink className="w-3 h-3" />
                </a></p>
                <p>2. Sign up or log in to your account</p>
                <p>3. Navigate to API Keys and create a new key</p>
                <p>4. Add credit to your account for pay-per-use billing</p>
              </div>
            </div>
          )}

          {selectedProvider === 'openrouter' && (
            <div className="bg-green-900/20 border border-green-800/30 rounded-lg p-4">
              <h4 className="font-medium text-green-300 mb-2 flex items-center gap-2">
                <Zap className="w-4 h-4" />
                How to use OpenRouter with Claude Max/Pro:
              </h4>
              <div className="space-y-2 text-sm text-green-200">
                <p>1. Visit <a href="https://openrouter.ai" target="_blank" rel="noopener noreferrer" className="underline inline-flex items-center gap-1">
                  openrouter.ai <ExternalLink className="w-3 h-3" />
                </a> and sign up</p>
                <p>2. Go to Keys and create a new API key</p>
                <p>3. Connect your Claude subscription or use free tier credits</p>
                <p>4. Free tier includes limited Claude usage without subscription</p>
              </div>
            </div>
          )}

          {selectedProvider === 'demo' && (
            <div className="bg-gray-800/50 border border-gray-700/50 rounded-lg p-4">
              <h4 className="font-medium text-gray-300 mb-2 flex items-center gap-2">
                <Bot className="w-4 h-4" />
                AI Disabled Behavior:
              </h4>
              <div className="space-y-1 text-sm text-gray-300">
                <p>• Does not use a model provider</p>
                <p>• Does not generate fallback fleet numbers</p>
                <p>• Keeps source-of-truth telemetry in Geotab-backed APIs</p>
              </div>
            </div>
          )}

          {/* Privacy Note */}
          {selectedProvider !== 'demo' && (
            <div className="bg-gray-800/30 rounded-lg p-3">
              <p className="text-xs text-gray-400">
                <strong>Privacy:</strong> API keys are stored in memory only and never saved to disk.
                You'll need to re-enter after server restarts.
              </p>
            </div>
          )}
        </div>
      </motion.div>
    </motion.div>
  )
}
