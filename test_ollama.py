import ollama

client = ollama.Client(host="http://localhost:11434")

response = client.generate(
    model="qwen3:8b",
    prompt="Say hello.",
    stream=False,
)

print(response)