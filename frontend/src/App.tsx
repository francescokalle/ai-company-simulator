import { useEffect, useRef, useState, useCallback } from 'react'
import { Application, Graphics, Text, Container } from 'pixi.js'
import { useStore, Agent, WalkEvent } from './store'

const ROLE_COLORS: Record<string, number> = {
  ceo: 0xffd700,
  manager: 0x4fc3f7,
  worker: 0x81c784,
  efficiency: 0xba68c8,
}

const STATUS_LABELS: Record<string, string> = {
  idle: '💤 Idle',
  walking: '🚶 Walking',
  talking: '💬 Talking',
  working: '⚒️ Working',
  fired: '❌ Fired',
}

interface AgentSprite {
  container: Container
  agentId: string
  targetX: number
  targetY: number
  speed: number
  walkPath: Array<{ x: number; y: number }>
  currentPathIndex: number
  statusText: Text
  nameText: Text
  thoughtText: Text
  body: Graphics
}

const DEFAULT_OFFICES = [
  { id: 'frontend', name: 'Frontend', desc: 'UI, componenti, user experience, design system', icon: '🎨' },
  { id: 'backend', name: 'Backend', desc: 'API, business logic, servizi, autenticazione', icon: '⚙️' },
  { id: 'database', name: 'Database', desc: 'Schema, query, migrazioni, ottimizzazione dati', icon: '🗄️' },
  { id: 'devops', name: 'DevOps', desc: 'CI/CD, deployment, monitoring, infrastruttura', icon: '🚀' },
  { id: 'qa', name: 'QA / Testing', desc: 'Test automation, quality assurance, code review', icon: '🧪' },
  { id: 'security', name: 'Security', desc: 'Audit, vulnerability management, best practices', icon: '🔒' },
  { id: 'docs', name: 'Documentation', desc: 'Documentazione tecnica, guide, API reference', icon: '📚' },
]

const OPTIONAL_OFFICES = [
  { id: 'sales', name: 'Sales', desc: 'Vendite, customer outreach, revenue growth', icon: '💰' },
  { id: 'marketing', name: 'Marketing', desc: 'Brand, promozioni, user acquisition, SEO', icon: '📣' },
  { id: 'legal', name: 'Legal', desc: 'Compliance, contratti, privacy policy', icon: '⚖️' },
  { id: 'support', name: 'Support', desc: 'Customer support, helpdesk, troubleshooting', icon: '🎧' },
]


function LoginScreen() {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const { setToken } = useStore()

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!username.trim() || !password.trim()) {
      setError('Inserisci username e password')
      return
    }

    setLoading(true)
    setError('')

    try {
      const formData = new FormData()
      formData.append('username', username)
      formData.append('password', password)

      const res = await fetch('/api/auth/login', { method: 'POST', body: formData })
      const data = await res.json()

      if (data.success) {
        setToken(data.token)
      } else {
        setError(data.error || data.detail || 'Errore durante l\'autenticazione')
      }
    } catch (err) {
      setError('Errore di connessione')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div style={{
      width: '100vw', height: '100vh', background: '#0f172a',
      display: 'flex', alignItems: 'center', justifyContent: 'center',
    }}>
      <div style={{
        background: '#1e293b', padding: 40, borderRadius: 12, width: 380,
        border: '1px solid #334155',
      }}>
        <h2 style={{ marginBottom: 8, color: '#e2e8f0', textAlign: 'center' }}>
          🏢 AI Virtual Company
        </h2>
        <p style={{ marginBottom: 24, color: '#64748b', textAlign: 'center', fontSize: 13 }}>
          Accedi al tuo account
        </p>

        <form onSubmit={handleSubmit}>
          <div style={{ marginBottom: 12 }}>
            <label style={{ display: 'block', marginBottom: 4, fontSize: 12, color: '#94a3b8' }}>
              Username
            </label>
            <input
              type="text" value={username} onChange={(e) => setUsername(e.target.value)}
              style={{ width: '100%', padding: 10, background: '#0f172a', border: '1px solid #334155', borderRadius: 6, color: '#e2e8f0' }}
              placeholder="username"
            />
          </div>
          <div style={{ marginBottom: 16 }}>
            <label style={{ display: 'block', marginBottom: 4, fontSize: 12, color: '#94a3b8' }}>
              Password
            </label>
            <input
              type="password" value={password} onChange={(e) => setPassword(e.target.value)}
              style={{ width: '100%', padding: 10, background: '#0f172a', border: '1px solid #334155', borderRadius: 6, color: '#e2e8f0' }}
              placeholder="••••••••"
            />
          </div>

          {error && (
            <div style={{ padding: 8, background: '#7f1d1d', borderRadius: 4, marginBottom: 12, fontSize: 12, color: '#fca5a5' }}>
              {error}
            </div>
          )}

          <button
            type="submit" disabled={loading}
            style={{
              width: '100%', padding: 12, background: '#3b82f6', border: 'none',
              borderRadius: 6, color: '#fff', fontWeight: 'bold', cursor: loading ? 'not-allowed' : 'pointer',
              opacity: loading ? 0.6 : 1,
            }}
          >
            {loading ? 'Caricamento...' : 'Accedi'}
          </button>
        </form>
      </div>
    </div>
  )
}

