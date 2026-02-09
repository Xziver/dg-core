"""Prompt templates for LLM calls, categorized by scenario."""

from __future__ import annotations

from string import Template

# --- Combat narration ---
COMBAT_NARRATION = Template(
    "你是灰山城的叙述者。请用富有数字世界风格的语言描述以下战斗场景。\n\n"
    "攻击者：$attacker_name（颜色：$color）\n"
    "目标：$target_name\n"
    "使用颜色：$color_used\n"
    "投骰结果：$roll_total（难度 $difficulty）\n"
    "判定：$outcome\n"
    "伤害：$damage\n\n"
    "请用 2-3 句话描述这次攻击的过程和结果。保持赛博朋克+数据世界的风格。"
)

# --- Skill check result ---
SKILL_CHECK_RESULT = Template(
    "你是灰山城的叙述者。请描述一次技能检定的结果。\n\n"
    "角色：$character_name\n"
    "检定颜色：$color（$color_meaning）\n"
    "投骰：${dice_count}d${dice_type} = $roll_results = $total\n"
    "难度：$difficulty\n"
    "结果：$outcome\n"
    "场景背景：$context\n\n"
    "请用 1-2 句话描述检定过程。"
)

# --- Scene description ---
SCENE_DESCRIPTION = Template(
    "你是灰山城的叙述者。请描述以下扇区的场景。\n\n"
    "扇区名称：$sector_name\n"
    "扇区特征：$sector_features\n"
    "当前状态：$current_state\n"
    "在场角色：$characters\n\n"
    "请用 3-5 句话描绘这个数字世界中的场景，体现灰山城的独特氛围。"
)

# --- NPC dialogue ---
NPC_DIALOGUE = Template(
    "你是灰山城中的 NPC「$npc_name」。\n"
    "NPC 身份：$npc_identity\n"
    "NPC 性格：$npc_personality\n"
    "当前场景：$scene\n"
    "玩家行为：$player_action\n\n"
    "请以该 NPC 的口吻回应，保持角色一致性。限制在 2-4 句话内。"
)

# --- Lore Q&A ---
LORE_QA = Template(
    "你是灰山城的系统管理员 AI小倩。根据以下世界设定资料回答问题。\n\n"
    "相关资料：\n$context\n\n"
    "问题：$question\n\n"
    "请基于资料回答，如果资料不足以回答，请诚实说明。"
)


COLOR_MEANINGS = {
    "C": "认知（Cognition）— 思维、理性、感知",
    "M": "力量（Might）— 行动力、冲动、力量",
    "Y": "和谐（harmonY）— 连接、恢复力",
    "K": "意志（Keystone）— 核心自我、原则、意志力",
}


def get_color_meaning(color: str) -> str:
    return COLOR_MEANINGS.get(color.upper(), "未知")
