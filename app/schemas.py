"""Pydantic-модели structured output от LLM (Раздел 9 ТЗ)."""

import re
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

Area = Literal["business", "personal"]
ActionType = Literal["create", "update", "none"]


def normalize_page_type(value: str) -> str:
    """Нормализует тип страницы для имени каталога.

    Список типов в AGENTS.md не исчерпывающий, поэтому тип — свободная строка,
    а не Literal. Пустой тип трактуется как ``idea``.
    """
    text = (value or "").strip().lower()
    text = re.sub(r"[\s/\\]+", "-", text)
    text = re.sub(r"[^a-z0-9\u0400-\u04ff-]", "", text)
    text = re.sub(r"-{2,}", "-", text).strip("-")
    return text or "idea"


class WikiAction(BaseModel):
    action: ActionType
    page_type: str = "idea"
    area: Area = "business"
    existing_path: str | None = None
    title: str = ""
    content: str = ""
    related_paths: list[str] = Field(default_factory=list)

    @field_validator("page_type")
    @classmethod
    def _normalize_page_type(cls, value: str) -> str:
        return normalize_page_type(value)

    @model_validator(mode="after")
    def _check_action(self) -> "WikiAction":
        if self.action in {"create", "update"} and not (
            self.title.strip() and self.content.strip()
        ):
            raise ValueError("для create/update нужны title и content")
        if self.action == "update" and not self.existing_path:
            raise ValueError("для update требуется existing_path")
        return self


class WikiPlan(BaseModel):
    summary: str = ""
    actions: list[WikiAction]


class TopicAnalysis(BaseModel):
    """Анализ темы: термины для поиска и вероятные типы страниц.

    Python использует search_terms для локального поиска (Раздел 21),
    а possible_types — чтобы передать LLM только нужные templates (Раздел 22).
    """

    topic: str = ""
    search_terms: list[str] = Field(default_factory=list)
    related_concepts: list[str] = Field(default_factory=list)
    likely_page_type: str = "idea"
    possible_types: list[str] = Field(default_factory=lambda: ["idea"])

    @field_validator("likely_page_type")
    @classmethod
    def _normalize_likely_page_type(cls, value: str) -> str:
        return normalize_page_type(value)

    @field_validator("possible_types")
    @classmethod
    def _normalize_possible_types(cls, values: list[str]) -> list[str]:
        return [normalize_page_type(value) for value in values]


class WikiAnswer(BaseModel):
    answer: str
    used_sources: list[str] = Field(default_factory=list)
    knows: bool = True