function App() {
  const canvasRef = useRef<HTMLDivElement>(null)
  const appRef = useRef<Application | null>(null)
  const spritesRef = useRef<Map<string, AgentSprite>>(new Map())
  const { companyState, ws, setCompanyState, setShowOnboarding, token, setToken } = useStore()

  useEffect(() => {
    if (!canvasRef.current) return

    const app = new Application({
      resizeTo: window,
      background: 0x0f172a,
      antialias: true,
    })

    canvasRef.current.appendChild(app.view as HTMLCanvasElement)
    appRef.current = app

    drawFloorplan(app)

    return () => {
      app.destroy(true)
    }
  }, [])

  useEffect(() => {
    if (!ws) return

    ws.onmessage = (event) => {
      const msg = JSON.parse(event.data)

      switch (msg.type) {
        case 'state':
          setCompanyState(msg.data)
          break
        case 'company_created':
          setShowOnboarding(false)
          break
        case 'agent_walking':
          handleAgentWalking(msg.data)
          break
        case 'agent_arrived':
          handleAgentArrived(msg.data)
          break
        case 'intent_to_communicate':
          handleCommunication(msg.data)
          break
        case 'agent_fired':
          handleAgentFired(msg.data)
          break
      }
    }
  }, [ws])

  useEffect(() => {
    if (!companyState || !appRef.current) return
    syncSprites(appRef.current, companyState.agents)
  }, [companyState])

  const handleAgentWalking = useCallback((data: WalkEvent) => {
    const sprite = spritesRef.current.get(data.agent_id)
    if (!sprite) return

    sprite.targetX = data.to_pos.x
    sprite.targetY = data.to_pos.y
    sprite.walkPath = generateWalkPath(data.from_pos, data.to_pos)
    sprite.currentPathIndex = 0
    sprite.statusText.text = STATUS_LABELS['walking']
  }, [])

  const handleAgentArrived = useCallback((data: { agent_id: string; target_id: string }) => {
    const sprite = spritesRef.current.get(data.agent_id)
    if (!sprite) return
    sprite.statusText.text = STATUS_LABELS['talking']
    setTimeout(() => {
      sprite.statusText.text = STATUS_LABELS['idle']
    }, 2000)
  }, [])

  const handleCommunication = useCallback((data: { source: string; target: string; message: string }) => {
    const sourceSprite = spritesRef.current.get(data.source)
    const targetSprite = spritesRef.current.get(data.target)
    if (sourceSprite && targetSprite) {
      showMessageBubble(sourceSprite, data.message)
    }
  }, [])

  const handleAgentFired = useCallback((data: { agent_id: string }) => {
    const sprite = spritesRef.current.get(data.agent_id)
    if (sprite && appRef.current) {
      appRef.current.stage.removeChild(sprite.container)
      spritesRef.current.delete(data.agent_id)
    }
  }, [])

  const syncSprites = (app: Application, agents: Record<string, Agent>) => {
    const sprites = spritesRef.current

    Object.values(agents).forEach((agent) => {
      if (!sprites.has(agent.id)) {
        const sprite = createAgentSprite(agent)
        sprites.set(agent.id, sprite)
        app.stage.addChild(sprite.container)
      }
    })

    sprites.forEach((sprite, id) => {
      if (!agents[id]) {
        app.stage.removeChild(sprite.container)
        sprites.delete(id)
      }
    })

    Object.values(agents).forEach((agent) => {
      const sprite = sprites.get(agent.id)
      if (sprite) {
        sprite.nameText.text = agent.name
        sprite.thoughtText.text = agent.thoughts?.substring(0, 40) || ''
        if (agent.status !== 'walking') {
          sprite.statusText.text = STATUS_LABELS[agent.status] || agent.status
        }
      }
    })
  }

  const createAgentSprite = (agent: Agent): AgentSprite => {
    const container = new Container()
    const color = ROLE_COLORS[agent.role] || 0xffffff

    const body = new Graphics()
    body.beginFill(color)
    body.drawCircle(0, 0, 15)
    body.endFill()
    body.lineStyle(2, 0xffffff, 0.8)
    body.drawCircle(0, 0, 15)

    const roleIndicator = new Graphics()
    roleIndicator.beginFill(0xffffff, 0.3)
    roleIndicator.drawCircle(0, 0, 8)
    roleIndicator.endFill()

    const nameText = new Text(agent.name, {
      fontFamily: 'Segoe UI',
      fontSize: 10,
      fill: 0xffffff,
      fontWeight: 'bold',
    })
    nameText.anchor.set(0.5, 0)
    nameText.y = 18

    const statusText = new Text(STATUS_LABELS[agent.status] || agent.status, {
      fontFamily: 'Segoe UI',
      fontSize: 9,
      fill: 0x94a3b8,
    })
    statusText.anchor.set(0.5, 0)
    statusText.y = 32

    const thoughtText = new Text('', {
      fontFamily: 'Segoe UI',
      fontSize: 8,
      fill: 0xcbd5e1,
      wordWrap: true,
      wordWrapWidth: 100,
    })
    thoughtText.anchor.set(0.5, 1)
    thoughtText.y = -20

    container.addChild(body, roleIndicator, nameText, statusText, thoughtText)
    container.x = agent.position.x
    container.y = agent.position.y
    container.eventMode = 'static'
    container.cursor = 'pointer'

    container.on('pointerdown', () => {
      const { setSelectedAgent, setShowAgentModal, setSelectedAgentData, setAgentChatLog, setAgentTaskQueue } = useStore.getState()
      setSelectedAgent(agent.id)
      setSelectedAgentData(agent)
      setAgentChatLog([])
      setAgentTaskQueue([])
      setShowAgentModal(true)

      const token = useStore.getState().token
      fetch(`/api/agents/${agent.id}`, {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      })
        .then((r) => r.json())
        .then((data) => {
          setSelectedAgentData(data)
          setAgentChatLog(data.chat_log || [])
          setAgentTaskQueue(data.task_queue || [])
        })
    })

    return {
      container,
      agentId: agent.id,
      targetX: agent.position.x,
      targetY: agent.position.y,
      speed: 2,
      walkPath: [],
      currentPathIndex: 0,
      statusText,
      nameText,
      thoughtText,
      body,
    }
  }

  const generateWalkPath = (from: { x: number; y: number }, to: { x: number; y: number }): Array<{ x: number; y: number }> => {
    const path: Array<{ x: number; y: number }> = []
    const steps = 20
    for (let i = 0; i <= steps; i++) {
      const t = i / steps
      const midX = (from.x + to.x) / 2
      const midY = (from.y + to.y) / 2 - 50
      const x = (1 - t) * (1 - t) * from.x + 2 * (1 - t) * t * midX + t * t * to.x
      const y = (1 - t) * (1 - t) * from.y + 2 * (1 - t) * t * midY + t * t * to.y
      path.push({ x, y })
    }
    return path
  }

  const showMessageBubble = (sprite: AgentSprite, message: string) => {
    const bubble = new Text(message.substring(0, 30) + '...', {
      fontFamily: 'Segoe UI',
      fontSize: 9,
      fill: 0xffffff,
      backgroundColor: 0x3b82f6,
      padding: 4,
    })
    bubble.anchor.set(0.5, 1)
    bubble.y = -40
    sprite.container.addChild(bubble)

    setTimeout(() => {
      sprite.container.removeChild(bubble)
      bubble.destroy()
    }, 3000)
  }

  useEffect(() => {
    let animationId: number

    const animate = () => {
      spritesRef.current.forEach((sprite) => {
        if (sprite.walkPath.length > 0 && sprite.currentPathIndex < sprite.walkPath.length) {
          const target = sprite.walkPath[sprite.currentPathIndex]
          const dx = target.x - sprite.container.x
          const dy = target.y - sprite.container.y
          const dist = Math.sqrt(dx * dx + dy * dy)

          if (dist < 2) {
            sprite.currentPathIndex++
          } else {
            sprite.container.x += (dx / dist) * sprite.speed
            sprite.container.y += (dy / dist) * sprite.speed
          }
        }
      })
      animationId = requestAnimationFrame(animate)
    }

    animate()
    return () => cancelAnimationFrame(animationId)
  }, [])

  // Show login if not authenticated
  if (!token) {
    return <LoginScreen />
  }

  return (
    <div style={{ width: '100vw', height: '100vh', position: 'relative' }}>
      <div ref={canvasRef} style={{ width: '100%', height: '100%' }} />
      <HUD />
      <OnboardingModal />
      <AgentModal />
      <MessageInput />
    </div>
  )
}

