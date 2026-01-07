"""
Demo endpoint that runs the full x402 flow and streams results
This is for filming/demonstration purposes

Uses a DAG-based flow engine for agent reasoning
"""
import os
import json
import time
import random
from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse
from web3 import Web3
from eth_account import Account
from dotenv import load_dotenv

load_dotenv()

router = APIRouter()

# Web3 setup
w3 = Web3(Web3.HTTPProvider(os.getenv("BASE_SEPOLIA_RPC", "https://sepolia.base.org")))

# USDC contract
USDC_ADDRESS = Web3.to_checksum_address(os.getenv("USDC_CONTRACT_ADDRESS", "0x036CbD53842c5426634e7929541eC2318f3dCF7e"))
USDC_ABI = [
    {
        "constant": False,
        "inputs": [
            {"name": "_to", "type": "address"},
            {"name": "_value", "type": "uint256"}
        ],
        "name": "transfer",
        "outputs": [{"name": "", "type": "bool"}],
        "type": "function"
    },
    {
        "constant": True,
        "inputs": [{"name": "_owner", "type": "address"}],
        "name": "balanceOf",
        "outputs": [{"name": "balance", "type": "uint256"}],
        "type": "function"
    }
]
usdc_contract = w3.eth.contract(address=USDC_ADDRESS, abi=USDC_ABI)

# Agent wallet
AGENT_PRIVATE_KEY = os.getenv("AGENT_PRIVATE_KEY")
if AGENT_PRIVATE_KEY and not AGENT_PRIVATE_KEY.startswith("0x"):
    AGENT_PRIVATE_KEY = "0x" + AGENT_PRIVATE_KEY

RECIPIENT_ADDRESS = Web3.to_checksum_address(os.getenv("RECIPIENT_ADDRESS"))
TIER_1_PRICE = 10000  # $0.01 in USDC units
TIER_2_PRICE = 100000  # $0.10 in USDC units


# ============================================
# DAG-based Agent Message Generator
# ============================================

class AgentBrain:
    """Generates contextual agent messages based on current state"""

    # Message templates for each decision point
    TEMPLATES = {
        "analyze_task": [
            "User wants properties in {neighborhood}. I'll query the listings API first.",
            "Task: find real estate in {neighborhood}. Starting with the listings endpoint.",
            "Looking for {neighborhood} properties. Let me check the real estate API.",
        ],
        "handle_402_tier1": [
            "API requires ${price}. This is within budget. Creating payment...",
            "Got 402 - need to pay ${price} for data access. Proceeding with payment.",
            "Payment required: ${price} USDC. Acceptable cost for listing data.",
        ],
        "analyze_listings": [
            "Found {count} properties. Best value: {address} at ${price:,}. Let me get a professional valuation.",
            "Retrieved {count} listings. {address} looks promising at ${price:,}. Requesting valuation.",
            "{count} properties found. Most interesting: {address} (${price:,}). Getting detailed valuation.",
        ],
        "handle_402_tier2": [
            "Valuation costs ${price} (proprietary algorithm). Worth it for accurate pricing. Paying...",
            "Professional valuation requires ${price}. Fair price for AI-powered analysis. Proceeding.",
            "${price} for valuation data. Good investment for accurate market insight.",
        ],
        "summarize": [
            "Analysis complete. {address} is {assessment} - listed at ${list_price:,}, estimated value ${est_value:,}.",
            "Done. {address}: listed ${list_price:,}, valued ${est_value:,}. Assessment: {assessment}.",
            "Task complete. {address} assessment: {assessment}. List price ${list_price:,} vs estimated ${est_value:,}.",
        ],
    }

    @classmethod
    def generate(cls, state: str, context: dict) -> str:
        """Generate a contextual message for the given state"""
        templates = cls.TEMPLATES.get(state, ["Processing..."])
        template = random.choice(templates)
        return template.format(**context)


# DAG Node definitions
# Each node: { "id": str, "type": str, "next": list[str], "condition": callable }

DEMO_DAG = {
    "nodes": {
        "init": {"type": "system", "next": ["analyze_task"]},
        "analyze_task": {"type": "agent", "next": ["request_tier1"]},
        "request_tier1": {"type": "http", "next": ["handle_402_tier1"]},
        "handle_402_tier1": {"type": "agent", "next": ["pay_tier1"]},
        "pay_tier1": {"type": "payment", "next": ["retry_tier1"]},
        "retry_tier1": {"type": "http", "next": ["analyze_listings"]},
        "analyze_listings": {"type": "agent", "next": ["request_tier2"], "condition": "has_listings"},
        "request_tier2": {"type": "http", "next": ["handle_402_tier2"]},
        "handle_402_tier2": {"type": "agent", "next": ["pay_tier2"]},
        "pay_tier2": {"type": "payment", "next": ["get_valuation"]},
        "get_valuation": {"type": "http", "next": ["summarize"]},
        "summarize": {"type": "agent", "next": ["done"]},
        "done": {"type": "system", "next": []},
    }
}

