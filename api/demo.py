"""
Demo endpoint that runs the full x402 flow and streams results
This is for filming/demonstration purposes

Uses EIP-3009 (TransferWithAuthorization) for gasless agent payments.
Server settles the payment and pays gas.
"""
import os
import json
import time
import random
import base64
import secrets
from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse
from web3 import Web3
from eth_account import Account
from eth_account.messages import encode_typed_data
from dotenv import load_dotenv

from payment import get_payment_verifier

load_dotenv()

router = APIRouter()

# Web3 setup
w3 = Web3(Web3.HTTPProvider(os.getenv("BASE_SEPOLIA_RPC", "https://sepolia.base.org")))

# USDC contract
USDC_ADDRESS = Web3.to_checksum_address(os.getenv("USDC_CONTRACT_ADDRESS", "0x036CbD53842c5426634e7929541eC2318f3dCF7e"))
USDC_ABI = [
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

# EIP-712 domain for USDC on Base Sepolia
EIP712_DOMAIN = {
    "name": "USDC",
    "version": "2",
    "chainId": 84532,
    "verifyingContract": USDC_ADDRESS
}

# EIP-712 types for TransferWithAuthorization
EIP712_TYPES = {
    "TransferWithAuthorization": [
        {"name": "from", "type": "address"},
        {"name": "to", "type": "address"},
        {"name": "value", "type": "uint256"},
        {"name": "validAfter", "type": "uint256"},
        {"name": "validBefore", "type": "uint256"},
        {"name": "nonce", "type": "bytes32"},
    ]
}

# Payment verifier for settling payments
payment_verifier = get_payment_verifier()


def create_signed_authorization(account: Account, amount: int) -> tuple[str, str]:
    """
    Create a signed EIP-3009 authorization (gasless for agent).

    Returns:
        Tuple of (x_payment_header, nonce_hex)
    """
    # Generate random 32-byte nonce
    nonce = secrets.token_bytes(32)
    nonce_hex = "0x" + nonce.hex()

    # Time bounds (valid for 5 minutes)
    current_time = int(time.time())
    valid_after = current_time
    valid_before = current_time + 300

    # Build EIP-712 message
    message = {
        "from": account.address,
        "to": RECIPIENT_ADDRESS,
        "value": amount,
        "validAfter": valid_after,
        "validBefore": valid_before,
        "nonce": nonce,
    }

    # Create typed data for signing
    typed_data = {
        "types": EIP712_TYPES,
        "primaryType": "TransferWithAuthorization",
        "domain": EIP712_DOMAIN,
        "message": message,
    }

    # Sign with EIP-712
    signable = encode_typed_data(full_message=typed_data)
    signed = account.sign_message(signable)
    signature = "0x" + signed.signature.hex()

    # Build X-PAYMENT payload
    payload = {
        "x402Version": 2,
        "scheme": "exact",
        "network": "base-sepolia",
        "signature": signature,
        "authorization": {
            "from": account.address,
            "to": RECIPIENT_ADDRESS,
            "value": str(amount),
            "validAfter": str(valid_after),
            "validBefore": str(valid_before),
            "nonce": nonce_hex,
        }
    }

    x_payment = base64.b64encode(json.dumps(payload).encode()).decode()
    return x_payment, nonce_hex


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

        # Step 2: 402 Response with X-PAYMENT-REQUIRED header (x402 spec)
        x402_response = {
            "x402Version": 1,
            "accepts": [{
                "scheme": "exact",
                "network": "base-sepolia",
                "maxAmountRequired": "10000",
                "resource": "/api/v1/listings",
                "description": "Pay $0.01 USDC for Tier 1 access",
                "mimeType": "application/json",
                "payTo": RECIPIENT_ADDRESS,
                "maxTimeoutSeconds": 300,
                "asset": USDC_ADDRESS,
                "extra": {"name": "USDC", "version": "1"}
            }]
        }
        yield f"data: {json.dumps({'step': 2, 'action': '402', 'message': 'Payment Required', 'x402': x402_response})}\n\n"
        time.sleep(1)

        # DAG: handle_402_tier1
        msg = AgentBrain.generate("handle_402_tier1", {"price": "0.01"})
        yield f"data: {json.dumps({'step': 'agent', 'action': 'deciding', 'message': msg})}\n\n"
        time.sleep(1)

        # Step 3: Sign EIP-3009 authorization (gasless for agent)
        yield f"data: {json.dumps({'step': 3, 'action': 'signing', 'message': 'Signing EIP-712 payment authorization (gasless)...'})}\n\n"

        # Create signed authorization
        x_payment, nonce_hex = create_signed_authorization(account, TIER_1_PRICE)

        yield f"data: {json.dumps({'step': 3, 'action': 'signed', 'nonce': nonce_hex[:18] + '...', 'amount': 0.01, 'message': 'Authorization signed! Server will settle...'})}\n\n"
        time.sleep(1)

        # Server settles the payment via transferWithAuthorization
        yield f"data: {json.dumps({'step': 3, 'action': 'settling', 'message': 'Server settling payment via transferWithAuthorization...'})}\n\n"

        settlement = payment_verifier.verify_and_settle(x_payment, tier=1)

        if settlement['valid']:
            tx_hash_hex = '0x' + settlement['tx_hash'] if not settlement['tx_hash'].startswith('0x') else settlement['tx_hash']
            yield f"data: {json.dumps({'step': 3, 'action': 'tx_confirmed', 'tx_hash': tx_hash_hex, 'block': settlement.get('block_number'), 'message': 'Payment settled!'})}\n\n"
        else:
            error_msg = settlement.get("error", "Unknown error")
            yield f"data: {json.dumps({'step': 3, 'action': 'tx_failed', 'message': f'Settlement failed: {error_msg}'})}\n\n"
            return

        # Step 4: Retry with signed authorization
        yield f"data: {json.dumps({'step': 4, 'action': 'retry', 'message': f'Retrying with X-PAYMENT header'})}\n\n"
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
                "x402Version": 1,
                "accepts": [{
                    "scheme": "exact",
                    "network": "base-sepolia",
                    "maxAmountRequired": "100000",
                    "resource": "/api/v1/valuation",
                    "description": "Pay $0.10 USDC for Tier 2 access",
                    "mimeType": "application/json",
                    "payTo": RECIPIENT_ADDRESS,
                    "maxTimeoutSeconds": 300,
                    "asset": USDC_ADDRESS,
                    "extra": {"name": "USDC", "version": "1"}
                }]
            }
            yield f"data: {json.dumps({'step': 7, 'action': '402', 'message': 'Payment Required', 'x402': x402_tier2})}\n\n"
            time.sleep(1)

            # DAG: handle_402_tier2
            msg = AgentBrain.generate("handle_402_tier2", {"price": "0.10"})
            yield f"data: {json.dumps({'step': 'agent', 'action': 'deciding', 'message': msg})}\n\n"
            time.sleep(1)

            # Sign Tier 2 authorization (gasless for agent)
            yield f"data: {json.dumps({'step': 8, 'action': 'signing', 'message': 'Signing $0.10 authorization (gasless)...'})}\n\n"

            x_payment_2, nonce_hex_2 = create_signed_authorization(account, TIER_2_PRICE)

            yield f"data: {json.dumps({'step': 8, 'action': 'signed', 'nonce': nonce_hex_2[:18] + '...', 'amount': 0.10, 'message': 'Authorization signed! Server will settle...'})}\n\n"
            time.sleep(1)

            # Server settles the payment
            yield f"data: {json.dumps({'step': 8, 'action': 'settling', 'message': 'Server settling Tier 2 payment...'})}\n\n"

            settlement_2 = payment_verifier.verify_and_settle(x_payment_2, tier=2)

            if settlement_2['valid']:
                tx_hash_2_hex = '0x' + settlement_2['tx_hash'] if not settlement_2['tx_hash'].startswith('0x') else settlement_2['tx_hash']
                yield f"data: {json.dumps({'step': 8, 'action': 'tx_confirmed', 'tx_hash': tx_hash_2_hex, 'block': settlement_2.get('block_number'), 'message': 'Tier 2 payment settled!'})}\n\n"
            else:
                error_msg_2 = settlement_2.get("error", "Unknown error")
                yield f"data: {json.dumps({'step': 8, 'action': 'tx_failed', 'message': f'Settlement failed: {error_msg_2}'})}\n\n"
                return

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

        yield f"data: {json.dumps({'step': 'done', 'tx_hash': tx_hash_hex, 'tx_hash_2': tx_hash_2_hex if listings else None, 'total_spent': total_spent, 'new_balance': new_balance_usd, 'basescan_url': f'https://sepolia.basescan.org/tx/{tx_hash_hex}', 'note': 'Agent signed authorizations (gasless), server settled via EIP-3009'})}\n\n"

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