function drawFloorplan(app: Application) {
  const floor = new Graphics()
  floor.beginFill(0x1e293b)
  floor.drawRect(0, 0, window.innerWidth, window.innerHeight)
  floor.endFill()

  const zones = [
    { x: 50, y: 50, w: 300, h: 200, label: 'CEO Office', color: 0x2d3748 },
    { x: 400, y: 50, w: 300, h: 200, label: 'Efficiency', color: 0x2d3748 },
    { x: 50, y: 300, w: 300, h: 200, label: 'Frontend', color: 0x1a365d },
    { x: 400, y: 300, w: 300, h: 200, label: 'Backend', color: 0x1a365d },
    { x: 50, y: 550, w: 300, h: 200, label: 'Database', color: 0x22543d },
    { x: 400, y: 550, w: 300, h: 200, label: 'Config', color: 0x744210 },
  ]

  zones.forEach((zone) => {
    floor.beginFill(zone.color, 0.5)
    floor.drawRoundedRect(zone.x, zone.y, zone.w, zone.h, 10)
    floor.endFill()
    floor.lineStyle(2, 0x4a5568, 0.5)
    floor.drawRoundedRect(zone.x, zone.y, zone.w, zone.h, 10)
  })

  app.stage.addChild(floor)

  zones.forEach((zone) => {
    const label = new Text(zone.label, {
      fontFamily: 'Segoe UI',
      fontSize: 14,
      fill: 0x94a3b8,
      fontWeight: 'bold',
    })
    label.x = zone.x + 10
    label.y = zone.y + 10
    app.stage.addChild(label)
  })
}