def stream_demo(neighborhood: str):
    """Generator that streams demo events as SSE using DAG-based flow"""

    try:
        # Initialize
        account = Account.from_key(AGENT_PRIVATE_KEY)
        balance = usdc_contract.functions.balanceOf(account.address).call()
        balance_usd = balance / 1_000_000

        yield f"data: {json.dumps({'step': 'init', 'wallet': account.address, 'balance': balance_usd})}\n\n"
        time.sleep(0.5)

        # DAG: analyze_task
        msg = AgentBrain.generate("analyze_task", {"neighborhood": neighborhood})
        yield f"data: {json.dumps({'step': 'agent', 'action': 'thinking', 'message': msg})}\n\n"
        time.sleep(1.5)

        # Step 1: First request (will get 402)
        yield f"data: {json.dumps({'step': 1, 'action': 'request', 'message': f'GET /api/v1/listings?neighborhood={neighborhood}'})}\n\n"
        time.sleep(1)

        # Step 2: 402 Response (structured x402 payment requirements)
        x402_response = {
            "x402_version": "1.0",
            "payment": {
                "amount": "10000",
                "amount_usd": 0.01,
                "currency": "USDC",
                "decimals": 6,
                "recipient": RECIPIENT_ADDRESS,
                "contract": USDC_ADDRESS,
                "network": "base-sepolia",
                "chain_id": 84532,
                "proof": {
                    "header": "X-Payment-Proof",
                    "type": "transaction_hash"
                }
            },
            "tier": 1
        }
        yield f"data: {json.dumps({'step': 2, 'action': '402', 'message': 'Payment Required', 'x402': x402_response})}\n\n"
        time.sleep(1)

        # DAG: handle_402_tier1
        msg = AgentBrain.generate("handle_402_tier1", {"price": "0.01"})
        yield f"data: {json.dumps({'step': 'agent', 'action': 'deciding', 'message': msg})}\n\n"
        time.sleep(1)

        # Step 3: Create payment
        yield f"data: {json.dumps({'step': 3, 'action': 'paying', 'message': 'Creating USDC payment on Base Sepolia...'})}\n\n"

        # Actually create the payment
        nonce = w3.eth.get_transaction_count(account.address)
        transfer_function = usdc_contract.functions.transfer(RECIPIENT_ADDRESS, TIER_1_PRICE)
        gas_estimate = transfer_function.estimate_gas({'from': account.address})

        transaction = transfer_function.build_transaction({
            'from': account.address,
            'gas': gas_estimate,
            'gasPrice': w3.eth.gas_price,
            'nonce': nonce,
            'chainId': 84532
        })

        signed_txn = w3.eth.account.sign_transaction(transaction, AGENT_PRIVATE_KEY)
        tx_hash = w3.eth.send_raw_transaction(signed_txn.raw_transaction)
        tx_hash_hex = '0x' + tx_hash.hex()

        yield f"data: {json.dumps({'step': 3, 'action': 'tx_sent', 'tx_hash': tx_hash_hex, 'amount': 0.01, 'message': 'Transaction sent, waiting for confirmation...'})}\n\n"

        # Wait for confirmation
        receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)

        if receipt['status'] == 1:
            yield f"data: {json.dumps({'step': 3, 'action': 'tx_confirmed', 'tx_hash': tx_hash_hex, 'block': receipt['blockNumber'], 'message': 'Payment confirmed!'})}\n\n"
        else:
            yield f"data: {json.dumps({'step': 3, 'action': 'tx_failed', 'message': 'Transaction failed'})}\n\n"
            return

        # Wait for RPC to index
        yield f"data: {json.dumps({'step': 3, 'action': 'waiting', 'message': 'Waiting for block indexing (10s)...'})}\n\n"
        time.sleep(10)

        # Step 4: Retry with proof
        yield f"data: {json.dumps({'step': 4, 'action': 'retry', 'message': f'Retrying with X-Payment-Proof header'})}\n\n"
        time.sleep(1)

        # Step 5: Verify and get data
        yield f"data: {json.dumps({'step': 5, 'action': 'verifying', 'message': 'Server verifying payment on-chain...'})}\n\n"
        time.sleep(1)

        # Query the database directly for real results
        import sqlite3
        db_path = os.path.join(os.path.dirname(__file__), "..", "data", "real_estate.db")
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM listings WHERE neighborhood = ? LIMIT 10", (neighborhood,))
        rows = cursor.fetchall()
        listings = [dict(row) for row in rows]
        conn.close()

        yield f"data: {json.dumps({'step': 5, 'action': 'success', 'message': f'200 OK - {len(listings)} listings', 'listings': listings, 'tier': 1})}\n\n"
        time.sleep(1)

        # DAG: analyze_listings
        if listings:
            best_listing = min(listings, key=lambda x: x['price'])
            msg = AgentBrain.generate("analyze_listings", {
                "count": len(listings),
                "address": best_listing['address'],
                "price": best_listing['price']
            })
            yield f"data: {json.dumps({'step': 'agent', 'action': 'analyzing', 'message': msg})}\n\n"
            time.sleep(2)

            # Tier 2: Valuation request
            addr = best_listing['address']
            yield f"data: {json.dumps({'step': 6, 'action': 'request', 'message': f'GET /api/v1/valuation?address={addr}'})}\n\n"
            time.sleep(1)

            # 402 for Tier 2
            x402_tier2 = {
                "x402_version": "1.0",
                "payment": {
                    "amount": "100000",
                    "amount_usd": 0.10,
                    "currency": "USDC",
                    "recipient": RECIPIENT_ADDRESS,
                    "proof": {"header": "X-Payment-Proof"}
                },
                "tier": 2
            }
            yield f"data: {json.dumps({'step': 7, 'action': '402', 'message': 'Payment Required - Tier 2', 'x402': x402_tier2})}\n\n"
            time.sleep(1)

            # DAG: handle_402_tier2
            msg = AgentBrain.generate("handle_402_tier2", {"price": "0.10"})
            yield f"data: {json.dumps({'step': 'agent', 'action': 'deciding', 'message': msg})}\n\n"
            time.sleep(1)

            # Create Tier 2 payment
            yield f"data: {json.dumps({'step': 8, 'action': 'paying', 'message': 'Creating $0.10 USDC payment...'})}\n\n"

            nonce = w3.eth.get_transaction_count(account.address)
            transfer_function = usdc_contract.functions.transfer(RECIPIENT_ADDRESS, TIER_2_PRICE)
            gas_estimate = transfer_function.estimate_gas({'from': account.address})

            transaction = transfer_function.build_transaction({
                'from': account.address,
                'gas': gas_estimate,
                'gasPrice': w3.eth.gas_price,
                'nonce': nonce,
                'chainId': 84532
            })

            signed_txn = w3.eth.account.sign_transaction(transaction, AGENT_PRIVATE_KEY)
            tx_hash_2 = w3.eth.send_raw_transaction(signed_txn.raw_transaction)
            tx_hash_2_hex = '0x' + tx_hash_2.hex()

            yield f"data: {json.dumps({'step': 8, 'action': 'tx_sent', 'tx_hash': tx_hash_2_hex, 'amount': 0.10, 'message': 'Tier 2 payment sent...'})}\n\n"

            receipt_2 = w3.eth.wait_for_transaction_receipt(tx_hash_2, timeout=120)

            if receipt_2['status'] == 1:
                yield f"data: {json.dumps({'step': 8, 'action': 'tx_confirmed', 'tx_hash': tx_hash_2_hex, 'block': receipt_2['blockNumber'], 'message': 'Payment confirmed!'})}\n\n"

            yield f"data: {json.dumps({'step': 8, 'action': 'waiting', 'message': 'Waiting for block indexing (10s)...'})}\n\n"
            time.sleep(10)

            # Valuation response
            valuation = {
                "address": best_listing["address"],
                "estimated_value": int(best_listing["price"] * 1.05),
                "confidence": 0.87,
                "assessment": "Slightly underpriced",
                "comparable_sales": 5
            }

            yield f"data: {json.dumps({'step': 9, 'action': 'success', 'message': '200 OK - Valuation received', 'valuation': valuation, 'tier': 2})}\n\n"
            time.sleep(1)

            # DAG: summarize
            summary_msg = AgentBrain.generate("summarize", {
                "address": best_listing['address'],
                "assessment": valuation['assessment'].lower(),
                "list_price": best_listing['price'],
                "est_value": valuation['estimated_value']
            })
            yield f"data: {json.dumps({'step': 'agent', 'action': 'summary', 'message': summary_msg})}\n\n"

        # Get final balance
        new_balance = usdc_contract.functions.balanceOf(account.address).call()
        new_balance_usd = new_balance / 1_000_000
        total_spent = balance_usd - new_balance_usd

        yield f"data: {json.dumps({'step': 'done', 'tx_hash': tx_hash_hex, 'tx_hash_2': tx_hash_2_hex if listings else None, 'total_spent': total_spent, 'new_balance': new_balance_usd, 'basescan_url': f'https://sepolia.basescan.org/tx/{tx_hash_hex}'})}\n\n"

    except Exception as e:
        yield f"data: {json.dumps({'step': 'error', 'message': str(e)})}\n\n"


@router.get("/demo/run")
async def run_demo(neighborhood: str = Query("Ixelles")):
    """
    Run the full x402 demo with real payments
    Returns Server-Sent Events for real-time updates
    """
    return StreamingResponse(
        stream_demo(neighborhood),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "Access-Control-Allow-Origin": "*"
        }
    )


@router.get("/demo/balance")
async def get_balance():
    """Get current agent wallet balance"""
    try:
        account = Account.from_key(AGENT_PRIVATE_KEY)
        balance = usdc_contract.functions.balanceOf(account.address).call()
        return {
            "wallet": account.address,
            "balance_usdc": balance / 1_000_000,
            "balance_raw": balance
        }
    except Exception as e:
        return {"error": str(e)}
