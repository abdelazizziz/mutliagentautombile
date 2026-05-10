import os
from dotenv import load_dotenv

from langchain_openai import ChatOpenAI
from langgraph.prebuilt import create_react_agent

from langchain_tools.software_tools import software_tools


load_dotenv()


SYSTEM_PROMPT = """
You are SoftwareStudyAgent.

Your job is to analyze a CANoe software package and build a SQLite database.

Workflow:
1. Discover files from cfg_path and software_root.
2. Create database schema.
3. Populate database from manifest.
4. Validate database.
5. Return a clear summary to the user.

Do not parse DBC, LDF, CAPL, CIN, VSYSVAR or CDD yourself.
Always use the provided tools.

Use:
- outputs/manifest.json as manifest path
- outputs/project_analysis.db as database path
"""


api_key = os.getenv("CAPGEMINI_API_KEY")
base_url = os.getenv(
    "CAPGEMINI_BASE_URL",
    "https://openai.generative.engine.capgemini.com/v1",
)
model = os.getenv(
    "CAPL_LLM_MODEL",
    "us.anthropic.claude-sonnet-4-5-20250929-v1:0",
)

if not api_key:
    raise ValueError("CAPGEMINI_API_KEY is missing in .env")


llm = ChatOpenAI(
    model=model,
    api_key=api_key,
    base_url=base_url,
    temperature=0,
    max_tokens=1024,
)


config_agent = create_react_agent(
    model=llm,
    tools=software_tools,
    prompt=SYSTEM_PROMPT,
)