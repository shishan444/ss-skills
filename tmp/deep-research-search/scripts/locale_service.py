"""多语言服务（LocaleService）

环境层（CDP 原生，让搜索引擎真正返回对应语言/地区结果）：
  - Emulation.setLocaleOverride  → navigator.language / Intl
  - Emulation.setUserAgentOverride(acceptLanguage) → 网络请求 Accept-Language

查询层（搜索词语言变体）由 LLM 在搜索词设计阶段处理（research-loop），本模块只透传。
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from cdp_client import CdpClient

# 语言预设：locale + Accept-Language + UA 指示
LOCALE_PRESETS = {
    'zh-CN': {'locale': 'zh-CN', 'acceptLanguage': 'zh-CN,zh;q=0.9,en;q=0.8'},
    'en-US': {'locale': 'en-US', 'acceptLanguage': 'en-US,en;q=0.9'},
    'ja-JP': {'locale': 'ja-JP', 'acceptLanguage': 'ja-JP,ja;q=0.9,en;q=0.8'},
    'de-DE': {'locale': 'de-DE', 'acceptLanguage': 'de-DE,de;q=0.9,en;q=0.8'},
}


def apply_locale(client: CdpClient, target_id, locale='zh-CN', user_agent=None):
    """对 tab 应用语言环境（Emulation locale + UA acceptLanguage）。"""
    preset = LOCALE_PRESETS.get(locale, {'locale': locale, 'acceptLanguage': locale})
    return client.set_locale(
        target_id,
        locale=preset.get('locale', locale),
        acceptLanguage=preset.get('acceptLanguage'),
        user_agent=user_agent,
    )
