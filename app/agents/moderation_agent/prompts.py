MODERATION_SYSTEM_PROMPT = """You are a YouTube content compliance specialist with deep expertise in
YouTube Community Guidelines, copyright law, spam policies, and advertiser-friendly content standards.

Your job is to review scripts before upload and flag any content that could:
- Get the video demonetised or removed
- Trigger a copyright claim
- Violate YouTube's spam or misleading metadata policies
- Result in channel strikes or termination

You are thorough but fair — you do not flag legitimate educational content.
Risk scores above 70 on any dimension should trigger a flag.

Always respond with valid JSON only. No markdown. No preamble."""


def build_moderation_prompt(
    script_content: str,
    script_type: str,
    topic_title: str,
    niche: str,
    seo_title: str,
    seo_description: str,
    tags: list[str],
) -> str:
    tags_str = ", ".join(tags[:20]) if tags else "none"
    excerpt = script_content[:1200]
    desc_excerpt = seo_description[:300] if seo_description else ""

    return f"""Review this YouTube content package for compliance and safety:

TITLE: "{seo_title or topic_title}"
TOPIC: "{topic_title}"
FORMAT: {"YouTube Shorts" if script_type == "short" else "long-form YouTube video"}
NICHE: {niche}
TAGS: {tags_str}

DESCRIPTION (excerpt):
{desc_excerpt}

SCRIPT (excerpt):
---
{excerpt}
---

Evaluate each risk dimension 0-100 (0=no risk, 100=definite violation):

1. copyright_risk — reuses song lyrics, movie dialogue, trademarked phrases,
   reproduces copyrighted tutorials verbatim, or makes unsubstantiated claims
   about proprietary technology

2. duplicate_risk — content appears to be scraped, paraphrased from a single source,
   or substantially identical to common existing content

3. spam_risk — misleading title/tags (clickbait that doesn't match content),
   keyword stuffing in description, artificially inflated engagement bait

4. policy_risk — hate speech, harassment, dangerous challenges, medical misinformation,
   election misinformation, graphic violence, adult content, or regulated products

5. monetization_risk — profanity, controversial topics that demonetise (politics,
   tragedy, war), explicit drug/alcohol/gambling references, shocking thumbnails

Flag a dimension if its score >= 70.
Set approved=true only if NO dimension is flagged.

Return ONLY valid JSON:
{{
  "copyright_risk_score": 5.0,
  "duplicate_risk_score": 10.0,
  "spam_risk_score": 8.0,
  "policy_risk_score": 3.0,
  "monetization_risk_score": 12.0,
  "copyright_risk": false,
  "duplicate_content": false,
  "spam_risk": false,
  "policy_violation": false,
  "monetization_unsafe": false,
  "overall_risk_score": 12.0,
  "approved": true,
  "rejection_reasons": [],
  "recommendations": [
    "Consider adding chapter timestamps to improve user experience"
  ],
  "reviewer_notes": "Clean educational content, no compliance issues found."
}}

If any flag is true, explain why in rejection_reasons.
JSON only."""