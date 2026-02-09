"""Narration rule — generate stylized text via LLM for event results."""

from __future__ import annotations

from app.domain.context import build_context
from app.models.result import DiceRollResult, EngineResult
from app.modules.llm.client import ask_llm_safe
from app.modules.llm.prompts import (
    COMBAT_NARRATION,
    SKILL_CHECK_RESULT,
    get_color_meaning,
)
from sqlalchemy.ext.asyncio import AsyncSession


async def narrate_skill_check(
    db: AsyncSession,
    session_id: str,
    character_name: str,
    color: str,
    roll_result: DiceRollResult,
    context_text: str = "",
) -> str:
    """Generate narrative text for a skill check result."""
    prompt = SKILL_CHECK_RESULT.safe_substitute(
        character_name=character_name,
        color=color.upper(),
        color_meaning=get_color_meaning(color),
        dice_count=roll_result.dice_count,
        dice_type=roll_result.dice_type,
        roll_results=" + ".join(str(r) for r in roll_result.results),
        total=roll_result.total,
        difficulty=roll_result.difficulty,
        outcome="成功" if roll_result.success else "失败",
        context=context_text or "（无额外上下文）",
    )
    return await ask_llm_safe(prompt, fallback=f"技能检定{'成功' if roll_result.success else '失败'}。")


async def narrate_combat(
    db: AsyncSession,
    session_id: str,
    attacker_name: str,
    target_name: str,
    color_used: str,
    roll_result: DiceRollResult,
    damage: int,
) -> str:
    """Generate narrative text for a combat result."""
    prompt = COMBAT_NARRATION.safe_substitute(
        attacker_name=attacker_name,
        color=get_color_meaning(color_used),
        target_name=target_name,
        color_used=color_used.upper(),
        roll_total=roll_result.total,
        difficulty=roll_result.difficulty,
        outcome="命中" if roll_result.success else "未命中",
        damage=damage,
    )
    return await ask_llm_safe(prompt, fallback=f"{'命中！' if roll_result.success else '未命中。'}")


async def enrich_result_with_narration(
    db: AsyncSession,
    session_id: str,
    result: EngineResult,
    **kwargs: str,
) -> EngineResult:
    """Add narrative text to an existing EngineResult."""
    if result.event_type == "skill_check" and result.rolls:
        result.narrative = await narrate_skill_check(
            db, session_id,
            character_name=kwargs.get("character_name", "未知角色"),
            color=result.data.get("color", "C"),
            roll_result=result.rolls[0],
            context_text=kwargs.get("context", ""),
        )
    elif result.event_type == "attack" and result.rolls:
        result.narrative = await narrate_combat(
            db, session_id,
            attacker_name=kwargs.get("attacker_name", "攻击者"),
            target_name=kwargs.get("target_name", "目标"),
            color_used=result.data.get("color_used", "C"),
            roll_result=result.rolls[0],
            damage=result.data.get("damage", 0),
        )
    return result
