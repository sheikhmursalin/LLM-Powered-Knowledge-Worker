# modules/agent_orchestrator.py

_agent_instances = {}

def run_agent(agent_name: str, user_input: str, suppress_output: bool = False) -> str:
    global _agent_instances
    
    # Reuse existing agent instance to maintain state
    if agent_name not in _agent_instances:
        if agent_name == "groq_worker" or agent_name == "memory_worker":
            from modules.groq import GroqAgent
            _agent_instances[agent_name] = GroqAgent(agent_name=agent_name)
        elif agent_name == "hf_worker":
            from modules.hf_agent import HFAgent
            _agent_instances[agent_name] = HFAgent(agent_name=agent_name)
        else:
            raise ValueError(f"Unknown agent: {agent_name}")
    
    agent = _agent_instances[agent_name]
    
    if not suppress_output:
        print(f"\n🤖 Agent: {agent_name}")
        print(f"🗣️ You: {user_input}")
        print("\n📤 Response:")
    
    try:
        response = agent.run(user_input)
        if not suppress_output:
            print(response)
        return response
    except Exception as e:
        error_msg = f"❌ Error: {e}"
        if not suppress_output:
            print(error_msg)
        return error_msg

# CLI interface (optional for testing)
if __name__ == "__main__":
    agent_name = "groq_worker"  # Default for CLI
    while True:
        try:
            user_input = input("🧠 Prompt: ")
            if user_input.strip().lower() in ["exit", "quit","thankyou","thank you", "bye", "goodbye","thanks"]:
                break
            run_agent(agent_name, user_input)
        except KeyboardInterrupt:
            print("\n👋 Bye..")
            break
