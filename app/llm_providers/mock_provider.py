import json
from typing import Optional
from app.llm_providers.base import BaseLLMProvider, LLMMessage, LLMResponse


MOCK_RESPONSES = {
    "topic": json.dumps([
        {"topic": "Docker vs Kubernetes: Which Should You Use in 2024?", "score": 95, "reason": "High search volume and trending in DevOps community"},
        {"topic": "Python FastAPI vs Django: Performance Comparison", "score": 88, "reason": "Rising interest in Python web frameworks"},
        {"topic": "GitHub Actions CI/CD Complete Guide", "score": 85, "reason": "DevOps automation is trending"},
        {"topic": "Linux Terminal Tricks That Save Hours", "score": 82, "reason": "Developer productivity content performs well"},
        {"topic": "Building REST APIs with Python in 10 Minutes", "score": 80, "reason": "Beginner-friendly tutorial with high search volume"},
    ]),
    "research": json.dumps({
        "summary": "This topic covers the comparison between two major containerization technologies. Docker focuses on container creation and management while Kubernetes handles container orchestration at scale.",
        "key_facts": [
            "Docker was created in 2013 by Solomon Hykes",
            "Kubernetes was released by Google in 2014",
            "Over 80% of companies using containers use Kubernetes for orchestration",
            "Docker Desktop has over 20 million users",
            "Kubernetes manages containerized workloads and services"
        ],
        "references": [
            "https://docs.docker.com",
            "https://kubernetes.io/docs",
            "https://www.cncf.io/reports"
        ]
    }),
    "short_script": """HOOK: Did you know Docker and Kubernetes are NOT the same thing?

BODY: Docker creates containers. Kubernetes orchestrates them. Think of Docker as a shipping container and Kubernetes as the entire port managing thousands of containers.

For small apps? Use Docker alone. For scaling to millions of users? That's when you need Kubernetes.

CTA: Follow for more DevOps tips that will level up your career!""",
    "long_script": """# Docker vs Kubernetes: Which Should You Use?

## INTRODUCTION
Welcome back to the channel! Today we're settling one of the biggest debates in the DevOps world: Docker versus Kubernetes. By the end of this video, you'll know exactly which one to use and when.

## WHAT IS DOCKER?
Docker is a containerization platform that lets you package your application and all its dependencies into a single unit called a container. Created in 2013, Docker revolutionized how we ship software by ensuring it runs the same way everywhere.

### Key Docker Features:
- Container creation and management
- Docker Hub for image sharing
- Docker Compose for multi-container apps
- Simple learning curve

## WHAT IS KUBERNETES?
Kubernetes, or K8s, is an open-source container orchestration system developed by Google and released in 2014. It automates the deployment, scaling, and management of containerized applications.

### Key Kubernetes Features:
- Automatic scaling
- Self-healing containers
- Load balancing
- Rolling updates and rollbacks

## HEAD TO HEAD COMPARISON
Let's compare them across five key areas.

### 1. Complexity
Docker is significantly easier to learn. You can be productive in hours. Kubernetes has a steep learning curve and typically takes weeks to master.

### 2. Scalability
Docker handles single-host scenarios well. Kubernetes excels at managing hundreds or thousands of containers across multiple machines.

### 3. Use Case
Use Docker for development, testing, and small production deployments. Use Kubernetes when you need high availability, auto-scaling, and managing complex microservices.

### 4. Resource Requirements
Docker is lightweight. Kubernetes requires substantial infrastructure overhead.

### 5. Community & Ecosystem
Both have massive communities. Kubernetes has become the industry standard for container orchestration.

## REAL WORLD EXAMPLES
Companies like Netflix, Spotify, and Airbnb use Kubernetes to manage thousands of containers. Startups and small teams often stick with Docker Compose.

## CONCLUSION
Here's the bottom line: Docker and Kubernetes aren't competing, they're complementary. Docker creates containers. Kubernetes manages them at scale. Start with Docker, learn Kubernetes when you're ready to scale.

## CALL TO ACTION
If this helped you, smash that like button and subscribe for weekly DevOps tutorials. Drop a comment below telling me which one you're currently using!""",
    "seo": json.dumps({
        "title": "Docker vs Kubernetes: Complete Comparison Guide 2024",
        "description": "Learn the key differences between Docker and Kubernetes. Understand when to use each technology, compare their features, and make the right choice for your project. Perfect for beginners and experienced developers.",
        "tags": ["docker", "kubernetes", "devops", "containers", "docker tutorial", "kubernetes tutorial", "container orchestration", "cloud native", "microservices", "docker vs kubernetes"],
        "hashtags": ["#Docker", "#Kubernetes", "#DevOps", "#CloudNative", "#Containers", "#Programming", "#Tech"]
    }),
    "quality": json.dumps({
        "grammar_score": 92.0,
        "fact_consistency_score": 88.0,
        "engagement_score": 85.0,
        "retention_score": 80.0,
        "seo_score": 90.0,
        "uniqueness_score": 78.0,
        "readability_score": 88.0,
        "overall_score": 86.0,
        "passed": True,
        "feedback": "Strong script with good structure. Hook is engaging. Consider adding more specific statistics."
    }),
    "thumbnail": json.dumps({
        "concept": "Split screen design: Docker whale logo on left with blue background, Kubernetes helm wheel on right with dark purple background. Bold white text 'Docker vs K8s' in center. Red VS badge. Clean, high contrast design optimized for thumbnail visibility."
    }),
    "voice": json.dumps({
        "audio_file_path": "storage/audio/mock-voice.mp3",
        "duration_seconds": 24.0,
        "word_count": 80,
        "provider_used": "mock"
    }),
    "video": json.dumps({
        "title": "Docker vs Kubernetes: The Ultimate Guide",
        "summary": "A polished explainer video with a hook, comparison, and CTA.",
        "scenes": [
            {"title": "Hook", "description": "Open with the main conflict", "duration_seconds": 10},
            {"title": "Comparison", "description": "Break down the key differences", "duration_seconds": 20}
        ],
        "edits": ["Add intro hook", "Add comparison overlays", "Add CTA"],
        "duration_seconds": 30
    }),
    "upload": json.dumps({
        "title": "Docker vs Kubernetes: The Ultimate Guide",
        "description": "A concise comparison video for developers learning containers.",
        "tags": ["docker", "kubernetes", "devops", "tutorial"],
        "status": "ready"
    }),
    "analytics": json.dumps({
        "summary": "The topic performed well with steady retention and strong engagement.",
        "recommendations": ["Post more comparison videos", "Use stronger hooks in intros"],
        "engagement_rate": 8.4,
        "score": 82.5
    }),
    "feedback": json.dumps({
        "winning_topics": ["Docker", "Kubernetes", "Python"],
        "recommendations": [
            "Docker content gets 40% more views than average - generate more Docker tutorials",
            "Python beginner content has highest retention rate - prioritize beginner series",
            "Avoid Linux topics - below average engagement for this channel"
        ],
        "suggested_topics": [
            "Docker Compose Tutorial for Beginners",
            "Python Decorators Explained Simply",
            "FastAPI vs Flask: Which is Faster?"
        ]
    }),
    "moderation": json.dumps({
        "copyright_risk_score": 5.0,
        "duplicate_risk_score": 8.0,
        "spam_risk_score": 4.0,
        "policy_risk_score": 3.0,
        "monetization_risk_score": 10.0,
        "copyright_risk": False,
        "duplicate_content": False,
        "spam_risk": False,
        "policy_violation": False,
        "monetization_unsafe": False,
        "overall_risk_score": 10.0,
        "approved": True,
        "rejection_reasons": [],
        "recommendations": [
            "Consider adding chapter timestamps to improve user experience",
            "Ensure thumbnail text matches video title exactly"
        ],
        "reviewer_notes": "Clean educational content. No compliance issues found. Safe for monetisation."
    }),
    "default": "This is a mock response from the MockProvider. Configure a real LLM provider using the LLM_PROVIDER environment variable."
}


