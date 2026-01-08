"""
Real Estate Agent using Anthropic SDK

Demonstrates:
- Service discovery via registry
- Autonomous payment via x402 (EIP-3009 gasless)
- Tool use to query APIs
- Decision making based on data
"""
import os
import httpx
import json
import base64
import secrets
from anthropic import Anthropic
from typing import Dict, List
from web3 import Web3
from eth_account import Account
from eth_account.messages import encode_typed_data
import time
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Initialize Anthropic client
client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

# API endpoint
API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000")

# Web3 setup for Base Sepolia
w3 = Web3(Web3.HTTPProvider(os.getenv("BASE_SEPOLIA_RPC", "https://sepolia.base.org")))

# USDC contract on Base Sepolia
USDC_ADDRESS = Web3.to_checksum_address(os.getenv("USDC_CONTRACT_ADDRESS", "0x036CbD53842c5426634e7929541eC2318f3dCF7e"))

# ERC20 ABI (minimal - just balanceOf for checking balance)
USDC_ABI = [
    {
        "constant": True,
        "inputs": [{"name": "_owner", "type": "address"}],
        "name": "balanceOf",
        "outputs": [{"name": "balance", "type": "uint256"}],
        "type": "function"
    }
]

# Initialize USDC contract
usdc_contract = w3.eth.contract(address=USDC_ADDRESS, abi=USDC_ABI)

# Agent wallet (loads from .env)
AGENT_PRIVATE_KEY = os.getenv("AGENT_PRIVATE_KEY")
if AGENT_PRIVATE_KEY and not AGENT_PRIVATE_KEY.startswith("0x"):
    AGENT_PRIVATE_KEY = "0x" + AGENT_PRIVATE_KEY

# Recipient address (incumbent/API owner)
RECIPIENT_ADDRESS = Web3.to_checksum_address(os.getenv("RECIPIENT_ADDRESS"))

# Pricing (must match API)
TIER_1_PRICE = 10000   # $0.01 in USDC (6 decimals)
TIER_2_PRICE = 100000  # $0.10 in USDC

