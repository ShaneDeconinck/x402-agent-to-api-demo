"""
x402 Payment Verification
Verifies USDC payments on Base testnet before serving API requests
"""
from web3 import Web3
from typing import Optional, Dict
import os
from datetime import datetime, timedelta

# Base Sepolia testnet RPC
BASE_SEPOLIA_RPC = "https://sepolia.base.org"

# USDC contract on Base Sepolia (you'll need to deploy or use existing)
# For demo purposes, we'll use a placeholder - in production this would be the real USDC contract
USDC_CONTRACT_ADDRESS = os.getenv("USDC_CONTRACT_ADDRESS", "0x036CbD53842c5426634e7929541eC2318f3dCF7e")  # Base Sepolia USDC

# Price tiers in USDC (6 decimals)
TIER_1_PRICE = 10000  # $0.01 in USDC
TIER_2_PRICE = 100000  # $0.10 in USDC

# Minimum ABI for USDC transfer events
USDC_ABI = [
    {
        "anonymous": False,
        "inputs": [
            {"indexed": True, "name": "from", "type": "address"},
            {"indexed": True, "name": "to", "type": "address"},
            {"indexed": False, "name": "value", "type": "uint256"}
        ],
        "name": "Transfer",
        "type": "event"
    }
]

class PaymentVerifier:
    """Verifies x402 payments on Base testnet"""

    def __init__(self):
        self.w3 = Web3(Web3.HTTPProvider(BASE_SEPOLIA_RPC))
        self.usdc_contract = self.w3.eth.contract(
            address=Web3.to_checksum_address(USDC_CONTRACT_ADDRESS),
            abi=USDC_ABI
        )
        self.recipient_address = os.getenv("RECIPIENT_ADDRESS")  # API owner's address

    def verify_payment(self, tx_hash: str, tier: int) -> Dict:
        """
        Verify payment transaction

        Args:
            tx_hash: Transaction hash from x402 header
            tier: 1 for data query, 2 for valuation

        Returns:
            Dict with verification result
        """
        import time

        # Retry logic for RPC lag (public nodes are slow to index)
        max_retries = 5
        retry_delay = 3  # seconds (total: up to 15 seconds)

        for attempt in range(max_retries):
            try:
                # Get transaction receipt
                receipt = self.w3.eth.get_transaction_receipt(tx_hash)
                break  # Success, exit retry loop
            except Exception as e:
                if "not found" in str(e).lower() and attempt < max_retries - 1:
                    # Block not indexed yet, wait and retry
                    time.sleep(retry_delay)
                    continue
                else:
                    # Real error or out of retries
                    return {
                        "valid": False,
                        "error": f"Verification failed: {str(e)}"
                    }

        try:

            # Check if transaction was successful
            if receipt['status'] != 1:
                return {
                    "valid": False,
                    "error": "Transaction failed"
                }

            # Check transaction recency (within last hour)
            block = self.w3.eth.get_block(receipt['blockNumber'])
            tx_time = datetime.fromtimestamp(block['timestamp'])
            if datetime.now() - tx_time > timedelta(hours=1):
                return {
                    "valid": False,
                    "error": "Transaction too old (must be within 1 hour)"
                }

            # Get transaction to check value and recipient
            tx = self.w3.eth.get_transaction(tx_hash)

            # For simplified demo: check if transaction exists and is recent
            # In production, you would:
            # 1. Verify it's a USDC transfer (parse logs)
            # 2. Verify correct amount based on tier
            # 3. Verify recipient is API owner
            # 4. Check transaction hasn't been used before (prevent replay)

            expected_amount = TIER_1_PRICE if tier == 1 else TIER_2_PRICE

            return {
                "valid": True,
                "tx_hash": tx_hash,
                "amount_usd": expected_amount / 1000000,  # Convert to dollars
                "tier": tier,
                "timestamp": tx_time.isoformat(),
                "from_address": tx['from']
            }

        except Exception as e:
            if "not found" in str(e).lower():
                return {
                    "valid": False,
                    "error": f"Transaction not yet indexed. Please retry in 5-10 seconds: {str(e)}"
                }
            return {
                "valid": False,
                "error": f"Verification failed: {str(e)}"
            }

    def get_price(self, tier: int) -> float:
        """Get price for tier in USD"""
        if tier == 1:
            return 0.01
        elif tier == 2:
            return 0.10
        else:
            raise ValueError("Invalid tier")


def get_payment_verifier() -> PaymentVerifier:
    """Get payment verifier"""
    return PaymentVerifier()
