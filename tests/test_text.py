from __future__ import annotations

from interview_assistant.core.text import (
    correct_keywords,
    match_qa_bank,
    match_quick_response,
)


def test_keyword_correction():
    assert correct_keywords("福瑞RTOS 使用 Free RTOS", {"福瑞rtos": "FreeRTOS"}) == (
        "FreeRTOS 使用 Free RTOS"
    )


def test_quick_response():
    intro = "面试官你好，我是测试候选人。"
    assert match_quick_response("请先自我介绍一下", intro) == intro
    assert match_quick_response("讲一下项目经历", intro) is None


def test_qa_bank_matching():
    bank = [
        {
            "keywords": ["线程", "进程", "区别"],
            "answer": "线程共享进程资源。",
        }
    ]
    assert match_qa_bank("线程和进程有什么区别？", bank) == "线程共享进程资源。"