# EIP-712 domain for USDC on Base Sepolia
EIP712_DOMAIN = {
    "name": "USDC",
    "version": "2",
    "chainId": 84532,  # Base Sepolia
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


class RealEstateAgent:
    """
    Agent that can query real estate data and valuations

    This demonstrates the "AI company" layer that builds on top
    of the incumbent's data assets
    """

    def __init__(self):
        self.api_base = API_BASE_URL
        self.http_client = httpx.Client()

        # Load agent account
        if not AGENT_PRIVATE_KEY:
            raise ValueError("AGENT_PRIVATE_KEY not set in .env")
        self.account = Account.from_key(AGENT_PRIVATE_KEY)

        print(f"🤖 Agent initialized")
        print(f"   Wallet: {self.account.address}")

        # Check USDC balance
        balance = usdc_contract.functions.balanceOf(self.account.address).call()
        balance_usd = balance / 1_000_000  # USDC has 6 decimals
        print(f"   Balance: {balance_usd:.4f} USDC")
        print()

    def create_payment(self, tier: int) -> str:
        """
        Create signed EIP-3009 authorization for USDC payment (gasless).

        Per x402 spec:
        - Agent signs EIP-712 TransferWithAuthorization
        - Returns base64-encoded JSON payload for X-PAYMENT header
        - Server settles via transferWithAuthorization (pays gas)
        - Contract nonce prevents replay attacks

        Args:
            tier: 1 for data query ($0.01), 2 for valuation ($0.10)

        Returns:
            Base64-encoded X-PAYMENT payload
        """
        amount = TIER_1_PRICE if tier == 1 else TIER_2_PRICE
        amount_usd = amount / 1_000_000

        print(f"💸 Signing payment authorization: ${amount_usd} USDC to {RECIPIENT_ADDRESS[:10]}...")

        # Generate random 32-byte nonce (EIP-3009 requirement)
        nonce = secrets.token_bytes(32)
        nonce_hex = "0x" + nonce.hex()

        # Time bounds (valid for 5 minutes)
        current_time = int(time.time())
        valid_after = current_time
        valid_before = current_time + 300  # 5 minutes

        # Build EIP-712 message
        message = {
            "from": self.account.address,
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
        signed = self.account.sign_message(signable)
        signature = signed.signature.hex()

        print(f"   ✓ Authorization signed (nonce: {nonce_hex[:18]}...)")
        print(f"   Valid for 5 minutes (until {valid_before})")

        # Build X-PAYMENT payload per x402 spec
        payload = {
            "x402Version": 2,
            "scheme": "exact",
            "network": "base-sepolia",
            "signature": "0x" + signature,
            "authorization": {
                "from": self.account.address,
                "to": RECIPIENT_ADDRESS,
                "value": str(amount),
                "validAfter": str(valid_after),
                "validBefore": str(valid_before),
                "nonce": nonce_hex,
            }
        }

        # Base64 encode for X-PAYMENT header
        x_payment = base64.b64encode(json.dumps(payload).encode()).decode()

        print()
        return x_payment

    def discover_service(self) -> Dict:
        """
        Step 1: Discover service

        In production, this would query the registry contract
        For demo, we query the API root endpoint
        """
        response = self.http_client.get(f"{self.api_base}/")
        return response.json()

    def query_listings(self, neighborhood: str = None, property_type: str = None,
                      min_price: int = None, max_price: int = None, bedrooms: int = None) -> Dict:
        """
        Query listings (Tier 1 - $0.01)

        Follows x402 protocol with EIP-3009:
        1. Try API call without payment
        2. Server returns 402 Payment Required
        3. Sign EIP-712 authorization (gasless)
        4. Retry with X-PAYMENT header
        5. Server settles via transferWithAuthorization
        """
        params = {}
        if neighborhood:
            params["neighborhood"] = neighborhood
        if property_type:
            params["property_type"] = property_type
        if min_price:
            params["min_price"] = min_price
        if max_price:
            params["max_price"] = max_price
        if bedrooms is not None:
            params["bedrooms"] = bedrooms

        # Step 1: Try without payment (will get 402)
        print(f"🔍 Querying API (first attempt)...")
        response = self.http_client.get(
            f"{self.api_base}/api/v1/listings",
            params=params
        )

        # Step 2: Server responds with 402 Payment Required
        if response.status_code == 402:
            payment_info = response.json()
            print(f"   ← 402 Payment Required")
            print(f"   Server requests: $0.01 USDC")
            print()

            # Step 3: Create signed authorization (gasless for agent)
            x_payment = self.create_payment(tier=1)

            # Step 4: Retry with X-PAYMENT header
            headers = {"X-PAYMENT": x_payment}

            print(f"🔍 Retrying API call with signed authorization...")
            response = self.http_client.get(
                f"{self.api_base}/api/v1/listings",
                params=params,
                headers=headers
            )

        if response.status_code != 200:
            raise Exception(f"API error: {response.status_code} - {response.text}")

        print(f"   ✓ API responded with {response.json().get('result_count', 0)} listings")
        print()
        return response.json()

    def get_valuation(self, address: str) -> Dict:
        """
        Get property valuation (Tier 2 - $0.10)

        Follows x402 protocol with EIP-3009:
        1. Try API call without payment
        2. Server returns 402 Payment Required
        3. Sign EIP-712 authorization (gasless)
        4. Retry with X-PAYMENT header
        5. Server settles via transferWithAuthorization
        """
        # Step 1: Try without payment (will get 402)
        print(f"🔍 Getting valuation (first attempt)...")
        response = self.http_client.get(
            f"{self.api_base}/api/v1/valuation",
            params={"address": address}
        )

        # Step 2: Server responds with 402 Payment Required
        if response.status_code == 402:
            payment_info = response.json()
            print(f"   ← 402 Payment Required")
            print(f"   Server requests: $0.10 USDC")
            print()

            # Step 3: Create signed authorization (gasless for agent)
            x_payment = self.create_payment(tier=2)

            # Step 4: Retry with X-PAYMENT header
            headers = {"X-PAYMENT": x_payment}

            print(f"🔍 Retrying with signed authorization...")
            response = self.http_client.get(
                f"{self.api_base}/api/v1/valuation",
                params={"address": address},
                headers=headers
            )

        if response.status_code != 200:
            raise Exception(f"API error: {response.status_code} - {response.text}")

        print(f"   ✓ API responded with valuation")
        print()
        return response.json()

    def get_balance(self) -> float:
        """Get current USDC balance"""
        balance = usdc_contract.functions.balanceOf(self.account.address).call()
        return balance / 1_000_000

    def close(self):
        """Close HTTP client"""
        self.http_client.close()


# Define tools for Claude
tools = [
    {
        "name": "query_listings",
        "description": "Query real estate listings. Costs $0.0001 per query. Returns up to 20 matching properties. Can filter by neighborhood, property type, price range, and bedrooms.",
        "input_schema": {
            "type": "object",
            "properties": {
                "neighborhood": {
                    "type": "string",
                    "description": "Neighborhood name (e.g., 'Ixelles', 'Etterbeek')"
                },
                "property_type": {
                    "type": "string",
                    "description": "Property type: apartment, house, studio, or penthouse"
                },
                "min_price": {
                    "type": "integer",
                    "description": "Minimum price in EUR"
                },
                "max_price": {
                    "type": "integer",
                    "description": "Maximum price in EUR"
                },
                "bedrooms": {
                    "type": "integer",
                    "description": "Number of bedrooms"
                }
            }
        }
    },
    {
        "name": "get_valuation",
        "description": "Get professional property valuation using proprietary algorithm. Costs $0.001 per query. Returns estimated value, comparable properties, confidence score, and pricing assessment. Use this for specific properties of interest.",
        "input_schema": {
            "type": "object",
            "properties": {
                "address": {
                    "type": "string",
                    "description": "Property address (must match exact address from listings)"
                }
            },
            "required": ["address"]
        }
    }
]


def run_agent(user_request: str) -> str:
    """
    Run the agent with a user request

    This demonstrates:
    1. Agent understands natural language request
    2. Agent decides which tools to use
    3. Agent autonomously creates USDC payments on Base Sepolia
    4. Agent includes payment proof in x402 headers
    5. Agent synthesizes results into useful response
    """
    agent = RealEstateAgent()

    # Track starting balance
    starting_balance = agent.get_balance()

    print(f"\n{'='*60}")
    print(f"USER REQUEST: {user_request}")
    print(f"{'='*60}\n")

    messages = [{"role": "user", "content": user_request}]

    try:
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=4096,
            tools=tools,
            messages=messages
        )

        print("Agent is thinking and using tools...\n")

        # Handle tool use
        while response.stop_reason == "tool_use":
            # Extract tool use
            tool_use_block = next(block for block in response.content if block.type == "tool_use")

            tool_name = tool_use_block.name
            tool_input = tool_use_block.input

            print(f"🔧 Using tool: {tool_name}")
            print(f"   Input: {tool_input}")

            # Execute tool
            if tool_name == "query_listings":
                result = agent.query_listings(**tool_input)
                print(f"   💰 Paid: $0.0001")
                print(f"   📊 Found {result['result_count']} listings")
            elif tool_name == "get_valuation":
                result = agent.get_valuation(**tool_input)
                print(f"   💰 Paid: $0.001")
                print(f"   📈 Valuation: €{result['valuation']['estimated_value']:,}")
            else:
                result = {"error": "Unknown tool"}

            print()

            # Continue conversation with tool result
            messages.append({"role": "assistant", "content": response.content})
            messages.append({
                "role": "user",
                "content": [{
                    "type": "tool_result",
                    "tool_use_id": tool_use_block.id,
                    "content": str(result)
                }]
            })

            response = client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=4096,
                tools=tools,
                messages=messages
            )

        # Extract final response
        final_response = next(
            (block.text for block in response.content if hasattr(block, "text")),
            None
        )

        # Show final balance
        ending_balance = agent.get_balance()
        total_spent = starting_balance - ending_balance

        print(f"\n{'='*60}")
        print("TRANSACTION SUMMARY")
        print(f"{'='*60}")
        print(f"Starting balance: {starting_balance:.4f} USDC")
        print(f"Ending balance:   {ending_balance:.4f} USDC")
        print(f"Total spent:      {total_spent:.4f} USDC")
        print(f"{'='*60}\n")

        return final_response

    finally:
        agent.close()


if __name__ == "__main__":
    # Example requests
    examples = [
        "I'm looking for a 2-bedroom apartment in Ixelles under €350,000. Can you help me find options?",
        "Find me a house in Uccle and tell me if the pricing is fair",
        "What's available in Schaerbeek for under €200k?"
    ]

    # Run first example
    result = run_agent(examples[0])

    print(f"\n{'='*60}")
    print("AGENT RESPONSE:")
    print(f"{'='*60}\n")
    print(result)
