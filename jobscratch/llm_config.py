#!/usr/bin/env python3
"""LLM 配置层 — 从 JSON 文件加载大模型接入配置。"""

import json
import os

DEFAULT_LLM_CONFIG_PATH = os.path.expanduser("~/.jobscratch/llm_config.json")

# 配置搜索顺序:用户目录标准位置优先,项目内本地文件兜底
CONFIG_PATH_CANDIDATES = (
    DEFAULT_LLM_CONFIG_PATH,
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "llm_config.json"),
)

REQUIRED_FIELDS = ("base_url", "api_key", "model")


class LLMConfig:
    """大模型接入配置,从 JSON 文件加载,字段缺失时保留默认值。"""

    def __init__(self, config_path=None):
        self.base_url = ""
        self.api_key = ""
        self.model = ""
        self.temperature = 0.3
        self.max_tokens = 4000
        self.config_path = ""
        self._load(config_path or self._find_existing_config())

    # ------------------------------------------------------------
    # 加载
    # ------------------------------------------------------------

    def _find_existing_config(self):
        """按搜索顺序返回第一个存在的配置文件,找不到则返回默认路径。"""
        for path in CONFIG_PATH_CANDIDATES:
            if os.path.isfile(path):
                return path
        return DEFAULT_LLM_CONFIG_PATH

    def _load(self, path):
        if not os.path.isfile(path):
            print(f"⚠️  LLM 配置文件不存在: {path} (使用默认值)")
            return
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError) as e:
            print(f"⚠️  LLM 配置文件解析失败: {path} ({e}) (使用默认值)")
            return
        self.config_path = path
        for key in ("base_url", "api_key", "model"):
            if data.get(key):
                setattr(self, key, str(data[key]))
        if data.get("temperature") is not None:
            self.temperature = float(data["temperature"])
        if data.get("max_tokens") is not None:
            self.max_tokens = int(data["max_tokens"])

    # ------------------------------------------------------------
    # 校验
    # ------------------------------------------------------------

    def validate(self):
        """必填项缺失时抛 RuntimeError,提示先创建配置文件。"""
        missing = [k for k in REQUIRED_FIELDS if not getattr(self, k)]
        if missing:
            raise RuntimeError(
                f"LLM 配置缺少必填项: {', '.join(missing)}。"
                f"请先创建配置文件 {DEFAULT_LLM_CONFIG_PATH}"
            )
        if not self.api_key.strip().lower().startswith("sk-"):
            raise RuntimeError(
                f"LLM 配置 api_key 格式异常(应以 sk- 开头): {self.api_key[:8]}..."
            )

    def __repr__(self):
        key = f"{self.api_key[:8]}..." if self.api_key else "(空)"
        return (f"LLMConfig(base_url={self.base_url!r}, api_key={key}, "
                f"model={self.model!r}, path={self.config_path!r})")


if __name__ == "__main__":
    cfg = LLMConfig()
    print(cfg)
    try:
        cfg.validate()
        print("✅ LLM 配置校验通过")
    except RuntimeError as e:
        print(f"❌ {e}")