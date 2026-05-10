from dotenv import load_dotenv
from agents.config_agent import config_agent

load_dotenv()

from dotenv import load_dotenv

# 1) Charger .env AVANT d'importer/créer l'agent
import os
from agents.config_agent import config_agent


if __name__ == "__main__":
    # 2) Vérification rapide sans afficher la clé
    print("LANGSMITH_TRACING =", os.getenv("LANGSMITH_TRACING"))
    print("LANGSMITH_PROJECT =", os.getenv("LANGSMITH_PROJECT"))
    print("LANGSMITH_API_KEY exists =", bool(os.getenv("LANGSMITH_API_KEY")))

    cfg_path = r"C:\Users\abboushi\Desktop\MDOOR_DEV_SPx_Baie2_v11 1\MDOOR_DEV_SPx_Baie2_v11\Stellantis_1605_MDOOR_V2_CANoev11.cfg"
    software_root = r"C:\Users\abboushi\Desktop\MDOOR_DEV_SPx_Baie2_v11 1\MDOOR_DEV_SPx_Baie2_v11"

    result = config_agent.invoke(
        {
            "messages": [
                (
                    "user",
                    f"""
Analyze this CANoe project and build the database.

cfg_path: {cfg_path}
software_root: {software_root}
"""
                )
            ]
        },
        config={
            "run_name": "SoftwareStudyAgent_CANoe_Project_Analysis",
            "tags": ["capl-forge", "software-study", "canoe-analysis"],
            "metadata": {
                "cfg_path": cfg_path,
                "software_root": software_root,
                "workflow": "config_agent_database_build",
            },
        },
    )

    print(result["messages"][-1].content)

# if __name__ == "__main__":
#     cfg_path = r"C:\Users\abboushi\Desktop\MDOOR_DEV_SPx_Baie2_v11 1\MDOOR_DEV_SPx_Baie2_v11\Stellantis_1605_MDOOR_V2_CANoev11.cfg"
#     software_root = r"C:\Users\abboushi\Desktop\MDOOR_DEV_SPx_Baie2_v11 1\MDOOR_DEV_SPx_Baie2_v11"

#     result = config_agent.invoke({
#         "messages": [
#             (
#                 "user",
#                 f"""
# Analyze this CANoe project and build the database.

# cfg_path: {cfg_path}
# software_root: {software_root}
# """
#             )
#         ]
#     })

#     print(result["messages"][-1].content)