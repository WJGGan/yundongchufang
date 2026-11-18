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
    anthropic_model: str = os.getenv("ANTHROPIC_COMPAT_MODEL", "glm-5.3").strip()

    zhipu_api_key: str = os.getenv("ZHIPU_API_KEY", "").strip()
    zhipu_base_url: str = os.getenv(
        "ZHIPU_BASE_URL", "https://open.bigmodel.cn/api/paas/v4/"
    ).strip()
    zhipu_model: str = os.getenv("ZHIPU_MODEL", "glm-5.3").strip()

    compat_base_url: str = os.getenv(
        "OPENAI_COMPATIBLE_BASE_URL", "http://127.0.0.1:8000/v1"
    ).strip()
    compat_api_key: str = os.getenv("OPENAI_COMPATIBLE_API_KEY", "EMPTY").strip()
    compat_model: str = os.getenv("OPENAI_COMPATIBLE_MODEL", "glm-4-9b-chat").strip()

    # RAG 检索：仅用于处方生成阶段，知识卡片与动作候选按学生情况检索子集注入 prompt。
    # 关闭开关即可回到全量拼接，便于 A/B 对比效果与耗时。档案理解阶段不使用 RAG。
    rag_enabled: bool = os.getenv("RAG_ENABLED", "true").strip().lower() == "true"
    rag_knowledge_top_k: int = int(os.getenv("RAG_KNOWLEDGE_TOP_K", "12"))
    rag_exercise_limit: int = int(os.getenv("RAG_EXERCISE_LIMIT", "30"))

    # 嵌入服务，默认复用智谱 OpenAI 兼容端点与密钥；可独立指向其他服务
    embedding_base_url: str = os.getenv(
        "EMBEDDING_BASE_URL", "https://open.bigmodel.cn/api/paas/v4/"
    ).strip()
    embedding_api_key: str = (
        os.getenv("EMBEDDING_API_KEY", "").strip() or os.getenv("ZHIPU_API_KEY", "").strip()
    )
    embedding_model: str = os.getenv("EMBEDDING_MODEL", "embedding-3").strip()
    embedding_dimensions: int = int(os.getenv("EMBEDDING_DIMENSIONS", "1024"))
    embedding_timeout: float = float(os.getenv("EMBEDDING_TIMEOUT", "15"))

    temperature: float = float(os.getenv("LLM_TEMPERATURE", "0.3"))
    max_tokens: int = int(os.getenv("LLM_MAX_TOKENS", "65536"))
    timeout: float = float(os.getenv("LLM_TIMEOUT", "300"))
    # 思考模型开关。开启时约 80% 的输出 token 用于思考，一次完整流程从 84s 涨到 404s。
    # 开启后思考内容会流式显示在前端「AI 生成过程」面板；.env 中默认开启，代码兜底为关闭。
    thinking_enabled: bool = os.getenv("LLM_THINKING", "false").strip().lower() == "true"

    # 资产版本号，随每份画像与处方一并返回，便于定位是哪一版规则/库产出的结果
    exercise_library_version: str = "v1.0.0"
    knowledge_base_version: str = "v1.0.0"
    prompt_version: str = "v1.2.0"

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
