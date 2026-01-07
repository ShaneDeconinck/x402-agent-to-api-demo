"""
Real Estate Agent using Anthropic SDK

Demonstrates:
- Service discovery via registry
- Autonomous payment via x402
- Tool use to query APIs
- Decision making based on data
"""
import os
import httpx
from anthropic import Anthropic
from typing import Dict, List
from web3 import Web3
from eth_account import Account
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

# ERC20 ABI (minimal - just what we need)
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

# Initialize USDC contract
usdc_contract = w3.eth.contract(address=USDC_ADDRESS, abi=USDC_ABI)

# Agent wallet (loads from .env)
AGENT_PRIVATE_KEY = os.getenv("AGENT_PRIVATE_KEY")
if AGENT_PRIVATE_KEY and not AGENT_PRIVATE_KEY.startswith("0x"):
    AGENT_PRIVATE_KEY = "0x" + AGENT_PRIVATE_KEY

# Recipient address (incumbent/API owner)
RECIPIENT_ADDRESS = Web3.to_checksum_address(os.getenv("RECIPIENT_ADDRESS"))

# Pricing (must match API)
TIER_1_PRICE = 100  # $0.0001 in USDC (6 decimals)
TIER_2_PRICE = 1000  # $0.001 in USDC


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
        Create USDC payment transaction on Base Sepolia

        Args:
            tier: 1 for data query ($0.0001), 2 for valuation ($0.001)

        Returns:
            Transaction hash
        """
        amount = TIER_1_PRICE if tier == 1 else TIER_2_PRICE
        amount_usd = amount / 1_000_000

        print(f"💸 Creating payment: ${amount_usd} USDC to {RECIPIENT_ADDRESS[:10]}...")

        # Build transaction
        nonce = w3.eth.get_transaction_count(self.account.address)

        # Create USDC transfer transaction
        transfer_function = usdc_contract.functions.transfer(RECIPIENT_ADDRESS, amount)

        # Estimate gas
        gas_estimate = transfer_function.estimate_gas({'from': self.account.address})

        # Build transaction
        transaction = transfer_function.build_transaction({
            'from': self.account.address,
            'gas': gas_estimate,
            'gasPrice': w3.eth.gas_price,
            'nonce': nonce,
            'chainId': 84532  # Base Sepolia
        })

        # Sign transaction
        signed_txn = w3.eth.account.sign_transaction(transaction, AGENT_PRIVATE_KEY)

        # Send transaction
        tx_hash = w3.eth.send_raw_transaction(signed_txn.raw_transaction)
        tx_hash_hex = tx_hash.hex()

        print(f"   Transaction sent: {tx_hash_hex[:20]}...")
        print(f"   Waiting for confirmation...")

        # Wait for transaction receipt
        receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)

        if receipt['status'] == 1:
            print(f"   ✓ Payment confirmed!")
            print(f"   View on BaseScan: https://sepolia.basescan.org/tx/{tx_hash_hex}")
            # Wait for RPC node to index the block (public nodes are slow)
            print(f"   ⏳ Waiting 20s for block propagation...")
            time.sleep(20)
        else:
            print(f"   ✗ Payment failed!")
            raise Exception("Payment transaction failed")

        print()
        return tx_hash_hex

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
        Query listings (Tier 1 - $0.0001)

        Follows x402 protocol:
        1. Try API call without payment
        2. Server returns 402 Payment Required
        3. Create payment based on server's requirements
        4. Retry with payment proof
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
            print(f"   Server requests: ${payment_info.get('price_usd', 0)} USDC")
            print()

            # Step 3: Create payment as requested by server
            tx_hash = self.create_payment(tier=1)

            # Step 4: Retry with payment proof
            headers = {
                "X-Payment-Proof": tx_hash
            }

            print(f"🔍 Retrying API call with payment proof...")
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
        Get property valuation (Tier 2 - $0.001)

        Follows x402 protocol:
        1. Try API call without payment
        2. Server returns 402 Payment Required
        3. Create payment based on server's requirements
        4. Retry with payment proof
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
            print(f"   Server requests: ${payment_info.get('price_usd', 0)} USDC")
            print()

            # Step 3: Create payment as requested by server
            tx_hash = self.create_payment(tier=2)

            # Step 4: Retry with payment proof
            headers = {
                "X-Payment-Proof": tx_hash
            }

            print(f"🔍 Retrying with payment proof...")
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