class MockLLMProvider(BaseLLMProvider):
    """Mock LLM provider for development and testing."""

    @property
    def provider_name(self) -> str:
        return "mock"

    def _select_response(self, prompt: str) -> str:
        prompt_lower = prompt.lower()
        if "topic" in prompt_lower or "trend" in prompt_lower:
            return MOCK_RESPONSES["topic"]
        elif "research" in prompt_lower or "summarize" in prompt_lower or "fact" in prompt_lower:
            return MOCK_RESPONSES["research"]
        elif "short script" in prompt_lower or "shorts" in prompt_lower:
            return MOCK_RESPONSES["short_script"]
        elif "long script" in prompt_lower or "long-form" in prompt_lower or "long form" in prompt_lower:
            return MOCK_RESPONSES["long_script"]
        elif "seo" in prompt_lower or "title" in prompt_lower or "description" in prompt_lower or "tag" in prompt_lower:
            return MOCK_RESPONSES["seo"]
        elif "quality" in prompt_lower or "grammar" in prompt_lower or "score" in prompt_lower:
            return MOCK_RESPONSES["quality"]
        elif "thumbnail" in prompt_lower or "image" in prompt_lower:
            return MOCK_RESPONSES["thumbnail"]
        elif "voice" in prompt_lower or "speech" in prompt_lower or "tts" in prompt_lower or "audio" in prompt_lower:
            return MOCK_RESPONSES["voice"]
        elif "video" in prompt_lower or "scene" in prompt_lower or "edit" in prompt_lower:
            return MOCK_RESPONSES["video"]
        elif "upload" in prompt_lower or "youtube" in prompt_lower:
            return MOCK_RESPONSES["upload"]
        elif "analytic" in prompt_lower or "report" in prompt_lower or "engagement" in prompt_lower:
            return MOCK_RESPONSES["analytics"]
        elif "feedback" in prompt_lower or "recommend" in prompt_lower:
            return MOCK_RESPONSES["feedback"]
        elif "moderat" in prompt_lower or "copyright" in prompt_lower or "policy" in prompt_lower or "compliance" in prompt_lower:
            return MOCK_RESPONSES["moderation"]
        return MOCK_RESPONSES["default"]

    async def generate(
        self,
        messages: list[LLMMessage],
        system: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> LLMResponse:
        combined = " ".join([m.content for m in messages])
        if system:
            combined = system + " " + combined
        content = self._select_response(combined)
        return LLMResponse(
            content=content,
            model="mock-model",
            input_tokens=len(combined.split()),
            output_tokens=len(content.split()),
            provider="mock",
        )

    async def generate_text(
        self,
        prompt: str,
        system: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> str:
        combined = (system or "") + " " + prompt
        return self._select_response(combined)