function HUD() {
  const { companyState, connected } = useStore()
  if (!companyState) return null

  return (
    <div style={{
      position: 'absolute', top: 10, right: 10, background: 'rgba(15,23,42,0.9)',
      padding: '12px 16px', borderRadius: 8, border: '1px solid #334155',
      fontSize: 12, minWidth: 180,
    }}>
      <div style={{ fontWeight: 'bold', marginBottom: 8, color: '#e2e8f0' }}>Company Status</div>
      <div>Agents: {companyState.agent_count}/{companyState.max_agents}</div>
      <div>Offices: {Object.keys(companyState.offices).length}</div>
      <div>Status: {connected ? '🟢 Connected' : '🔴 Disconnected'}</div>
      <div>Running: {companyState.running ? '✅' : '❌'}</div>
    </div>
  )
}

function OnboardingModal() {
  const { showOnboarding, setShowOnboarding, setGithubInviteUrl } = useStore()
  const [sourceType, setSourceType] = useState<'zip' | 'github'>('github')
  const [apiKey, setApiKey] = useState('')
  const [projectName, setProjectName] = useState('')
  const [file, setFile] = useState<File | null>(null)
  const [githubUrl, setGithubUrl] = useState('')
  const [githubAppId, setGithubAppId] = useState('')
  
  
  const [inviteUrl, setInviteUrl] = useState<string | null>(null)
  const [invited, setInvited] = useState(false)
  const [selectedDefault, setSelectedDefault] = useState<Set<string>>(new Set(DEFAULT_OFFICES.map(o => o.id)))
  const [selectedOptional, setSelectedOptional] = useState<Set<string>>(new Set())
  const [customOffices, setCustomOffices] = useState('')
  const [loading, setLoading] = useState(false)
  const [settingsLoaded, setSettingsLoaded] = useState(false)
  const [keyStatus, setKeyStatus] = useState<{ok: boolean; message: string} | null>(null)

  // Validate + upload the private key to the server (never kept in browser state)
  const handlePrivateKeyUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0]
    if (!f) return

    const text = await f.text()
    if (!text.includes('BEGIN RSA PRIVATE KEY') && !text.includes('PRIVATE KEY')) {
      setKeyStatus({ ok: false, message: 'File non valido: manca l\'header PEM.' })
      return
    }

    const token = useStore.getState().token
    setKeyStatus({ ok: true, message: 'Caricamento...' })
    try {
      const fd = new FormData()
      fd.append('private_key', text)
      const res = await fetch('/api/github/upload-key', {
        method: 'POST',
        body: fd,
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      })
      const data = await res.json()
      if (data.success) {
        setKeyStatus({
          ok: true,
          message: `Chiave caricata e validata (RSA ${data.key_size} bit).`,
        })
      } else {
        setKeyStatus({ ok: false, message: data.error || 'Chiave rifiutata.' })
      }
    } catch {
      setKeyStatus({ ok: false, message: 'Errore di rete durante il caricamento.' })
    }
  }

  // Load saved settings when the modal opens
  useEffect(() => {
    const token = useStore.getState().token
    if (!token || settingsLoaded) return

    fetch('/api/settings', {
      headers: { Authorization: `Bearer ${token}` },
    })
      .then((r) => r.json())
      .then((data) => {
        if (data.success && data.settings) {
          const s = data.settings
          if (s.opencode_api_key && s.opencode_api_key !== '***') setApiKey(s.opencode_api_key)
          if (s.github_repo_url) setGithubUrl(s.github_repo_url)
          if (s.github_app_id) setGithubAppId(s.github_app_id)
          if (s.optional_offices?.length) setSelectedOptional(new Set(s.optional_offices))
          if (s.custom_offices?.length) setCustomOffices(s.custom_offices.join(', '))
        }
        setSettingsLoaded(true)
      })
      .catch(() => setSettingsLoaded(true))
  }, [settingsLoaded])

  if (!showOnboarding) return null

  const toggleOffice = (id: string, list: Set<string>, setList: (s: Set<string>) => void) => {
    const next = new Set(list)
    if (next.has(id)) {
      next.delete(id)
    } else {
      next.add(id)
    }
    setList(next)
  }

  const handleGitHubSetup = async () => {
    if (!githubUrl.trim() || !githubAppId.trim()) {
      alert('Inserisci URL repository e GitHub App ID.')
      return
    }

    setLoading(true)
    try {
      // Extract owner/repo from URL
      const match = githubUrl.match(/github\.com\/([^\/]+)\/([^\/]+)/)
      if (!match) {
        alert('URL GitHub non valido. Usa il formato: https://github.com/owner/repo')
        setLoading(false)
        return
      }

      const [, owner, repo] = match

      // A GitHub App is not a user: it must be INSTALLED on the repo,
      // not invited as a collaborator. This endpoint verifies the install.
      const token = useStore.getState().token
      const res = await fetch('/api/github/setup', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({
          app_id: githubAppId.trim(),
          owner,
          repo,
        }),
      })
      const result = await res.json()
      if (result.success) {
        setInvited(true)
        setInviteUrl(null)
        alert(`✅ App installata e funzionante su ${owner}/${repo}`)
      } else {
        setInvited(false)
        alert(result.error || 'Verifica fallita.')
        // When not installed yet, show the one-click install link
        setInviteUrl(result.install_url || null)
      }
    } catch (err) {
      alert('Errore: ' + err)
    } finally {
      setLoading(false)
    }
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()

    const source = sourceType === 'github' ? githubUrl : file
    if (!source || !apiKey || !projectName) return

    setLoading(true)
    const formData = new FormData()
    formData.append('api_key', apiKey)
    formData.append('project_name', projectName)
    formData.append('optional_offices', [
      ...Array.from(selectedOptional),
      ...customOffices.split(',').map(s => s.trim()).filter(Boolean)
    ].join(','))

    try {
      const token = useStore.getState().token

      // Persist settings to the account so they're pre-filled next time
      if (token) {
        const settingsData = new FormData()
        if (apiKey) settingsData.append('opencode_api_key', apiKey)
        if (sourceType === 'github' && githubUrl) settingsData.append('github_repo_url', githubUrl)
        if (sourceType === 'github' && githubAppId) settingsData.append('github_app_id', githubAppId)
        settingsData.append('optional_offices', Array.from(selectedOptional).join(','))
        settingsData.append('custom_offices', customOffices)
        await fetch('/api/settings', {
          method: 'POST',
          body: settingsData,
          headers: { Authorization: `Bearer ${token}` },
        }).catch(() => {}) // settings save must never block onboarding
      }

      // Send auth header with onboarding (endpoint is protected)
      if (sourceType === 'zip' && file) {
        formData.append('project_file', file)
      } else if (sourceType === 'github') {
        formData.append('github_url', githubUrl)
      }

      const res = await fetch('/api/onboard', {
        method: 'POST',
        body: formData,
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      })
      const data = await res.json()
      if (data.github_invite_url) {
        setGithubInviteUrl(data.github_invite_url)
      }
      if (data.error) {
        alert(`Onboarding: ${data.detail || data.error}`)
        return
      }
      setShowOnboarding(false)
    } catch (err) {
      alert('Onboarding failed: ' + err)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div style={{
      position: 'absolute', inset: 0, background: 'rgba(0,0,0,0.8)',
      display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 100,
      overflowY: 'auto',
    }}>
      <div style={{
        background: '#1e293b', padding: 32, borderRadius: 12, width: 640,
        maxWidth: '95vw', maxHeight: '90vh', overflowY: 'auto',
        border: '1px solid #334155',
      }}>
        <h2 style={{ marginBottom: 20, color: '#e2e8f0' }}>🏢 Setup Azienda Virtuale</h2>

        <form onSubmit={handleSubmit}>
          {/* Source Type Selector */}
          <div style={{ marginBottom: 16 }}>
            <label style={{ display: 'block', marginBottom: 8, fontSize: 12, color: '#94a3b8', fontWeight: 'bold' }}>
              Sorgente Progetto
            </label>
            <div style={{ display: 'flex', gap: 8 }}>
              <button
                type="button"
                onClick={() => setSourceType('github')}
                style={{
                  flex: 1, padding: 10, borderRadius: 6, border: '1px solid #334155',
                  background: sourceType === 'github' ? '#3b82f6' : '#0f172a',
                  color: '#fff', cursor: 'pointer', fontSize: 13,
                }}
              >
                🐙 GitHub Repository
              </button>
              <button
                type="button"
                onClick={() => setSourceType('zip')}
                style={{
                  flex: 1, padding: 10, borderRadius: 6, border: '1px solid #334155',
                  background: sourceType === 'zip' ? '#3b82f6' : '#0f172a',
                  color: '#fff', cursor: 'pointer', fontSize: 13,
                }}
              >
                📦 Upload ZIP
              </button>
            </div>
          </div>

          {/* GitHub Repo Input */}
          {sourceType === 'github' && (
            <div style={{ marginBottom: 16, padding: 16, background: '#0f172a', borderRadius: 8, border: '1px solid #334155' }}>
              <div style={{ marginBottom: 8 }}>
                <label style={{ display: 'block', marginBottom: 4, fontSize: 12, color: '#94a3b8' }}>
                  GitHub Repository URL
                </label>
                <input
                  type="text" value={githubUrl} onChange={(e) => setGithubUrl(e.target.value)}
                  style={{ width: '100%', padding: 8, background: '#1e293b', border: '1px solid #334155', borderRadius: 4, color: '#e2e8f0' }}
                  placeholder="https://github.com/username/repository"
                />
              </div>
              <div style={{ marginBottom: 8 }}>
                <label style={{ display: 'block', marginBottom: 4, fontSize: 12, color: '#94a3b8' }}>
                  GitHub App ID
                </label>
                <input
                  type="text" value={githubAppId} onChange={(e) => setGithubAppId(e.target.value)}
                  style={{ width: '100%', padding: 8, background: '#1e293b', border: '1px solid #334155', borderRadius: 4, color: '#e2e8f0' }}
                  placeholder="123456"
                />
              </div>
              <div style={{ marginBottom: 8 }}>
                <label style={{ display: 'block', marginBottom: 4, fontSize: 12, color: '#94a3b8' }}>
                  GitHub App Private Key (.pem) — caricata sul server, non viene salvata nel browser
                </label>
                <input
                  type="file" accept=".pem,.key" onChange={handlePrivateKeyUpload}
                  style={{ width: '100%', color: '#94a3b8', fontSize: 12 }}
                />
                {keyStatus && (
                  <div style={{
                    marginTop: 4, fontSize: 11,
                    color: keyStatus.ok ? '#4ade80' : '#f87171',
                  }}>
                    {keyStatus.message}
                  </div>
                )}
              </div>
              <button
                type="button" onClick={handleGitHubSetup} disabled={loading || !githubUrl.trim() || !githubAppId.trim()}
                style={{
                  width: '100%', padding: 8, background: '#238636', border: 'none',
                  borderRadius: 4, color: '#fff', cursor: 'pointer', fontSize: 12,
                  marginBottom: 8,
                }}
              >
                {loading ? 'Verifica in corso...' : '🔗 Verifica installazione GitHub App'}
              </button>
              {inviteUrl && (
                <div style={{ padding: 8, background: '#1a365d', borderRadius: 4, fontSize: 11 }}>
                  <div style={{ color: '#94a3b8', marginBottom: 4 }}>
                    {invited ? '✅ App installata e funzionante' : '⚠️ Installa la GitHub App sulla repository (un click):'}
                  </div>
                  <a href={inviteUrl} target="_blank" rel="noopener noreferrer" style={{ color: '#60a5fa' }}>
                    {inviteUrl}
                  </a>
                </div>
              )}
            </div>
          )}

          {/* ZIP Upload */}
          {sourceType === 'zip' && (
            <div style={{ marginBottom: 16 }}>
              <label style={{ display: 'block', marginBottom: 4, fontSize: 12, color: '#94a3b8' }}>Project File (.zip)</label>
              <input
                type="file" accept=".zip" onChange={(e) => setFile(e.target.files?.[0] || null)}
                style={{ width: '100%', color: '#94a3b8' }}
              />
            </div>
          )}

          {/* Project Name + API Key */}
          <div style={{ display: 'flex', gap: 12, marginBottom: 16 }}>
            <div style={{ flex: 1 }}>
              <label style={{ display: 'block', marginBottom: 4, fontSize: 12, color: '#94a3b8' }}>Nome Progetto</label>
              <input
                type="text" value={projectName} onChange={(e) => setProjectName(e.target.value)}
                style={{ width: '100%', padding: 8, background: '#0f172a', border: '1px solid #334155', borderRadius: 4, color: '#e2e8f0' }}
                placeholder="my-project"
              />
            </div>
            <div style={{ flex: 1 }}>
              <label style={{ display: 'block', marginBottom: 4, fontSize: 12, color: '#94a3b8' }}>API Key (Opencode Zen)</label>
              <input
                type="password" value={apiKey} onChange={(e) => setApiKey(e.target.value)}
                style={{ width: '100%', padding: 8, background: '#0f172a', border: '1px solid #334155', borderRadius: 4, color: '#e2e8f0' }}
                placeholder="sk-or-..."
              />
            </div>
          </div>

          {/* Default Offices */}
          <div style={{ marginBottom: 16 }}>
            <label style={{ display: 'block', marginBottom: 8, fontSize: 12, color: '#94a3b8', fontWeight: 'bold' }}>
              Uffici Default
            </label>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 6 }}>
              {DEFAULT_OFFICES.map((office) => (
                <label
                  key={office.id}
                  style={{
                    display: 'flex', alignItems: 'center', gap: 8, padding: 8,
                    background: selectedDefault.has(office.id) ? '#1a365d' : '#0f172a',
                    borderRadius: 6, cursor: 'pointer', fontSize: 12,
                    border: selectedDefault.has(office.id) ? '1px solid #3b82f6' : '1px solid #334155',
                  }}
                >
                  <input
                    type="checkbox" checked={selectedDefault.has(office.id)}
                    onChange={() => toggleOffice(office.id, selectedDefault, setSelectedDefault)}
                    style={{ cursor: 'pointer' }}
                  />
                  <div>
                    <div style={{ color: '#e2e8f0' }}>{office.icon} {office.name}</div>
                    <div style={{ color: '#64748b', fontSize: 10 }}>{office.desc}</div>
                  </div>
                </label>
              ))}
            </div>
          </div>

          {/* Optional Offices */}
          <div style={{ marginBottom: 16 }}>
            <label style={{ display: 'block', marginBottom: 8, fontSize: 12, color: '#94a3b8', fontWeight: 'bold' }}>
              Uffici Opzionali
            </label>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 6 }}>
              {OPTIONAL_OFFICES.map((office) => (
                <label
                  key={office.id}
                  style={{
                    display: 'flex', alignItems: 'center', gap: 8, padding: 8,
                    background: selectedOptional.has(office.id) ? '#1a365d' : '#0f172a',
                    borderRadius: 6, cursor: 'pointer', fontSize: 12,
                    border: selectedOptional.has(office.id) ? '1px solid #3b82f6' : '1px solid #334155',
                  }}
                >
                  <input
                    type="checkbox" checked={selectedOptional.has(office.id)}
                    onChange={() => toggleOffice(office.id, selectedOptional, setSelectedOptional)}
                    style={{ cursor: 'pointer' }}
                  />
                  <div>
                    <div style={{ color: '#e2e8f0' }}>{office.icon} {office.name}</div>
                    <div style={{ color: '#64748b', fontSize: 10 }}>{office.desc}</div>
                  </div>
                </label>
              ))}
            </div>
          </div>

          {/* Custom Offices */}
          <div style={{ marginBottom: 16 }}>
            <label style={{ display: 'block', marginBottom: 4, fontSize: 12, color: '#94a3b8' }}>
              Uffici Custom (comma-separated)
            </label>
            <input
              type="text" value={customOffices} onChange={(e) => setCustomOffices(e.target.value)}
              style={{ width: '100%', padding: 8, background: '#0f172a', border: '1px solid #334155', borderRadius: 4, color: '#e2e8f0' }}
              placeholder="Mobile, Data Science, AI Research"
            />
          </div>

          {/* Auto-creation notice */}
          <div style={{ padding: 8, background: '#1a365d', borderRadius: 4, fontSize: 11, color: '#94a3b8', marginBottom: 16 }}>
            ℹ️ Durante l'analisi del progetto, il sistema può creare automaticamente ulteriori uffici se rileva componenti non coperte (es: cartella "mobile" → Ufficio Mobile).
          </div>

          <button
            type="submit" disabled={loading}
            style={{
              width: '100%', padding: 12, background: '#3b82f6', border: 'none',
              borderRadius: 6, color: '#fff', fontWeight: 'bold', cursor: loading ? 'not-allowed' : 'pointer',
              opacity: loading ? 0.6 : 1, fontSize: 14,
            }}
          >
            {loading ? 'Creazione in corso...' : '🚀 Crea Azienda Virtuale'}
          </button>
        </form>
      </div>
    </div>
  )
}

