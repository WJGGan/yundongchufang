"""运行配置。所有可调项集中在此，便于交付期替换为本地推理服务。"""

import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
FRONTEND_DIR = BASE_DIR.parent.parent / "frontend"

load_dotenv(BASE_DIR.parent / ".env")


class Settings:
    """进程级配置，启动时读取一次。"""

    llm_provider: str = os.getenv("LLM_PROVIDER", "zhipu").strip().lower()

    # 智谱 Anthropic 兼容端点
    anthropic_base_url: str = os.getenv(
        "ANTHROPIC_COMPAT_BASE_URL", "https://open.bigmodel.cn/api/anthropic"
    ).strip()
    anthropic_api_key: str = os.getenv("ANTHROPIC_COMPAT_API_KEY", "").strip()
    anthropic_model: str = os.getenv("ANTHROPIC_COMPAT_MODEL", "glm-4.6").strip()

    zhipu_api_key: str = os.getenv("ZHIPU_API_KEY", "").strip()
    zhipu_base_url: str = os.getenv(
        "ZHIPU_BASE_URL", "https://open.bigmodel.cn/api/paas/v4/"
    ).strip()
    zhipu_model: str = os.getenv("ZHIPU_MODEL", "glm-4.6").strip()

    compat_base_url: str = os.getenv(
        "OPENAI_COMPATIBLE_BASE_URL", "http://127.0.0.1:8000/v1"
    ).strip()
    compat_api_key: str = os.getenv("OPENAI_COMPATIBLE_API_KEY", "EMPTY").strip()
    compat_model: str = os.getenv("OPENAI_COMPATIBLE_MODEL", "glm-4-9b-chat").strip()

    temperature: float = float(os.getenv("LLM_TEMPERATURE", "0.3"))
    max_tokens: int = int(os.getenv("LLM_MAX_TOKENS", "16384"))
    timeout: float = float(os.getenv("LLM_TIMEOUT", "300"))
    # GLM-4.6 等思考模型：开启思考会先消耗 token 产出推理过程，需预留更大的 max_tokens
    thinking_enabled: bool = os.getenv("LLM_THINKING", "true").strip().lower() == "true"

    # 资产版本号，随每份画像与处方一并返回，便于定位是哪一版规则/库产出的结果
    exercise_library_version: str = "v1.0.0"
    knowledge_base_version: str = "v1.0.0"
    prompt_version: str = "v1.0.0"

    @property
    def active_model(self) -> str:
        if self.llm_provider == "zhipu":
            return self.zhipu_model
        if self.llm_provider == "anthropic_compatible":
            return self.anthropic_model
        if self.llm_provider == "openai_compatible":
            return self.compat_model
        return "mock"


settings = Settings()
