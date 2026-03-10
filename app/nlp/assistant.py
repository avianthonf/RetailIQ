import logging

import faiss
import numpy as np
from sentence_transformers import SentenceTransformer
from transformers import pipeline

logger = logging.getLogger(__name__)


class RetailAssistant:
    """
    NLP Assistant using RAG and fine-tuned LLaMA (simulated with transformer pipeline).
    """

    def __init__(self):
        # In a real production environment, we'd load a 7B model on GPU
        # For this implementation, we use a smaller model for demonstration
        self.generator = pipeline("text-generation", model="facebook/opt-125m")
        self.embedder = SentenceTransformer("all-MiniLM-L6-v2")
        self.index = faiss.IndexFlatL2(384)
        self.kb_docs = []

    def add_to_knowledge_base(self, docs: list[str]):
        self.kb_docs.extend(docs)
        embeddings = self.embedder.encode(docs)
        self.index.add(np.array(embeddings).astype("float32"))

    def query(self, user_query: str):
        # 1. Retrieve
        query_vec = self.embedder.encode([user_query])
        D, I = self.index.search(np.array(query_vec).astype("float32"), k=2)

        context = ""
        for i in I[0]:
            if i < len(self.kb_docs):
                context += self.kb_docs[i] + "\n"

        # 2. Augment & Generate
        prompt = f"Context: {context}\nQuestion: {user_query}\nAnswer:"
        response = self.generator(prompt, max_new_tokens=50)[0]["generated_text"]

        return response.split("Answer:")[-1].strip()


def handle_assistant_query(query_text: str, store_id: int):
    assistant = RetailAssistant()
    # Mock KB integration
    assistant.add_to_knowledge_base(
        [
            "Store 101 has high demand for milk this weekend.",
            "Supplier Alpha is delayed by 2 days.",
            "Current promotion on Bread ends on Tuesday.",
        ]
    )
    return assistant.query(query_text)
