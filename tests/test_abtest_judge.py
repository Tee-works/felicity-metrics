import math

from felicity import abtest, judge


def test_two_proportion_known_values():
    # matches R: prop.test(c(60, 50), c(100, 100), correct = FALSE), X-squared = 2.0202, p = 0.1552
    t = abtest.two_proportion_test(50, 100, 60, 100)
    assert math.isclose(t.z, 1.4213, abs_tol=1e-3)
    assert math.isclose(t.p_value, 0.1552, abs_tol=1e-3)
    assert t.ci_low < t.diff < t.ci_high


def test_srm_and_power():
    assert abtest.srm_check(5000, 5000) == 1.0
    assert abtest.srm_check(5000, 5400) < 0.001
    assert 380 <= abtest.required_n_per_arm(0.5, 0.1) <= 400


def conv(enq, turns):
    return judge.Conversation("CVTEST", enq, [judge.Turn(s, b) for s, b in turns])


def test_heuristic_judge_rules():
    c = conv("lettings", [("customer", "Is the flat free?"), ("felicity", "When are you looking to move in?"),
                          ("customer", "January"), ("felicity", "I can book you a viewing on Tuesday.")])
    s = judge.HeuristicJudge().score(c)
    assert (s.details_captured, s.next_step_offered, s.safe_escalation) == (1, 1, None)
    urgent = conv("maintenance", [("customer", "There's a strong smell of gas"), ("felicity", "I've logged this.")])
    assert judge.HeuristicJudge().score(urgent).safe_escalation == 0


def test_llm_judge_without_model_falls_back():
    j = judge.LLMJudge()
    s = j.score(conv("sales", [("customer", "hi"), ("felicity", "Are you a cash buyer?")]))
    assert "fallback" in s.judge and s.details_captured == 1


def test_llm_judge_with_model_and_bad_output():
    good = judge.LLMJudge(complete=lambda p: '{"details_captured": 0, "next_step_offered": 1, "safe_escalation": null, "rationale": "ok"}',
                          model_name="fake-model")
    c = conv("lettings", [("customer", "hi"), ("felicity", "When are you looking to move in?")])
    s = good.score(c)
    assert (s.details_captured, s.next_step_offered, s.judge) == (0, 1, "fake-model")
    assert "[PHONE]" in judge.LLMJudge().build_prompt(conv("lettings", [("customer", "[PHONE]")]))
    bad = judge.LLMJudge(complete=lambda p: "not json", model_name="fake-model")
    assert "unparseable" in bad.score(c).judge
