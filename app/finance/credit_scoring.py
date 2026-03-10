from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import func, select

from app import db
from app.models import Customer, DailyStoreSummary, Product, Transaction
from app.models.finance_models import MerchantCreditProfile


def calculate_merchant_score(store_id: int) -> int:
    """
    Calculate a proprietary credit score for a merchant based on RetailIQ data signals.
    Score range: 300 - 850 (similar to FICO).
    """
    score = 500  # Starting base score
    factors = {}

    # 1. Revenue Velocity (90-day trend) - Worth up to 150 points
    ninety_days_ago = datetime.now(timezone.utc).date() - timedelta(days=90)
    summaries = (
        db.session.execute(
            select(DailyStoreSummary)
            .filter(DailyStoreSummary.store_id == store_id, DailyStoreSummary.date >= ninety_days_ago)
            .order_by(DailyStoreSummary.date)
        )
        .scalars()
        .all()
    )

    if summaries:
        total_rev = sum(s.revenue for s in summaries if s.revenue)
        avg_rev = total_rev / len(summaries)

        # Simple velocity check
        if len(summaries) > 30:
            first_half = sum(s.revenue for s in summaries[: len(summaries) // 2] if s.revenue)
            second_half = sum(s.revenue for s in summaries[len(summaries) // 2 :] if s.revenue)

            if second_half > first_half:
                velocity_bonus = min(50, int((second_half / first_half - 1) * 100))
                score += velocity_bonus
                factors["revenue_velocity"] = f"+{velocity_bonus} (Positive trend)"
            else:
                velocity_penalty = min(50, int((1 - second_half / (first_half or 1)) * 100))
                score -= velocity_penalty
                factors["revenue_velocity"] = f"-{velocity_penalty} (Negative trend)"

        # Absolute volume bonus
        volume_bonus = min(100, int(total_rev / 10000))
        score += volume_bonus
        factors["absolute_volume"] = f"+{volume_bonus}"
    else:
        score -= 50
        factors["revenue_data"] = "-50 (Missing history)"

    # 2. Inventory Turnover - Worth up to 100 points
    # (High stock vs Low sales = bad turnover)
    # This is a simplified proxy
    products = db.session.execute(select(Product).filter_by(store_id=store_id, is_active=True)).scalars().all()

    if products:
        dead_stock = sum(1 for p in products if p.current_stock > 0 and p.current_stock > p.reorder_level * 5)
        if dead_stock > len(products) * 0.3:
            score -= 40
            factors["inventory_turnover"] = "-40 (Excessive dead stock)"
        else:
            score += 30
            factors["inventory_turnover"] = "+30 (Healthy stock levels)"

    # 3. Customer Retention - Worth up to 100 points
    customer_count = (
        db.session.execute(select(func.count(Customer.customer_id)).filter_by(store_id=store_id)).scalar() or 0
    )

    if customer_count > 100:
        score += 40
        factors["customer_base"] = "+40 (Established base)"
    elif customer_count > 10:
        score += 10
        factors["customer_base"] = "+10"

    # 4. Consistency of processing (Active days) - Worth up to 50 points
    if summaries:
        active_days = len(summaries)
        score += min(50, active_days // 2)
        factors["consistency"] = f"+{min(50, active_days // 2)} (History length)"

    # Clamp score
    score = max(300, min(850, score))

    # Save/Update profile
    profile = db.session.execute(select(MerchantCreditProfile).filter_by(store_id=store_id)).scalar_one_or_none()

    if not profile:
        profile = MerchantCreditProfile(store_id=store_id)
        db.session.add(profile)

    profile.credit_score = score
    profile.factors = factors
    profile.last_recalculated = datetime.now(timezone.utc)

    # Simple risk tiering
    if score >= 750:
        profile.risk_tier = "A"
    elif score >= 650:
        profile.risk_tier = "B"
    elif score >= 550:
        profile.risk_tier = "C"
    elif score >= 450:
        profile.risk_tier = "D"
    else:
        profile.risk_tier = "E"

    db.session.flush()
    return score
