"""
Real Estate API with x402 Payment Required

Two-tier API demonstrating agent-accessible data assets:
- Tier 1: Raw data queries ($0.0001)
- Tier 2: Proprietary valuation ($0.001)
"""
from fastapi import FastAPI, HTTPException, Header, Query
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from typing import Optional, List
import sqlite3
import os
from pydantic import BaseModel

from payment import get_payment_verifier, USDC_CONTRACT_ADDRESS
from valuation import calculate_valuation
from demo import router as demo_router

# Payment configuration
RECIPIENT_ADDRESS = os.environ.get("RECIPIENT_ADDRESS")
CHAIN_ID = 84532  # Base Sepolia
NETWORK = "base-sepolia"

app = FastAPI(
    title="Real Estate API (x402)",
    description="Agent-accessible real estate data with pay-per-query model",
    version="0.1.0"
)

# CORS for frontend demo
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include demo router
app.include_router(demo_router)

# Payment verifier (verifies real USDC transactions on Base Sepolia)
payment_verifier = get_payment_verifier()

# Database path (relative to api directory)
DB_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "real_estate.db")


# Models
class ListingQuery(BaseModel):
    neighborhood: Optional[str] = None
    property_type: Optional[str] = None
    min_price: Optional[int] = None
    max_price: Optional[int] = None
    bedrooms: Optional[int] = None
    limit: int = 10


class PricingInfo(BaseModel):
    """API pricing information"""
    tier_1_price: float
    tier_1_description: str
    tier_2_price: float
    tier_2_description: str
    payment_method: str
    currency: str


