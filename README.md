# AI Virtual Company Simulator

Piattaforma web-based per la simulazione di un'azienda virtuale multi-agente. Il sistema analizza un progetto software, crea una struttura aziendale con uffici, manager e agenti specializzati, e visualizza la comunicazione tra agenti in una vista 2D interattiva.

## Architettura

```
┌─────────────────────────────────────────────────────────────┐
│                     Frontend (React + PixiJS)                │
│  ┌─────────────┐  ┌──────────────┐  ┌───────────────────┐  │
│  │ Office View │  │ Agent Modal  │  │ Onboarding Form   │  │
│  │ (2D Sims)   │  │ (Details)    │  │ (Project Upload)  │  │
│  └─────────────┘  └──────────────┘  └───────────────────┘  │
└──────────────────────────┬──────────────────────────────────┘
                           │ WebSocket + REST API
┌──────────────────────────▼──────────────────────────────────┐
│                  Backend (FastAPI + Uvicorn)                 │
│  ┌────────────┐  ┌────────────┐  ┌────────────────────┐    │
│  │ Web Server │  │ Event Bus  │  │ Company Engine     │    │
│  │ (REST+WS)  │  │ (Async)    │  │ (Orchestrator)     │    │
│  └────────────┘  └────────────┘  └────────────────────┘    │
│  ┌──────────────────────────────────────────────────────┐  │
│  │ Agent System                                         │  │
│  │  ┌─────┐  ┌─────────┐  ┌───────┐  ┌────────────┐   │  │
│  │  │ CEO │  │Managers │  │Workers│  │ Efficiency │   │  │
│  │  └─────┘  └─────────┘  └───────┘  └────────────┘   │  │
│  └──────────────────────────────────────────────────────┘  │
│  ┌──────────────────────────────────────────────────────┐  │
│  │ Memory System                                        │  │
│  │  ┌──────────────┐  ┌─────────────────────────────┐   │  │
│  │  │ Vector Store │  │ Graph Store                 │   │  │
│  │  │ (ChromaDB)   │  │ (Neo4j / In-Memory)         │   │  │
│  │  └──────────────┘  └─────────────────────────────┘   │  │
│  └──────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

## Tech Stack

| Componente | Tecnologia |
|------------|------------|
| Backend | Python 3.11+, FastAPI, Uvicorn |
| Frontend | React 18, PixiJS 7, Zustand, TypeScript |
| Real-time | WebSocket (FastAPI native) |
| Vector DB | ChromaDB (con fallback in-memory) |
| Graph DB | Neo4j (con fallback in-memory) |
| Event Bus | Async queue (con fallback Redis) |
| Deployment | Docker, Docker Compose, Cloudflare Tunnel |

## Avvio Rapido

### Prerequisiti

- Python 3.11+
- Node.js 18+
- (Opzionale) Neo4j per graph database persistente
- (Opzionale) Redis per event bus distribuito

### 1. Setup Backend

```bash
cd ai-company-simulator
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 2. Setup Frontend

```bash
cd frontend
npm install
npm run build
```

### 3. Avvio Server

```bash
cd ..
python main.py
```

Il server sarà disponibile su `http://localhost:8002` (la porta 8000 è occupata da un altro progetto su questo server)

### 4. Cloudflare Tunnel (per accesso remoto)

```bash
cloudflared tunnel --url http://localhost:8000
```

## API Endpoints

| Method | Endpoint | Descrizione |
|--------|----------|-------------|
| GET | `/` | Frontend (React app) |
| POST | `/api/onboard` | Onboard nuovo progetto |
| POST | `/api/message` | Invia messaggio al CEO |
| GET | `/api/state` | Stato azienda corrente |
| GET | `/api/agents/{id}` | Dettagli agente |
| GET | `/api/offices` | Lista uffici |
| GET | `/api/memory/search?q=` | Ricerca semantica |
| WS | `/ws` | WebSocket per eventi real-time |

## Funzionalità

### Sistema Agenti

- **CEO**: Punto di contatto unico con l'utente. Massima autonomia, scompone gli obiettivi e delega ai manager.
- **Office Managers**: Un ufficio per ogni componente del progetto. Ricevono istruzioni dal CEO, creano task per i worker.
- **Worker Agents**: Specializzati per aspetto del progetto (es. "Authentication Specialist"). Eseguono analisi, coding, testing.
- **Efficiency/HR**: Monitora performance, può licenziare agenti underperforming, riassegnare task, richiedere nuovi agenti.

### Cap Agenti

Limite hard-coded di **50 agenti attivi** per prevenire OOM. Quando il limite è raggiunto, l'Efficiency Office riassegna agenti esistenti invece di crearne di nuovi.

### Memoria

- **Vector Store**: ChromaDB per ricerca semantica sul codice
- **Graph Store**: Neo4j per mappare relazioni tra componenti e agenti
- **Fallback**: Se Neo4j/ChromaDB non disponibili, usa implementazioni in-memory

### Comunicazione Agenti

1. Agente A vuole comunicare con Agente B
2. Viene emesso evento `IntentToCommunicate(Source: A, Target: B, Message: X)`
3. Il frontend anima l'agente A che cammina verso la scrivania di B
4. Solo quando lo sprite arriva a destinazione, il messaggio viene processato da B

### Visualizzazione

- Vista 2D top-down dell'ufficio
- Agenti come sprite colorati per ruolo (CEO=oro, Manager=blu, Worker=verde, Efficiency=viola)
- Click su qualsiasi agente per aprire dettagli (pensieri, task queue, chat log)
- Animazioni di camminata con path curvi
- Bolle di messaggio durante la comunicazione

## Configurazione

Copia `.env.example` in `.env` e configura:

```env
OPENCODE_API_KEY=your-opencode-zen-key-here
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=password
MAX_AGENTS=50
```

## Docker

```bash
# Build e avvio
docker-compose up --build

# Oppure solo il backend (senza Neo4j/Redis)
docker build -t ai-company-sim .
docker run -p 8000:8000 -v $(pwd)/data:/app/data ai-company-sim
```

## Struttura Progetto

```
ai-company-simulator/
├── backend/
│   ├── core_engine/       # Orchestratore, analyzer, model selector
│   ├── agent_system/     # CEO, Manager, Worker, Efficiency agents
│   ├── memory_db/        # Vector store, graph store
│   ├── event_bus/        # Message broker async
│   └── web_server/       # FastAPI app + WebSocket
├── frontend/
│   └── src/
│       ├── components/   # React components
│       ├── game/         # PixiJS game engine
│       ├── store.ts      # Zustand state
│       └── App.tsx       # Main app
├── data/                 # Persistent data (uploads, chroma)
├── main.py               # Entry point
├── requirements.txt
├── Dockerfile
└── docker-compose.yml
```

## Licenza

MIT
