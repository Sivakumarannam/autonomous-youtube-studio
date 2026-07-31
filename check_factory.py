from app.llm_providers.factory import get_llm_provider

provider = get_llm_provider()

print("Provider Type:", type(provider))
print("Provider Name:", provider.provider_name)