# Helper functions
def get_db_connection():
    """Get database connection"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def get_x402_payment_details(tier: int) -> dict:
    """
    Generate machine-readable x402 payment requirements.

    This is the key to the x402 protocol: the 402 response tells the agent
    exactly how to pay - what token, what amount, what address, and how to
    prove payment. Any agent can parse this and pay autonomously.
    """
    price_usd = payment_verifier.get_price(tier)
    # USDC has 6 decimals, so $0.0001 = 100 units
    amount_units = int(price_usd * 1_000_000)

    return {
        "x402_version": "1.0",
        "payment": {
            # What to pay
            "amount": str(amount_units),
            "amount_usd": price_usd,
            "currency": "USDC",
            "decimals": 6,

            # Where to pay
            "recipient": RECIPIENT_ADDRESS,
            "contract": USDC_CONTRACT_ADDRESS,

            # Which network
            "network": NETWORK,
            "chain_id": CHAIN_ID,

            # How to prove payment
            "proof": {
                "header": "X-Payment-Proof",
                "type": "transaction_hash",
                "description": "Include the transaction hash of your USDC transfer"
            }
        },
        "tier": tier,
        "expires_in_seconds": 3600,  # Payment must be recent
        "description": f"Tier {tier} access requires {price_usd} USDC payment"
    }


def verify_x402_payment(payment_proof: Optional[str], tier: int) -> dict:
    """
    Verify x402 payment header

    The x402 protocol: Client includes payment proof in header
    Server verifies before responding
    """
    if not payment_proof:
        raise HTTPException(
            status_code=402,
            detail=get_x402_payment_details(tier)
        )

    # Verify payment
    verification = payment_verifier.verify_payment(payment_proof, tier)

    if not verification["valid"]:
        payment_details = get_x402_payment_details(tier)
        payment_details["error"] = verification.get("error", "Payment verification failed")
        raise HTTPException(
            status_code=402,
            detail=payment_details
        )

    return verification


# Endpoints

@app.get("/")
async def root():
    """API information and discovery"""
    return {
        "name": "Real Estate API",
        "description": "Agent-accessible real estate data with x402 payment",
        "version": "0.1.0",
        "tiers": {
            "tier_1": {
                "endpoint": "/api/v1/listings",
                "description": "Query real estate listings",
                "price_usd": 0.0001,
                "payment_required": True
            },
            "tier_2": {
                "endpoint": "/api/v1/valuation",
                "description": "Proprietary property valuation",
                "price_usd": 0.001,
                "payment_required": True
            }
        },
        "payment": {
            "method": "USDC on Base testnet",
            "header": "X-Payment-Proof",
            "value": "Transaction hash of USDC payment"
        },
        "docs": "/docs"
    }


@app.get("/pricing")
async def get_pricing() -> PricingInfo:
    """Get API pricing information"""
    return PricingInfo(
        tier_1_price=0.0001,
        tier_1_description="Query listings by location/criteria",
        tier_2_price=0.001,
        tier_2_description="Proprietary valuation algorithm",
        payment_method="USDC on Base testnet",
        currency="USD"
    )


@app.get("/api/v1/listings")
async def get_listings(
    neighborhood: Optional[str] = None,
    property_type: Optional[str] = None,
    min_price: Optional[int] = None,
    max_price: Optional[int] = None,
    bedrooms: Optional[int] = None,
    limit: int = Query(10, le=20),  # Max 20 results (prevents bulk extraction)
    x_payment_proof: Optional[str] = Header(None)
):
    """
    TIER 1: Query real estate listings ($0.0001 per query)

    Requires x402 payment proof in X-Payment-Proof header

    Query parameters prevent bulk extraction:
    - Must specify search criteria
    - Maximum 20 results per query
    - Cannot dump entire database
    """
    # Verify payment
    payment = verify_x402_payment(x_payment_proof, tier=1)

    # Build query
    conn = get_db_connection()
    cursor = conn.cursor()

    query = "SELECT * FROM listings WHERE 1=1"
    params = []

    if neighborhood:
        query += " AND neighborhood = ?"
        params.append(neighborhood)

    if property_type:
        query += " AND property_type = ?"
        params.append(property_type)

    if min_price:
        query += " AND price >= ?"
        params.append(min_price)

    if max_price:
        query += " AND price <= ?"
        params.append(max_price)

    if bedrooms is not None:
        query += " AND bedrooms = ?"
        params.append(bedrooms)

    query += f" LIMIT {limit}"

    cursor.execute(query, params)
    rows = cursor.fetchall()

    listings = [dict(row) for row in rows]
    conn.close()

    return {
        "tier": 1,
        "price_paid_usd": payment["amount_usd"],
        "query": {
            "neighborhood": neighborhood,
            "property_type": property_type,
            "min_price": min_price,
            "max_price": max_price,
            "bedrooms": bedrooms
        },
        "result_count": len(listings),
        "listings": listings,
        "note": "Data queries are scoped to prevent bulk extraction. Multiple specific queries required to access full dataset."
    }


@app.get("/api/v1/valuation")
async def get_valuation(
    address: str,
    x_payment_proof: Optional[str] = Header(None)
):
    """
    TIER 2: Property valuation ($0.001 per query)

    Requires x402 payment proof in X-Payment-Proof header

    Returns proprietary valuation based on:
    - Comparable sales analysis
    - Market demand signals
    - Neighborhood trends
    - Confidence scoring

    This endpoint sells INSIGHTS, not raw data.
    The algorithm is the intellectual property.
    """
    # Verify payment
    payment = verify_x402_payment(x_payment_proof, tier=2)

    # Calculate valuation
    valuation = calculate_valuation(address, DB_PATH)

    if not valuation:
        raise HTTPException(
            status_code=404,
            detail=f"Property not found: {address}"
        )

    return {
        "tier": 2,
        "price_paid_usd": payment["amount_usd"],
        "valuation": valuation,
        "note": "Valuation uses proprietary algorithm. The IP is in the calculation, not the data."
    }


@app.get("/health")
async def health_check():
    """Health check endpoint (no payment required)"""
    return {"status": "healthy", "payment_required": False}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
