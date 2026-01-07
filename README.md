# x402 + Stablecoins: Agent-Accessible Data Assets

A proof of concept exploring how incumbents can monetize data assets in an agent economy.

**Demo video:** https://www.youtube.com/watch?v=ocYXPjUdFXg

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

**Stablecoins** provide that layer:
- Predictable costs (cents per query, not volatile crypto)
- Instant settlement (no invoicing)
- Cryptographic proof (no disputes)
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
│  via Anthropic  │
│      SDK        │
└────────┬────────┘
         │
         │ 1. Discovers service
         │    via Registry
         ▼
┌─────────────────┐
│    Registry     │
│   (Base L2)     │
│  Smart Contract │
└────────┬────────┘
         │
         │ 2. Queries API
         │    with x402 header
         ▼
┌─────────────────┐
│   FastAPI with  │
│ x402 Verification│
├─────────────────┤
│  Tier 1: Query  │
│  Tier 2: Value  │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  SQLite + Algo  │
│ (Proprietary IP)│
└─────────────────┘
```

## Tech Stack

- **API:** FastAPI (Python)
- **Database:** SQLite with mock listings
- **Algorithm:** Simple but realistic valuation model
- **Payment:** USDC on Base testnet
- **Registry:** Solidity smart contract
- **Agent:** Anthropic SDK
- **Frontend:** Simple demo interface

## Trade-offs

**Scrape-resistant, not scrape-proof:**
- Extraction is economically unfavorable, not impossible
- Pay-per-query makes bulk extraction expensive
- The bet: Value of agent accessibility > cost of extraction

**Gas fees are the constraint:**
- Base gas: ~$0.007/transaction
- Minimum viable pricing: $0.01/query
- Solutions: Batching, higher tiers, or gas sponsorship (at cost of platform lock-in)

**Real estate sites already expose data publicly.** This model monetizes access instead of fighting it.

## What This Demonstrates

1. **x402 as a protocol** for agent payments
2. **Stablecoins** as enterprise-friendly settlement layer
3. **Registry pattern** for service discovery
4. **Tiered monetization** of existing data assets
5. **Clear separation** between data providers (incumbents) and experience builders (AI companies)

## Status

🚧 Proof of concept - exploring "a vision" for agent-accessible economies
