import ollama

class LocalLlamaAdapter:
    def __init__(self, model_name: str):
        self.model_name = model_name

    def generate(self, prompt: str) -> str:
        print(f"⏳ Loading {self.model_name} and generating response...") # NEW
        try:
            response = ollama.chat(
                model=self.model_name,
                messages=[{'role': 'user', 'content': prompt}]
            )
            print(f"✅ {self.model_name} complete.") # NEW
            return response['message']['content']
        except Exception as e:
            return f"ERROR: Infrastructure failure - {str(e)}"