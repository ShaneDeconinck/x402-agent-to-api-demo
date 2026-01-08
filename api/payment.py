"""
x402 Payment Verification & Settlement
Verifies and settles USDC payments on Base testnet using EIP-3009

Per x402 spec, uses transferWithAuthorization for gasless payments:
- Agent signs EIP-712 authorization (no gas required)
- Server calls transferWithAuthorization to settle (pays gas)
- Contract handles nonce replay protection
"""
from web3 import Web3
from eth_account import Account
from typing import Optional, Dict
import os
import json
import base64
from datetime import datetime, timedelta

# Base Sepolia testnet RPC
BASE_SEPOLIA_RPC = "https://sepolia.base.org"

# USDC contract on Base Sepolia
USDC_CONTRACT_ADDRESS = os.getenv("USDC_CONTRACT_ADDRESS", "0x036CbD53842c5426634e7929541eC2318f3dCF7e")

# Price tiers in USDC (6 decimals)
TIER_1_PRICE = 10000  # $0.01 in USDC
TIER_2_PRICE = 100000  # $0.10 in USDC

# EIP-3009 ABI for USDC
USDC_ABI = [
    {
        "inputs": [
            {"name": "from", "type": "address"},
            {"name": "to", "type": "address"},
            {"name": "value", "type": "uint256"},
            {"name": "validAfter", "type": "uint256"},
            {"name": "validBefore", "type": "uint256"},
            {"name": "nonce", "type": "bytes32"},
            {"name": "v", "type": "uint8"},
            {"name": "r", "type": "bytes32"},
            {"name": "s", "type": "bytes32"}
        ],
        "name": "transferWithAuthorization",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function"
    },
    {
        "inputs": [
            {"name": "authorizer", "type": "address"},
            {"name": "nonce", "type": "bytes32"}
        ],
        "name": "authorizationState",
        "outputs": [{"name": "", "type": "bool"}],
        "stateMutability": "view",
        "type": "function"
    },
    {
        "inputs": [{"name": "_owner", "type": "address"}],
        "name": "balanceOf",
        "outputs": [{"name": "balance", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function"
    }
]

class PaymentVerifier:
    """
    Verifies and settles x402 payments using EIP-3009 transferWithAuthorization.

    Flow:
    1. Agent signs EIP-712 authorization (gasless for agent)
    2. Server receives signature + authorization in X-PAYMENT header
    3. Server calls transferWithAuthorization on USDC contract (pays gas)
    4. Contract verifies signature, checks nonce not used, transfers USDC
    """

    def __init__(self):
        self.w3 = Web3(Web3.HTTPProvider(BASE_SEPOLIA_RPC))
        self.usdc_contract = self.w3.eth.contract(
            address=Web3.to_checksum_address(USDC_CONTRACT_ADDRESS),
            abi=USDC_ABI
        )
        self.recipient_address = Web3.to_checksum_address(os.getenv("RECIPIENT_ADDRESS"))

        # Server wallet for settling payments (pays gas)
        server_private_key = os.getenv("RECIPIENT_PRIVATE_KEY")
        if server_private_key and not server_private_key.startswith("0x"):
            server_private_key = "0x" + server_private_key
        self.server_account = Account.from_key(server_private_key) if server_private_key else None

    def _is_nonce_used(self, from_address: str, nonce: bytes) -> bool:
        """Check if nonce has been used on-chain (EIP-3009 contract check)"""
        try:
            return self.usdc_contract.functions.authorizationState(
                Web3.to_checksum_address(from_address),
                nonce
            ).call()
        except Exception:
            return False

    def verify_and_settle(self, x_payment: str, tier: int) -> Dict:
        """
        Verify and settle payment using EIP-3009 transferWithAuthorization.

        Args:
            x_payment: Base64-encoded JSON with signature and authorization
            tier: 1 for data query ($0.01), 2 for valuation ($0.10)

        Returns:
            Dict with verification/settlement result
        """
        try:
            # Decode X-PAYMENT header
            payload = json.loads(base64.b64decode(x_payment).decode())

            signature = payload.get("signature")
            auth = payload.get("authorization", {})

            from_addr = Web3.to_checksum_address(auth.get("from"))
            to_addr = Web3.to_checksum_address(auth.get("to"))
            value = int(auth.get("value"))
            valid_after = int(auth.get("validAfter"))
            valid_before = int(auth.get("validBefore"))
            nonce = bytes.fromhex(auth.get("nonce").replace("0x", ""))

        except Exception as e:
            return {"valid": False, "error": f"Invalid X-PAYMENT format: {str(e)}"}

        # Verify recipient matches our address
        if to_addr.lower() != self.recipient_address.lower():
            return {"valid": False, "error": f"Invalid recipient. Expected {self.recipient_address}"}

        # Verify amount meets tier requirement
        expected_amount = TIER_1_PRICE if tier == 1 else TIER_2_PRICE
        if value < expected_amount:
            return {"valid": False, "error": f"Insufficient payment. Expected {expected_amount}, got {value}"}

        # Verify time bounds
        current_time = int(datetime.now().timestamp())
        if current_time < valid_after:
            return {"valid": False, "error": "Authorization not yet valid"}
        if current_time > valid_before:
            return {"valid": False, "error": "Authorization expired"}

        # Check if nonce already used (on-chain check)
        if self._is_nonce_used(from_addr, nonce):
            return {"valid": False, "error": "Nonce already used (replay attack prevented)"}

        # Check payer has sufficient balance
        balance = self.usdc_contract.functions.balanceOf(from_addr).call()
        if balance < value:
            return {"valid": False, "error": f"Insufficient USDC balance. Has {balance}, needs {value}"}

        # Parse signature
        if signature.startswith("0x"):
            signature = signature[2:]
        sig_bytes = bytes.fromhex(signature)

        if len(sig_bytes) == 65:
            r = sig_bytes[:32]
            s = sig_bytes[32:64]
            v = sig_bytes[64]
            # Adjust v if needed (some signers use 0/1, contract expects 27/28)
            if v < 27:
                v += 27
        else:
            return {"valid": False, "error": "Invalid signature length"}

        # Settle payment by calling transferWithAuthorization
        if not self.server_account:
            return {"valid": False, "error": "Server wallet not configured for settlement"}

        try:
            # Build transaction
            tx = self.usdc_contract.functions.transferWithAuthorization(
                from_addr,
                to_addr,
                value,
                valid_after,
                valid_before,
                nonce,
                v,
                r,
                s
            ).build_transaction({
                'from': self.server_account.address,
                'gas': 100000,
                'gasPrice': self.w3.eth.gas_price,
                'nonce': self.w3.eth.get_transaction_count(self.server_account.address),
                'chainId': 84532  # Base Sepolia
            })

            # Sign and send
            signed_tx = self.w3.eth.account.sign_transaction(tx, self.server_account.key)
            tx_hash = self.w3.eth.send_raw_transaction(signed_tx.raw_transaction)

            # Wait for confirmation
            receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash, timeout=60)

            if receipt['status'] != 1:
                return {"valid": False, "error": "Settlement transaction failed"}

            return {
                "valid": True,
                "tx_hash": tx_hash.hex(),
                "amount_usd": value / 1_000_000,
                "tier": tier,
                "from_address": from_addr,
                "settled_at": datetime.now().isoformat(),
                "block_number": receipt['blockNumber']
            }

        except Exception as e:
            error_msg = str(e)
            if "already used" in error_msg.lower() or "nonce" in error_msg.lower():
                return {"valid": False, "error": "Nonce already used (replay attack prevented)"}
            return {"valid": False, "error": f"Settlement failed: {error_msg}"}

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
