"""Pydantic-модели structured output от LLM (Раздел 9 ТЗ)."""

from typing import Literal

from pydantic import BaseModel, Field, model_validator

PageType = Literal["concept", "decision", "gap", "idea", "source", "synthesis"]
Area = Literal["business", "personal"]
ActionType = Literal["create", "update", "none"]


class WikiAction(BaseModel):
    action: ActionType
    page_type: PageType = "idea"
    area: Area = "business"
    existing_path: str | None = None
    title: str = ""
    content: str = ""
    related_paths: list[str] = Field(default_factory=list)

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
    likely_page_type: PageType = "idea"
    possible_types: list[PageType] = Field(default_factory=lambda: ["idea"])


class WikiAnswer(BaseModel):
    answer: str
    used_sources: list[str] = Field(default_factory=list)
    knows: bool = True