function AgentModal() {
  const { showAgentModal, setShowAgentModal, selectedAgent, agentChatLog, agentTaskQueue } = useStore()
  if (!showAgentModal || !selectedAgent) return null

  return (
    <div style={{
      position: 'absolute', top: 0, right: 0, width: 350, height: '100%',
      background: '#1e293b', borderLeft: '1px solid #334155', padding: 20,
      overflowY: 'auto', zIndex: 50,
    }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
        <h3 style={{ color: '#e2e8f0', margin: 0 }}>{selectedAgent.name}</h3>
        <button onClick={() => setShowAgentModal(false)} style={{ background: 'none', border: 'none', color: '#94a3b8', fontSize: 20, cursor: 'pointer' }}>×</button>
      </div>

      <div style={{ marginBottom: 16 }}>
        <div style={{ fontSize: 11, color: '#64748b', marginBottom: 4 }}>Role</div>
        <div style={{ color: '#e2e8f0', textTransform: 'capitalize' }}>{selectedAgent.role}</div>
      </div>

      {selectedAgent.office_name && (
        <div style={{ marginBottom: 16 }}>
          <div style={{ fontSize: 11, color: '#64748b', marginBottom: 4 }}>Office</div>
          <div style={{ color: '#e2e8f0' }}>{selectedAgent.office_name}</div>
        </div>
      )}

      {selectedAgent.specialization && (
        <div style={{ marginBottom: 16 }}>
          <div style={{ fontSize: 11, color: '#64748b', marginBottom: 4 }}>Specialization</div>
          <div style={{ color: '#e2e8f0' }}>{selectedAgent.specialization}</div>
        </div>
      )}

      <div style={{ marginBottom: 16 }}>
        <div style={{ fontSize: 11, color: '#64748b', marginBottom: 4 }}>Status</div>
        <div style={{ color: '#e2e8f0' }}>{STATUS_LABELS[selectedAgent.status] || selectedAgent.status}</div>
      </div>

      <div style={{ marginBottom: 16 }}>
        <div style={{ fontSize: 11, color: '#64748b', marginBottom: 4 }}>Thoughts</div>
        <div style={{ color: '#cbd5e1', fontStyle: 'italic' }}>{selectedAgent.thoughts || 'No thoughts yet...'}</div>
      </div>

      <div style={{ marginBottom: 16 }}>
        <div style={{ fontSize: 11, color: '#64748b', marginBottom: 4 }}>Performance</div>
        <div style={{ color: '#e2e8f0', fontSize: 12 }}>
          <div>Tasks Completed: {selectedAgent.performance?.tasks_completed || 0}</div>
          <div>Tasks Failed: {selectedAgent.performance?.tasks_failed || 0}</div>
          <div>Messages: {selectedAgent.performance?.total_messages || 0}</div>
        </div>
      </div>

      {agentTaskQueue.length > 0 && (
        <div style={{ marginBottom: 16 }}>
          <div style={{ fontSize: 11, color: '#64748b', marginBottom: 4 }}>Task Queue ({agentTaskQueue.length})</div>
          {agentTaskQueue.map((task, i) => (
            <div key={i} style={{ background: '#0f172a', padding: 8, borderRadius: 4, marginBottom: 4, fontSize: 11, color: '#cbd5e1' }}>
              {task.description}
            </div>
          ))}
        </div>
      )}

      {agentChatLog.length > 0 && (
        <div>
          <div style={{ fontSize: 11, color: '#64748b', marginBottom: 4 }}>Chat Log</div>
          {agentChatLog.slice(-10).map((entry, i) => (
            <div key={i} style={{ background: '#0f172a', padding: 8, borderRadius: 4, marginBottom: 4, fontSize: 11 }}>
              <div style={{ color: '#64748b', fontSize: 10 }}>{entry.from ? `From: ${entry.from}` : `To: ${entry.to}`}</div>
              <div style={{ color: '#cbd5e1' }}>{entry.message}</div>
              {entry.response && <div style={{ color: '#81c784', marginTop: 4 }}>↳ {entry.response}</div>}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

function MessageInput() {
  const [message, setMessage] = useState('')
  const { companyState } = useStore()

  if (!companyState) return null

  const handleSend = async () => {
    if (!message.trim()) return
    const token = useStore.getState().token
    const formData = new FormData()
    formData.append('message', message)
    await fetch('/api/message', {
      method: 'POST',
      body: formData,
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    })
    setMessage('')
  }

  return (
    <div style={{
      position: 'absolute', bottom: 20, left: '50%', transform: 'translateX(-50%)',
      display: 'flex', gap: 8, width: 500, zIndex: 40,
    }}>
      <input
        type="text" value={message} onChange={(e) => setMessage(e.target.value)}
        onKeyDown={(e) => e.key === 'Enter' && handleSend()}
        placeholder="Send a message to the CEO..."
        style={{
          flex: 1, padding: 12, background: 'rgba(30,41,59,0.9)', border: '1px solid #334155',
          borderRadius: 8, color: '#e2e8f0', fontSize: 14,
        }}
      />
      <button
        onClick={handleSend}
        style={{
          padding: '12px 20px', background: '#3b82f6', border: 'none',
          borderRadius: 8, color: '#fff', fontWeight: 'bold', cursor: 'pointer',
        }}
      >
        Send
      </button>
    </div>
  )
}

function useWebSocket() {
  const { setWs, setConnected, setCompanyState, token } = useStore()

  useEffect(() => {
    if (!token) return

    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const ws = new WebSocket(`${protocol}//${window.location.host}/ws?token=${token}`)

    ws.onopen = () => {
      setConnected(true)
      setWs(ws)
    }

    ws.onclose = () => {
      setConnected(false)
      setWs(null)
      // Reconnect after 5 seconds without reloading the page
      setTimeout(() => {
        const currentToken = useStore.getState().token
        if (currentToken) {
          useWebSocket()
        }
      }, 5000)
    }

    ws.onerror = () => {
      setConnected(false)
    }

    return () => ws.close()
  }, [token])
}

function AppWithWebSocket() {
  useWebSocket()
  return <App />
}

export default AppWithWebSocket
