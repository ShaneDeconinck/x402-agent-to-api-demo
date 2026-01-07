"""
Proprietary valuation algorithm
This represents the incumbent's intellectual property - not just data, but expertise

Simple but realistic model that demonstrates the concept
"""
import sqlite3
from typing import Dict, List, Optional

def get_comparables(address: str, neighborhood: str, property_type: str, sqm: int, db_path: str = "data/real_estate.db") -> List[Dict]:
    """Find comparable properties"""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Find similar properties in same neighborhood
    cursor.execute('''
        SELECT address, property_type, bedrooms, sqm, price, days_on_market
        FROM listings
        WHERE neighborhood = ?
        AND property_type = ?
        AND sqm BETWEEN ? AND ?
        AND address != ?
        ORDER BY ABS(sqm - ?) ASC
        LIMIT 5
    ''', (neighborhood, property_type, sqm * 0.8, sqm * 1.2, address, sqm))

    comparables = []
    for row in cursor.fetchall():
        comparables.append({
            "address": row[0],
            "property_type": row[1],
            "bedrooms": row[2],
            "sqm": row[3],
            "price": row[4],
            "days_on_market": row[5],
            "price_per_sqm": round(row[4] / row[3], 2)
        })

    conn.close()
    return comparables

def calculate_valuation(address: str, db_path: str = "data/real_estate.db") -> Optional[Dict]:
    """
    Proprietary valuation algorithm

    This is simplified but demonstrates the concept:
    - Uses comparable sales
    - Adjusts for time on market (demand signal)
    - Applies neighborhood trends
    - Returns confidence score

    Real algorithms would be much more complex, but this shows
    how IP is embedded in the calculation, not just the data
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Get property details
    cursor.execute('''
        SELECT address, neighborhood, property_type, bedrooms, sqm, price, days_on_market
        FROM listings
        WHERE address = ?
    ''', (address,))

    result = cursor.fetchone()
    if not result:
        conn.close()
        return None

    address, neighborhood, property_type, bedrooms, sqm, listed_price, days_on_market = result

    # Get comparables
    comparables = get_comparables(address, neighborhood, property_type, sqm, db_path)

    if not comparables:
        conn.close()
        return {
            "address": address,
            "estimated_value": listed_price,
            "confidence": "low",
            "reasoning": "Insufficient comparable properties for accurate valuation",
            "comparables": []
        }

    # Calculate average price per sqm from comparables
    avg_price_per_sqm = sum(c['price_per_sqm'] for c in comparables) / len(comparables)

    # Base valuation
    base_value = avg_price_per_sqm * sqm

    # Adjustment factor based on days on market
    # If property has been on market long, it might be overpriced
    if days_on_market > 90:
        market_adjustment = 0.95  # 5% discount
        adjustment_reason = "Property has been on market >90 days, suggesting price resistance"
    elif days_on_market < 30:
        market_adjustment = 1.02  # 2% premium
        adjustment_reason = "Fresh listing, market typically pays premium"
    else:
        market_adjustment = 1.0
        adjustment_reason = "Normal market duration"

    estimated_value = int(base_value * market_adjustment)

    # Confidence score
    comparable_count = len(comparables)
    price_variance = max(c['price_per_sqm'] for c in comparables) - min(c['price_per_sqm'] for c in comparables)
    relative_variance = price_variance / avg_price_per_sqm

    if comparable_count >= 4 and relative_variance < 0.15:
        confidence = "high"
    elif comparable_count >= 3 and relative_variance < 0.25:
        confidence = "medium"
    else:
        confidence = "low"

    # Valuation vs listed price
    price_difference = ((estimated_value - listed_price) / listed_price) * 100

    if price_difference > 10:
        pricing_assessment = "underpriced"
    elif price_difference < -10:
        pricing_assessment = "overpriced"
    else:
        pricing_assessment = "fairly priced"

    conn.close()

    return {
        "address": address,
        "neighborhood": neighborhood,
        "property_type": property_type,
        "sqm": sqm,
        "listed_price": listed_price,
        "estimated_value": estimated_value,
        "price_per_sqm": round(estimated_value / sqm, 2),
        "confidence": confidence,
        "pricing_assessment": pricing_assessment,
        "price_difference_pct": round(price_difference, 1),
        "reasoning": f"Based on {comparable_count} comparable properties. {adjustment_reason}.",
        "comparables": comparables[:3],  # Return top 3
        "market_metrics": {
            "avg_price_per_sqm": round(avg_price_per_sqm, 2),
            "days_on_market": days_on_market,
            "market_adjustment": market_adjustment
        }
    }

# This is the "secret sauce" - the algorithm that turns data into insights
# In a real scenario, this would be much more sophisticated:
# - ML models trained on historical sales
# - Macro economic indicators
# - Neighborhood trends over time
# - Seasonal adjustments
# - Renovation quality assessments
# etc.
