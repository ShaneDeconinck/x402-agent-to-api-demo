# x402 + Stablecoins: Agent-Accessible Data Assets

A proof of concept exploring how incumbents can monetize data assets in an agent economy.

**Demo video:** https://www.youtube.com/watch?v=wNHUrroN_Hk

## The Gap

**Current Reality:**
- APIs require accounts, API keys, billing systems
- Works for human-driven integrations
- Breaks for autonomous agents that need to discover and transact independently
- Agents can't sign up for services, manage invoices, or handle billing disputes

**What's Missing:**
A protocol for agents to autonomously pay for API access without human intervention.

## The Solution

**HTTP 402 (Payment Required)** has existed since 1997 but never had a payment layer that worked.

**Stablecoins + EIP-3009** provide that layer:
- Predictable costs (cents per query, not volatile crypto)
- **Gasless for agents** - Sign authorization, server settles
- Instant settlement (no invoicing)
- Cryptographic proof (no disputes)
- **Built-in replay protection** - Contract-level nonce tracking
- Works globally without intermediaries

## The Model

Real estate websites already expose data publicly. Scrapers take it for free.

**x402 doesn't make data more protected - it makes access monetized.**

### Two-Tier API

1. **Tier 1: Listings** ($0.01/query)
   - Query listings by neighborhood
   - Returns structured JSON

2. **Tier 2: AI Valuation** ($0.10/query)
   - Proprietary pricing model
   - Returns valuation + assessment

### The Vision

- **Incumbents** expose data via x402 APIs (Tier 1 & 2)
- **AI companies** build agent experiences (discovery, conversation, UX)
- **Agents** autonomously discover, pay, and consume
- **Multiple AI companies** can compete using the same backend

Incumbents don't become AI companies. They monetize what they already have.

## Architecture

```
┌─────────────────┐
│  Agent (Claude) │
│  Signs EIP-712  │
│  (no gas!)      │
└────────┬────────┘
         │
         │ 1. GET /listings → 402 Payment Required
         │ 2. Agent signs TransferWithAuthorization
         │ 3. GET /listings + X-PAYMENT header
         ▼
┌─────────────────┐
│   FastAPI with  │
│ x402 + EIP-3009 │
├─────────────────┤
│  Verifies sig   │
│  Calls USDC     │
│  transferWith-  │
│  Authorization  │
│  (server pays   │
│   gas)          │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│   USDC Contract │
│   (Base Sepolia)│
│  Checks nonce,  │
│  transfers USDC │
└─────────────────┘
```

### EIP-3009 Flow

1. **Agent signs** EIP-712 `TransferWithAuthorization` message (gasless)
2. **Server receives** signature + authorization in `X-PAYMENT` header
3. **Server calls** `USDC.transferWithAuthorization()` (pays gas)
4. **Contract verifies** signature, checks nonce not used, transfers USDC
5. **Server returns** data

## Tech Stack

- **API:** FastAPI (Python)
- **Database:** SQLite with mock listings
- **Algorithm:** Simple but realistic valuation model
- **Payment:** USDC on Base Sepolia via EIP-3009
- **Signing:** EIP-712 (eth_account)
- **Agent:** Anthropic SDK (gasless - only signs)
- **Frontend:** Tailwind CSS demo interface

## Trade-offs

**Scrape-resistant, not scrape-proof:**
- Extraction is economically unfavorable, not impossible
- Pay-per-query makes bulk extraction expensive
- The bet: Value of agent accessibility > cost of extraction

**Gas fees paid by server:**
- Server pays ~$0.007/transaction to settle
- Agent pays $0 gas (only signs)
- Server must price queries to cover gas overhead
- At $0.01/query: 70% gas overhead
- At $0.10/query: 7% gas overhead

**Replay protection built-in:**
- EIP-3009 nonce tracked by USDC contract
- Each authorization can only be used once
- No server-side tracking needed

**Real estate sites already expose data publicly.** This model monetizes access instead of fighting it.

## What This Demonstrates

1. **x402 + EIP-3009** for gasless agent payments
2. **Stablecoins** as enterprise-friendly settlement layer
3. **Contract-level nonce** for replay protection
4. **Tiered monetization** of existing data assets
5. **Server-side settlement** - agents don't need ETH for gas

## Getting Started

### Prerequisites

- Python 3.11+
- Two MetaMask wallets (agent + recipient)
- Testnet USDC on Base Sepolia (for agent wallet)
- Testnet ETH on Base Sepolia (for recipient wallet, to pay gas)

### Setup

```bash
# Clone the repo
git clone https://github.com/ShaneDeconinck/x402-agent-to-api-demo.git
cd x402-agent-to-api-demo

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Copy environment template
cp .env.example .env
```

### Configure .env

Edit `.env` with your keys:

```bash
# Anthropic API key (for the agent)
ANTHROPIC_API_KEY=your_key

# Agent wallet (pays for API access)
AGENT_PRIVATE_KEY=64_hex_chars_no_0x

# Recipient wallet (receives payments, settles on-chain)
RECIPIENT_ADDRESS=0x...
RECIPIENT_PRIVATE_KEY=64_hex_chars_no_0x

# Optional: Alchemy RPC for faster indexing
BASE_SEPOLIA_RPC=https://base-sepolia.g.alchemy.com/v2/YOUR_KEY
```

### Run

```bash
# Activate venv (if not already active)
source venv/bin/activate

# Start API + frontend
./start.sh
```

Opens http://localhost:3000 with the demo UI.

- **Frontend:** http://localhost:3000
- **API:** http://localhost:8888
- **API Docs:** http://localhost:8888/docs

### Get Testnet Tokens

1. **Base Sepolia ETH:** https://www.alchemy.com/faucets/base-sepolia
2. **Base Sepolia USDC:** https://faucet.circle.com/

## Status

🚧 Proof of concept - exploring "a vision" for agent-accessible economies
