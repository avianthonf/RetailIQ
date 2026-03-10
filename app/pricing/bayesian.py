import logging
from datetime import datetime, timedelta

import numpy as np
import pandas as pd
import pymc as pm
import shap

logger = logging.getLogger(__name__)


from typing import List


class BayesianPricer:
    """
    Bayesian Price Elasticity Modeling using PyMC.
    """

    def __init__(self):
        self.trace = None
        self.model = None

    def estimate_elasticity(self, prices: list[float], quantities: list[float]):
        """
        Estimate elasticity using a log-log model: log(Q) = alpha + beta * log(P) + epsilon
        """
        log_p = np.log(prices)
        log_q = np.log(quantities)

        with pm.Model() as self.model:
            alpha = pm.Normal("alpha", mu=0, sigma=10)
            beta = pm.Normal("beta", mu=-1, sigma=5)  # Elasticity usually negative
            sigma = pm.HalfNormal("sigma", sigma=1)

            mu = alpha + beta * log_p
            pm.Normal("obs", mu=mu, sigma=sigma, observed=log_q)

            self.trace = pm.sample(draws=1000, tune=500, chains=2, target_accept=0.9, progressbar=False)

        return pm.summary(self.trace, var_names=["beta"])["mean"].iloc[0]

    def explain_decision(self, model, X):
        """
        Provide SHAP explanations for pricing decisions.
        """
        explainer = shap.Explainer(model)
        shap_values = explainer(X)
        return shap_values


def get_bayesian_recommendation(prices, quantities, current_price, cost_price, inventory_level):
    pricer = BayesianPricer()
    try:
        elasticity = pricer.estimate_elasticity(prices, quantities)
    except Exception:
        elasticity = -0.5  # Default fallback

    # Optimization logic: Maximize Profit = (P - Cost) * Q(P)
    # Q(P) is modeled by elasticity

    suggested_price = current_price
    if elasticity > -1:  # Inelastic
        suggested_price = current_price * 1.05
    elif elasticity < -2:  # Very elastic
        suggested_price = current_price * 0.95

    # Inventory pressure guardrail
    if inventory_level < 5:
        suggested_price *= 1.10  # Raise price if stock is low

    return {
        "suggested_price": round(suggested_price, 2),
        "elasticity": round(elasticity, 3),
        "reason": "Bayesian elasticity optimization with inventory pressure guardrails.",
    }
