from typing import List, Tuple
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnablePassthrough
from langchain_core.output_parsers import StrOutputParser
from langchain_core.documents import Document

from services.document_processor import vector_store
from core.config import settings

# Setup Gemini LLM
llm = ChatGoogleGenerativeAI(
    model="gemini-1.5-pro",
    google_api_key=settings.GEMINI_API_KEY,
    temperature=0.3
)

# Setup Retriever with top_k = 3
retriever = vector_store.as_retriever(search_kwargs={"k": settings.TOP_K})

# Define the Prompt
template = """Answer the question based only on the following context.
If you cannot answer the question based on the context, say "I don't know based on the provided documents. Please provide more information."

Context: {context}

Question: {question}

Answer:"""
prompt = ChatPromptTemplate.from_template(template)

def format_docs(docs: List[Document]) -> str:
    return "\n\n".join(doc.page_content for doc in docs)

# Create the RAG Chain
rag_chain = (
    {"context": retriever | format_docs, "question": RunnablePassthrough()}
    | prompt
    | llm
    | StrOutputParser()
)

async def generate_rag_response(query: str, session_history: str = "") -> Tuple[str, List[dict]]:
    # Retrieve documents separately so we can extract citations
    docs = await retriever.ainvoke(query)
    
    # Generate answer using the chain
    # We pass the question directly since context is fetched within the chain
    answer = await rag_chain.ainvoke(query)

    citations = []
    for i, doc in enumerate(docs):
        citations.append({
            "source": doc.metadata.get("source", "Unknown"),
            "content_snippet": doc.page_content[:200] + "...", 
            "page": doc.metadata.get("page")
        })

    return answer, citations
