ONESHOT_SOLVER_PROMPT = """
You are a question-answering system for a RAG benchmark.

Answer the question using ONLY the information in the provided context.
If the context does not contain enough information to answer, output exactly:
Insufficient information in the provided context.

Return only the answer text. Do not include citations, preamble, or explanations of your reasoning.

Question:
{question}

Context:
{context}
""".strip()


HYDE_PROMPT = """
Write a short, information-dense passage that would answer the user query below.
The passage should look like something that could appear in a relevant document.
Do not mention that this is hypothetical. Do not include preamble, headings, or bullet points.
Output ONLY the passage text.

User query:
{query}
""".strip()

PLANNED_MULTIHOP_PLANNING_PROMPT = """
You generate search sub-queries for retrieving information from a vector database.

Given the user question, produce 2 to 6 focused search queries that help retrieve the necessary passages.
- Include key entities, synonyms/alternate phrasings, and important constraints (dates, locations, identifiers).
- Keep each query short (3-12 words) and specific.

Return ONLY a JSON object with this exact shape:
{{"queries": ["...", "..."]}}
No additional keys. No commentary. No markdown.

User question:
{question}
""".strip()

PLANNED_MULTIHOP_EXECUTION_PROMPT = """
You are a question-answering system for a RAG benchmark.

Answer the question using ONLY the information in the provided context.
If the context does not contain enough information to answer, output exactly:
Insufficient information in the provided context.

If the context contains conflicting claims and you cannot determine the correct one from the context alone,
output exactly: Insufficient information in the provided context.

Return only the answer text. Do not include citations, preamble, or explanations of your reasoning.

Question:
{question}

Context:
{context}
""".strip()