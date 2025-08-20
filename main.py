# main.py (only for CLI testing, for UI run "python flaskapp.py" in terminal)

from modules.agent_orchestrator import run_agent
from modules.groq import GroqAgent
import modules.email_module as email_module

def warm_up_llm(agent_name):
    try:
        run_agent(agent_name, "Hello! (warm-up)", suppress_output=True)
    except Exception as e:
        print(f"Warm-up failed: {e}")

def main():
    print("💼 LLM Knowledge Worker Initialized.")
    agent_name = "memory_worker"

    warm_up_llm(agent_name)  

    # Create a persistent agent instance
    agent = GroqAgent(agent_name="memory_worker")

    while True:
        user_input = input("\n🧠 Prompt: ")
        if user_input.lower().strip() in ["exit", "quit","thankyou","thank you", "bye", "goodbye","thanks"]:
            print("👋 Bye..")
            break

        # Use the persistent agent instance instead of run_agent
        try:
            print(f"\n🤖 Agent: {agent_name}")
            print(f"🗣️ You: {user_input}")
            print("\n📤 Response:")
            
            response = agent.run(user_input)
            print(response)
            
        except Exception as e:
            print(f"❌ Error: {e}")

if __name__ == "__main__":
    main()