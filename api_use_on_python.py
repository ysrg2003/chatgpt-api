import openai

client = openai.OpenAI(
    API_KEY="CHANGE_ME_TO_A_STRONG_SECRET_KEY",        #the same api key in your eneroment , you set it as you prefer
    base_url="http://localhost:7860/v1"
)
response = client.chat.completions.create(
    model="",  # or gpt-4o-mini
    messages=[{"role": "user", "content":  "what is the latest Anthropic model"}],
)
print(response.choices[0].message.content)