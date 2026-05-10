import os
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI

load_dotenv()

llm = ChatOpenAI(
    model=os.getenv("CAPL_LLM_MODEL"),
    api_key=os.getenv("CAPGEMINI_API_KEY"),
    base_url=os.getenv("CAPGEMINI_BASE_URL"),
    temperature=0,
    max_tokens=512,
)

response = llm.invoke("Dis bonjour en français.")
print(response.content)