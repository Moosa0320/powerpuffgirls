import os
from harness.providers.base import ProviderError, Result, safe_call
from harness.providers.fakes import FakeLLM, FakeSTT, FakeTTS, FakeVision
from harness.providers.factory import build_chain, call_with_fallback, first_provider
from harness.llm.base import LLMReply


def test_safe_call_success() -> None:
    res = safe_call("test", lambda x: x * 2, 21)
    assert res.ok
    assert res.value == 42
    assert res.error is None


def test_safe_call_timeout() -> None:
    import time

    def slow():
        time.sleep(0.2)
        return "done"

    res = safe_call("slow_test", slow, timeout=0.05)
    assert not res.ok
    assert res.error is not None
    assert res.error.kind == "timeout"
    assert "slow_test" in res.error.provider


def test_safe_call_catches_exception() -> None:
    def buggy():
        raise ValueError("secret_internal_value")

    res = safe_call("buggy_test", buggy)
    assert not res.ok
    assert res.error is not None
    assert res.error.kind == "unavailable"
    # Never leak sensitive internals/paths
    assert "secret_internal_value" not in res.error.message


def test_fake_llm_replies() -> None:
    fake = FakeLLM(replies=['{"hello": "world"}'])
    res = fake.chat([{"role": "user", "content": "hi"}])
    assert res.ok
    assert res.value is not None
    assert res.value.content == '{"hello": "world"}'


def test_fake_stt_transcribe() -> None:
    stt = FakeSTT(text="aaj pani diya")
    res = stt.transcribe(b"fake_wav")
    assert res.ok
    assert res.value == "aaj pani diya"

    stt_fail = FakeSTT(fail=True)
    res_fail = stt_fail.transcribe(b"fake_wav")
    assert not res_fail.ok
    assert res_fail.error is not None
    assert res_fail.error.kind == "bad_response"


def test_fake_vision_and_tts() -> None:
    v = FakeVision(observation={"leaf_color": "yellow", "spots": True})
    vres = v.observe(b"fake_jpg")
    assert vres.ok
    assert vres.value["leaf_color"] == "yellow"
    assert vres.value["spots"] is True
    assert "wilting" in vres.value

    t = FakeTTS()
    tres = t.speak("hello")
    assert tres.ok
    assert tres.value == b"hello"


def test_provider_factory_fallback_chain() -> None:
    fake_reg = {
        "llm": {
            "custom": FakeLLM,
            "ollama": FakeLLM,
        }
    }
    env = {"LLM_BACKEND": "custom"}
    chain = build_chain("llm", env=env, registry=fake_reg)
    assert len(chain) >= 1

    # Call with fallback
    fake1 = FakeLLM(replies=[ValueError("provider 1 died")])
    fake2 = FakeLLM(replies=["success from fallback"])
    res = call_with_fallback([fake1, fake2], "chat", [{"role": "user", "content": "hi"}])
    assert res.ok
    assert res.value.content == "success from fallback"


def test_provider_factory_exhausted_chain() -> None:
    fake1 = FakeLLM(replies=[ValueError("err1")])
    res = call_with_fallback([fake1], "chat", [{"role": "user", "content": "hi"}])
    assert not res.ok
    assert res.error is not None
    assert "use typed input" in res.error.message
