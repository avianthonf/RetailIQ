import logging

import numpy as np
import pandas as pd
from sklearn.metrics.pairwise import cosine_similarity

logger = logging.getLogger(__name__)


class RetailRecommender:
    """
    Two-tower Recommendation Model (Simplified for integration).
    """

    def __init__(self):
        self.user_embeddings = {}
        self.item_embeddings = {}

    def get_recommendations(self, user_id: int, top_k=5):
        # Mock embeddings logic
        # In production, these are learned via Dot Product of User and Item towers
        items = ["Product_A", "Product_B", "Product_C", "Bundle_1", "Bundle_2"]
        # Randomly shuffle for demo
        np.random.shuffle(items)
        return items[:top_k]

    def get_bundle_suggestions(self, product_id: int):
        # Association Rule Mining or Embedding similarity
        return ["Product_Frequently_Bought_With_" + str(product_id)]


def get_ai_recommendations(user_id: int, store_id: int):
    recommender = RetailRecommender()
    return recommender.get_recommendations(user_id)


def get_product_bundles(product_id: int):
    recommender = RetailRecommender()
    return recommender.get_bundle_suggestions(product_id)
