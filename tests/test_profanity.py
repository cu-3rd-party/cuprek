from pathlib import Path

import pytest

from circlebot.services.profanity import ProfanityDetector

DATA_DIR = Path(__file__).resolve().parents[1] / "data"
DET = ProfanityDetector.load(DATA_DIR)

PROFANE = [
    # Russian, plain
    "да иди ты нахуй",
    "это полный пиздец",
    "не пизди мне тут",
    "ты заебал уже честно",
    "какой же он мудак",
    "да похуй мне на это",
    "офигеть, охуеть просто",
    "он спиздил мой зонт",
    # Russian, obfuscated
    "х у й тебе",
    "хуууйня какая-то",
    "х.у.й полный",
    "бл*дь как же так",
    "6лядь ну ты даёшь",
    "п0шёл на*уй",
    "да ну нахуй",
    # Russian, transliterated
    "idi nahuy otsюda",
    "polniy pizdec",
    "ty che, blyad?",
    # English
    "what the fuck is this",
    "f u c k you",
    "this is bullshit",
    "you piece of sh!t",
    "sh1t happens sometimes",
    "stop being such an asshole",
    "you dumb bitch",
    "он конченый долбоёб",
    "хватит доёбываться до меня",
]

CLEAN = [
    # Russian
    "привет, как дела?",
    "оформи страховку до пятницы",
    "запишись к психиатру на приём",
    "купил килограмм мандаринов",
    "наша команда работает отлично",
    "хлеб, молоко и яйца",
    "надо требовать отчёт с подрядчика",
    "по улице ходил верблюд",
    "подстрахуй меня на этой неделе",
    "не психуй, всё нормально",
    "у стада был вожак",
    "это классический пример",
    # English
    "this is a great classroom",
    "the grass is green today",
    "let's assess the assignment together",
    "please pass the salt",
    "Scunthorpe is a town in England",
    "we need to assign a new manager",
    "massive success for the whole class",
    "the shiitake mushrooms were tasty",
]


@pytest.mark.parametrize("text", PROFANE)
def test_profane_is_detected(text: str) -> None:
    assert DET.is_profane(text), f"missed profanity in: {text!r}"


@pytest.mark.parametrize("text", CLEAN)
def test_clean_is_not_flagged(text: str) -> None:
    assert not DET.is_profane(text), f"false positive: {text!r} -> {DET.find_match(text)!r}"


def test_empty_and_none() -> None:
    assert not DET.is_profane(None)
    assert not DET.is_profane("")
    assert not DET.is_profane("   ")


def test_find_match_returns_fragment() -> None:
    assert DET.find_match("ты мудак") is not None
    assert DET.find_match("hello there") is None
