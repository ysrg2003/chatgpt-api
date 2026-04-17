import openai

client = openai.OpenAI(
    api_key="gptkey0",        #the same api key in your environment; set as you prefer
    base_url="https://yousefsg-chatgpt-api.hf.space/v1"
)
response = client.chat.completions.create(
    model="",  # or gpt-4o-mini
    messages=[{"role": "user", "content":  "what is the latest Anthropic model"}],
)
print(response.choices[0].message.content)