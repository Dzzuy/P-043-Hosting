"""Executable specs for config-driven outcomes and two independent abuse layers."""

from copy import deepcopy
from dataclasses import replace

import httpx
import pytest
from fastapi import FastAPI

from src.agents.roleplay.customer_agent import CustomerAgent, CustomerResponseError
from src.agents.roleplay.graph import RoleplayGraph, RoleplaySessionConflictError
from src.agents.roleplay.guardrails import check_advisor_message
from src.agents.roleplay.scenario_loader import ScenarioRepository
from src.agents.roleplay.state import (
    ConversationStage,
    EvaluationStatus,
    LinkedBenefit,
    RoleplayMessage,
    RoleplayState,
    TerminationStatus,
)
from src.agents.roleplay.state_reducer import apply_turn_analysis
from src.agents.roleplay.turn_analyzer import TurnAnalysis, TurnAnalyzer
from src.api.practice import create_practice_router
from src.integrations.practice_runtime import _turn_analysis_context
from src.services.practice import PracticeService

SCENARIO_ID = "SCENARIO_04_VF6_ECO_PLUS_UPSELL"
UPSELL = "OBJ_VF6_PLUS_WORTH"
ELIGIBILITY = "OBJ_VF6_PROMO_ELIGIBILITY"


class Checkpoint:
    def __init__(self):
        self.states = {}

    async def load(self, key):
        return deepcopy(self.states.get(key))

    async def save(self, key, value):
        self.states[key] = deepcopy(value)


class CustomerModel:
    def __init__(self, *outputs):
        self.outputs = list(outputs)
        self.calls = 0

    async def generate(self, **kwargs):
        self.calls += 1
        return self.outputs.pop(0)


class AnalysisModel:
    def __init__(self, *outputs):
        self.outputs = list(outputs)
        self.calls = 0

    async def analyze(self, *args):
        self.calls += 1
        return self.outputs.pop(0)


def runtime(*, analyses=(), replies=()):
    repository = ScenarioRepository()
    customer = CustomerModel(*replies)
    analysis = AnalysisModel(*analyses)
    checkpoint = Checkpoint()
    graph = RoleplayGraph(repository, TurnAnalyzer(analysis), CustomerAgent(customer), checkpoint)
    return graph, checkpoint, customer, analysis


@pytest.fixture
def scenario():
    return ScenarioRepository().get(SCENARIO_ID)


@pytest.fixture
def state(scenario):
    return RoleplayState.from_scenario("session", scenario)


def links(*ids):
    needs = {"airbags_7": "family_usage", "motor_150kw": "weekend_trips", "camera_360": "parking"}
    return [LinkedBenefit(benefit_id=key, need_fact_key=needs[key]) for key in ids]


@pytest.mark.parametrize("reply", ["Dạ được ạ, chị đủ điều kiện", "Được", "Dạ có", "Đúng rồi ạ"])
@pytest.mark.asyncio
async def test_eligibility_confirmation_after_two_prompts_resolves_without_dropout(scenario, reply):
    graph, checkpoint, customer, analyzer = runtime(
        analyses=[
            {
                "factual_claims": [{"text": "Eco giá 646 triệu", "category": "price"}],
                "detected_intents": ["ask_current_vehicle_or_promo"],
                "discovered_fact_ids": ["current_vehicle"],
            },
            {},
            {},
            {"addressed_objection_ids": [ELIGIBILITY], "resolved_objection_ids": [ELIGIBILITY]},
        ],
        replies=[
            {
                "reply": "Em kiểm tra giúp chị xem xe máy xăng đứng tên chị có được áp dụng ưu đãi không nhé?",
                "raised_objection_id": ELIGIBILITY,
            },
            {
                "reply": "Xe máy xăng đứng tên chị có được tính vào điều kiện nhận ưu đãi không em?",
                "raised_objection_id": ELIGIBILITY,
            },
            {
                "reply": "Chị có xe máy xăng đứng tên chị, vậy chị có đủ điều kiện không em?",
                "raised_objection_id": ELIGIBILITY,
            },
            {"reply": "Vậy chị xem tiếp bản Eco nhé."},
        ],
    )
    await graph.start("session", SCENARIO_ID)
    await graph.continue_session("session", "Eco giá 646 triệu. Chị đang đi xe gì?")
    await graph.continue_session("session", "Để em kiểm tra.")
    await graph.continue_session("session", "Em đang xem lại điều kiện.")
    before = await graph.get_session_state("session")
    assert ELIGIBILITY in before.active_objections
    assert before.concern_prompt_counts[ELIGIBILITY] == 2
    context = _turn_analysis_context(reply, scenario, before)
    assert context["state"]["recent_messages"][-1]["content"] == before.messages[-1].content

    view = await graph.continue_session("session", reply)
    after = RoleplayState.model_validate(await checkpoint.load("session"))
    assert view["termination_status"] == TerminationStatus.ACTIVE.value
    assert after.resolved_objections == [ELIGIBILITY]
    assert ELIGIBILITY not in after.active_objections
    assert ELIGIBILITY not in after.unresolved_objections
    assert after.policy_mentions == []
    assert UPSELL in after.unresolved_objections
    assert after.messages[-1].content == "Vậy chị xem tiếp bản Eco nhé."
    assert customer.calls == analyzer.calls == 4


@pytest.mark.parametrize(
    "fact_key,intent,question",
    [
        ("family_usage", "ask_daily_usage", "Chị dùng xe hằng ngày vào việc gì, chở ai?"),
        ("weekend_trips", "ask_long_trips", "Cuối tuần chị có đi xa hay về quê không?"),
        ("priorities", "ask_priorities", "Khi chọn xe chị ưu tiên điều gì nhất?"),
    ],
)
@pytest.mark.asyncio
async def test_usage_needs_are_spoken_only_after_relevant_discovery(scenario, fact_key, intent, question):
    graph, _, customer, _ = runtime(
        analyses=[{}, {"detected_intents": [intent], "discovered_fact_ids": [fact_key]}],
        replies=[{"reply": "Chào em, chị đang tìm hiểu VF 6 Eco. Ưu đãi đó thế nào em?"}],
    )
    await graph.start("session", SCENARIO_ID)
    await graph.continue_session("session", "Chào chị, VF 6 đang có ưu đãi tốt.")
    before = await graph.get_session_state("session")
    assert before.revealed_facts == []
    view = await graph.continue_session("session", question)
    after = await graph.get_session_state("session")
    assert after.revealed_facts == [fact_key]
    assert set(after.spoken_fact_message_ids) == {fact_key}
    assert view["messages"][-1]["content"] == scenario.hidden_facts[fact_key]
    assert customer.calls == 1  # Discovery uses the configured disclosure, without generation.


@pytest.mark.parametrize("revealed", [False, True])
def test_airbags_require_discovered_family_usage(scenario, state, revealed):
    state.revealed_facts = ["family_usage"] if revealed else []
    updated = apply_turn_analysis(state, scenario, "Plus", TurnAnalysis(linked_benefits=links("airbags_7")))
    assert updated.linked_benefits == (links("airbags_7") if revealed else [])


@pytest.mark.parametrize(
    "message,triggered", [("Bản Plus phù hợp với chị.", True), ("BẢN PLUS", True), ("plusieurs", False)]
)
def test_keyword_triggered_objection_has_word_boundaries(scenario, state, message, triggered):
    updated = apply_turn_analysis(state, scenario, message, TurnAnalysis())
    assert (UPSELL in updated.active_objections) is triggered
    assert state.active_objections == []


@pytest.mark.parametrize(
    "benefits,resolved",
    [
        (["airbags_7"], False),
        (["motor_150kw", "camera_360"], False),
        (["airbags_7", "camera_360"], True),
        (["airbags_7", "airbags_7"], False),
    ],
)
def test_upsell_rule_requires_distinct_benefits_and_safety(scenario, state, benefits, resolved):
    state.revealed_facts = ["parking", "family_usage", "weekend_trips"]
    updated = apply_turn_analysis(state, scenario, "Plus", TurnAnalysis(linked_benefits=links(*benefits)))
    assert (UPSELL in updated.resolved_objections) is resolved
    assert (UPSELL in updated.unresolved_objections) is not resolved


def test_analyzer_cannot_bypass_upsell_rule(scenario, state):
    state.active_objections = [UPSELL]
    updated = apply_turn_analysis(
        state, scenario, "Plus", TurnAnalysis(addressed_objection_ids=[UPSELL], resolved_objection_ids=[UPSELL])
    )
    assert UPSELL in updated.unresolved_objections
    assert UPSELL not in updated.resolved_objections


def test_benefit_links_and_policy_mentions_accumulate_and_deduplicate(scenario, state):
    state.revealed_facts = ["parking", "family_usage"]
    first = apply_turn_analysis(
        state,
        scenario,
        "Plus",
        TurnAnalysis(linked_benefits=links("airbags_7"), policy_mentions=["charging", "invalid", "charging"]),
    )
    second = apply_turn_analysis(
        first,
        scenario,
        "Camera hỗ trợ chị.",
        TurnAnalysis(linked_benefits=links("camera_360", "airbags_7"), policy_mentions=["charging", "warranty"]),
    )
    assert UPSELL in second.resolved_objections
    assert len(second.linked_benefits) == 2
    assert second.policy_mentions == ["charging", "warranty"]
    assert first.resolved_objections == []


@pytest.mark.asyncio
async def test_analyzer_filters_unknown_and_unrevealed_need_keys(scenario, state):
    state.revealed_facts = ["family_usage"]
    model = AnalysisModel(
        {
            "linked_benefits": [
                {"benefit_id": "camera_360", "need_fact_key": "parking"},
                {"benefit_id": "airbags_7", "need_fact_key": "family_usage"},
                {"benefit_id": "fake", "need_fact_key": "visible_goals"},
                {"benefit_id": "airbags_7", "need_fact_key": "family_usage"},
            ],
            "policy_mentions": ["warranty", "fake", "warranty"],
            "mentioned_products": ["Eco"],
        }
    )
    analysis = await TurnAnalyzer(model).analyze("Túi khí bảo vệ con chị.", scenario, state)
    assert analysis.linked_benefits == links("airbags_7")
    assert analysis.policy_mentions == ["warranty"]
    context = _turn_analysis_context("Chào chị", scenario, state)
    assert set(context["state"]["allowed_need_fact_keys"]) == {"visible_goals", "family_usage"}
    assert context["scenario"]["customer_goals"] == scenario.customer_goals
    for field in ("upsell_benefits", "acceptable_outcomes", "policy_expectations"):
        assert context["scenario"][field]
    assert scenario.hidden_facts["parking"] not in str(context)


@pytest.mark.parametrize(
    "selected,resolved,expected",
    [
        ("upsell_plus", [], "close_eco"),
        ("bogus", [], "close_eco"),
        ("close_eco", [], "close_eco"),
        ("upsell_plus", [UPSELL], "upsell_plus"),
    ],
)
@pytest.mark.asyncio
async def test_accepted_outcome_is_validated_and_recorded(scenario, selected, resolved, expected):
    graph, checkpoint, _, _ = runtime(
        analyses=[{"next_step_attempted": True}],
        replies=[
            {"reply": "Chị đồng ý, mình hẹn lái thử nhé.", "accepted_next_step": True, "accepted_outcome_id": selected}
        ],
    )
    await graph.start("session", SCENARIO_ID)
    saved = await graph.get_session_state("session")
    saved.resolved_objections = resolved
    saved.unresolved_objections = [key for key in saved.unresolved_objections if key not in resolved]
    await checkpoint.save("session", saved.model_dump(mode="json"))
    view = await graph.continue_session("session", "Chị muốn hẹn lái thử không?")
    assert view["closing_outcome"] == expected
    assert "hidden_facts" not in view
    assert (await graph.get_session_state("session")).closing_outcome == expected


@pytest.mark.asyncio
async def test_acceptance_cannot_resolve_upsell_objection_without_benefits():
    graph, _, _, _ = runtime(
        analyses=[{}, {"next_step_attempted": True}],
        replies=[
            {"reply": "Bản cao hơn có đáng không?", "raised_objection_id": UPSELL},
            {"reply": "Chị đồng ý lái thử Eco.", "accepted_next_step": True, "accepted_outcome_id": "upsell_plus"},
        ],
    )
    await graph.start("session", SCENARIO_ID)
    await graph.continue_session("session", "Chị xem Plus nhé.")
    await graph.continue_session("session", "Mình lái thử nhé?")
    saved = await graph.get_session_state("session")
    assert saved.closing_outcome == "close_eco"
    assert UPSELL not in saved.resolved_objections
    assert UPSELL not in saved.active_objections


@pytest.mark.asyncio
async def test_customer_price_leak_guard_retries(scenario, state):
    model = CustomerModel({"reply": "Bản Plus giá 637 triệu nhé."}, {"reply": "Chị muốn xem xe thực tế."})
    turn = await CustomerAgent(model).generate_turn(scenario, state, mode="response")
    assert turn.message.content == "Chị muốn xem xe thực tế."
    assert model.calls == 2


@pytest.mark.parametrize("reply", ["Giá 637 triệu nhé.", "Xe có 150 kW.", "Camera 360° nhé."])
@pytest.mark.asyncio
async def test_customer_rejects_repeated_unsupported_figures(scenario, state, reply):
    model = CustomerModel({"reply": reply}, {"reply": reply})
    with pytest.raises(CustomerResponseError, match="unsupported price or specification"):
        await CustomerAgent(model).generate_turn(scenario, state, mode="response")


@pytest.mark.asyncio
async def test_customer_can_repeat_exact_advisor_figures(scenario, state):
    state.messages = [RoleplayMessage(role="advisor", content="Giá 637 triệu và công suất 150 kW.")]
    model = CustomerModel({"reply": "637 triệu và 150 kW đúng không em?"})
    turn = await CustomerAgent(model).generate_turn(scenario, state, mode="response")
    assert "637 triệu" in turn.message.content


@pytest.mark.asyncio
async def test_disclosed_fact_keys_detect_paraphrase_and_ignore_unpermitted_keys():
    class ParaphrasingCustomer(CustomerAgent):
        async def generate_turn(self, scenario, state, **kwargs):
            turn = await super().generate_turn(scenario, state, **kwargs)
            return replace(
                turn,
                message=RoleplayMessage(role="customer", content="Đỗ trong hầm chật lắm em."),
                disclosed_fact_keys=("parking", "budget"),
            )

    graph, checkpoint, customer, _ = runtime(
        analyses=[{"detected_intents": ["ask_parking_conditions"], "discovered_fact_ids": ["parking"]}],
        replies=[{"reply": "Chào em, chị đang tìm hiểu VF 6 Eco."}],
    )
    graph = RoleplayGraph(
        ScenarioRepository(),
        TurnAnalyzer(
            AnalysisModel({"detected_intents": ["ask_parking_conditions"], "discovered_fact_ids": ["parking"]})
        ),
        ParaphrasingCustomer(customer),
        checkpoint,
    )
    await graph.start("session", SCENARIO_ID)
    await graph.continue_session("session", "Chỗ đỗ xe thế nào chị?")
    saved = await graph.get_session_state("session")
    assert saved.spoken_fact_message_ids.keys() == {"parking"}
    assert saved.messages[-1].content == "Đỗ trong hầm chật lắm em."


@pytest.mark.asyncio
async def test_blocks_profanity_and_ends_session():
    graph, _, customer, analyzer = runtime()
    await graph.start("session", SCENARIO_ID)
    view = await graph.continue_session("session", "Đm đồ ngu")
    assert view["termination_status"] == "advisor_misconduct"
    assert view["conversation_stage"] == "finished"
    assert view["messages"][-1]["content"] == "Chị sẽ báo cáo em lên quản lý. Chị không có nhu cầu mua xe ở đây nữa."
    assert analyzer.calls == 0
    assert customer.calls == 0
    assert "ngu" not in view["termination_reason"]
    state = await graph.finish_session("session")
    assert state.evaluation_status is EvaluationStatus.PENDING
    assert state.misconduct_reason
    with pytest.raises(RoleplaySessionConflictError):
        await graph.continue_session("session", "Xin chào")


@pytest.mark.asyncio
async def test_analyzer_flag_ends_session():
    graph, _, customer, analyzer = runtime(analyses=[{"unsafe_or_abusive": True}])
    await graph.start("session", SCENARIO_ID)
    view = await graph.continue_session("session", "Một câu không chứa từ khóa.")
    assert view["termination_status"] == "advisor_misconduct"
    assert analyzer.calls == 1
    assert customer.calls == 0
    assert (await graph.get_session_state("session")).misconduct_reason == "semantic_abuse"
    assert view["messages"][-1]["content"] == "Chị nghĩ mình nên dừng cuộc trao đổi ở đây. Chào em."


@pytest.mark.asyncio
async def test_message_after_misconduct_is_409():
    graph, _, _, _ = runtime()
    service = PracticeService(graph, ScenarioRepository(), session_id_factory=lambda: "session")
    app = FastAPI()
    app.include_router(create_practice_router(service), prefix="/api/v1")
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        assert (await client.post("/api/v1/practice/sessions", json={"scenario_id": SCENARIO_ID})).status_code == 201
        stopped = await client.post("/api/v1/practice/session/message", json={"message": "Đm đồ ngu"})
        assert stopped.status_code == 200
        assert stopped.json()["termination_status"] == "advisor_misconduct"
        response = await client.post("/api/v1/practice/session/message", json={"message": "Xin chào"})
        assert response.status_code == 409


@pytest.mark.parametrize("scenario_id", ["SCENARIO_01_VF5_TAXI", "SCENARIO_02_VF7_VS_CX5", "SCENARIO_03_VF6_APARTMENT"])
@pytest.mark.asyncio
async def test_existing_scenarios_keep_default_closing_outcome(scenario_id):
    graph, _, _, _ = runtime(
        analyses=[{"next_step_attempted": True}],
        replies=[{"reply": "Chị đồng ý hẹn lái thử.", "accepted_next_step": True}],
    )
    await graph.start("session", scenario_id)
    view = await graph.continue_session("session", "Mình hẹn lái thử nhé?")
    assert view["termination_status"] == "active"
    assert view["closing_outcome"] == "close"
    expected_stage = (
        ConversationStage.CLOSING
        if scenario_id == "SCENARIO_03_VF6_APARTMENT"
        else ConversationStage.OBJECTION_HANDLING
    )
    assert view["conversation_stage"] == expected_stage.value


@pytest.mark.parametrize(
    "message",
    [
        "chị yên tâm, xe ngon lắm",
        "động cơ mạnh",
        "xe sử dụng nguồn điện 220V dân dụng để sạc tại nhà rất an toàn",
        "ghế người lái có tính năng chỉnh điện 8 hướng và làm mát",
        "cái giá này là cực tốt",
        "chị đừng lo",
        "mấy ông bán xe xăng hay chê xe điện chứ thực tế đi tiết kiệm lắm ạ",
        "xe này chạy như điên",
        "Dung tích xi lanh bản máy xăng trước đây là 2000 cc, nhưng dòng xe điện này công suất còn vượt trội hơn.",
        "Chị có thể thanh toán tiền cọc qua thẻ tín dụng có mã ccv hoặc chuyển khoản ngân hàng ạ.",
        "Hệ thống pin của xe có tính năng tự động ngắt khi dòng điện quá tải để đảm bảo an toàn tuyệt đối.",
        "Dạ chính sách giá và khuyến mại tháng này bên em là cố định theo niêm yết của hãng rồi ạ, em không thể bớt thêm được nữa.",
        "Nguyên nhân chính khiến chi phí vận hành xe điện rẻ hơn là nhờ giá điện sinh hoạt thấp hơn giá xăng dầu.",
        "Buổi sáng mai lúc 9h em mời anh chị qua showroom để trực tiếp trải nghiệm cảm giác lái thử nhé.",
        "Xe bên em cam kết chính hãng 100%, khung gầm nguyên bản, không hề bị đâm đụng hay ngập nước.",
        "Động cơ điện phản hồi tức thì nên khi đạp ga xe bốc đầu rất nhanh nhưng vẫn kiểm soát cực kỳ mượt mà.",
        "Mẹ em ở nhà cũng đang đi một chiếc VF 5 Plus màu trắng này, tiện dụng cho gia đình lắm chị.",
        "Chị cứ cân nhắc kỹ nhé, nếu hôm nay chưa tiện đặt cọc thì khi nào sẵn sàng chị nhắn lại em hỗ trợ.",
        "Dạ cản trước và cản sau của xe được mạ chrome thể thao rất khỏe khoắn và tinh tế ạ.",
        "Em xin phép gửi báo giá chi tiết và thông số kỹ thuật cho anh qua hòm thư điện tử hoặc Zalo nhé.",
        "Chương trình hỗ trợ đổi xe cũ lấy xe mới áp dụng cho tất cả khách hàng trên toàn quốc.",
        "Hệ thống hỗ trợ đỗ xe thông minh sẽ tự động đánh lái giúp chị vào chuồng hẹp dễ dàng.",
        "Dạ bên em đang xử lý hồ sơ trả góp ngân hàng cho khách hàng ở chi nhánh Bắc Ninh và Nam Định ạ.",
        "Dòng SUV này được rất nhiều khách hàng nữ ưa chuộng vì tầm nhìn thoáng và vô lăng trợ lực rất nhẹ.",
        "Anh chị check tin nhắn qua dm trên Zalo hoặc Instagram giúp em nhé, em vừa gửi hợp đồng mẫu rồi ạ.",
    ],
)
def test_allows_normal_sales_talk(message):
    assert check_advisor_message(message).level == "ok"


@pytest.mark.parametrize(
    "message",
    [
        "Chị ngu vừa thôi, không có tiền thì đừng có bấm vào hỏi giá xe.",
        "Nói mãi không hiểu à, đúng là đồ óc chó mới so sánh xe điện với xe tàu.",
        "Tư duy đần độn như mày thì cả đời này cũng chỉ đi xe máy rách thôi.",
        "Khách hàng kiểu gì mà bại não thế, hợp đồng ghi rõ mười mươi rồi.",
        "Mày bị điên à mà đòi mua xe VF 9 với giá 500 triệu?",
        "Đm tư vấn từ sáng đến giờ xong bảo không có tiền mua, lượn mẹ đi.",
        "Cái đkm nhà mày, thích phá đám showroom bọn tao không?",
        "Hỏi như cc vậy, xe người ta tiền tỷ mà trả giá như mớ rau ngoài chợ.",
        "vcl cái bà này, không cọc thì biến đi cho người khác làm việc.",
        "Xe đéo bán cho loại khách hãm lồn như mày nữa, cút!",
        "Tư vấn hết nước hết cái xong đéo mua, đúng dkm mày.",
        "Chị mặc váy này lái thử xe nhìn ngực to với mông nở sexy quá, tối đi uống rượu với em nhé.",
        "Em giảm giá hết nấc cho chị, bù lại tối nay qua đêm khách sạn với anh nhé.",
        "Body chị múp thế này ngồi ghế cơ trưởng VF 9 thì tha hồ nhún nhảy lên giường.",
        "Gái đẹp thế này mà không có đại gia nuôi à, cho anh sờ tí anh bớt cho 50 củ.",
        "Mày bước chân ra khỏi showroom này là biết tay tao, tao đập chết mày.",
        "Mày có tin tao cho người đến tận nhà đốt nhà mày không con ranh?",
        "Biết bố mày là ai không mà dám ăn nói xấc xược với tao?",
        "Còn lải nhải nữa tao cho vỡ alo bây giờ, đừng để tao phải xử lý mày.",
        "Mấy đứa bắc kỳ chó như chúng mày lúc nào cũng bủn xỉn ki bo.",
        "Lũ namke lười làm đòi hưởng thụ, tiền đéo đâu mà mua xe sang.",
        "Đúng là đàn bà đái không qua ngọn cỏ, phụ nữ thì biết cái quái gì về động cơ.",
        "Lũ mọi miên mọi rợ trên núi xuống phố mua xe à mà ngáo ngơ thế.",
        "Shut the fuck up, you are wasting my time, stupid bitch.",
        "What a fucking asshole, get out of my showroom right now.",
    ],
)
def test_blocks_abuse_pattern_catalog(message):
    assert check_advisor_message(message).level == "end_session"


@pytest.mark.asyncio
async def test_misconduct_session_can_finish_and_save_evaluation():
    from src.models.evaluation import CriterionType, SessionEvaluationResult

    class Evaluator:
        async def evaluate(self, scenario, state, knowledge_evidence):
            assert state.termination_status.value == "advisor_misconduct"
            return SessionEvaluationResult(
                session_id=state.session_id,
                scenario_id=state.scenario_id,
                rubric_version="test",
                assessed_criteria_count=0,
                evaluations=[
                    {"criterion": criterion, "status": "unassessed", "reason": "No opportunity."}
                    for criterion in CriterionType
                ],
            )

    graph, _, _, _ = runtime()

    class EvidenceProvider:
        async def for_session(self, scenario, state):
            return []

    service = PracticeService(
        graph,
        ScenarioRepository(),
        session_id_factory=lambda: "session",
        evaluator=Evaluator(),
        knowledge_evidence=EvidenceProvider(),
    )
    await service.start_session(SCENARIO_ID)
    await service.send_message("session", "Đm đồ ngu")
    result = await service.finish_session("session")
    assert result.evaluation_status is EvaluationStatus.COMPLETE
    saved = await graph.get_session_state("session")
    assert saved.termination_status.value == "advisor_misconduct"
    assert saved.evaluation_result is not None


def test_outcome_falls_back_to_preferred_base_or_none(scenario, state):
    from src.agents.roleplay.contracts import AcceptableOutcome

    scenario = scenario.model_copy(
        update={
            "acceptable_outcomes": [
                AcceptableOutcome(outcome_id="base", label="Base", product="Eco"),
                AcceptableOutcome(outcome_id="preferred_base", label="Preferred", product="Eco", preferred=True),
            ]
        }
    )
    assert CustomerAgent.validated_outcome_id("missing", scenario, state) == "preferred_base"
    locked = scenario.model_copy(
        update={
            "acceptable_outcomes": [
                AcceptableOutcome(
                    outcome_id="locked", label="Locked", product="Plus", requires_resolved_objections=[UPSELL]
                )
            ]
        }
    )
    assert CustomerAgent.validated_outcome_id("locked", locked, state) is None


@pytest.mark.asyncio
async def test_customer_can_repeat_figures_in_revealed_statements(scenario, state):
    state.revealed_facts = ["budget"]
    statement = next(rule.revealed_statement for rule in scenario.disclosure_rules if rule.fact_key == "budget")
    state.messages = [RoleplayMessage(role="customer", content=statement)]
    state.spoken_fact_message_ids = {"budget": state.messages[0].message_id}
    turn = await CustomerAgent(CustomerModel({"reply": statement})).generate_turn(scenario, state, mode="response")
    assert turn.message.content == statement


def test_guardrail_normalizes_combining_accents_and_compound_diacritics():
    import unicodedata

    assert check_advisor_message(unicodedata.normalize("NFD", "Đồ óc chó")).level == "end_session"
    assert check_advisor_message("Đốt nhà").level == "end_session"
    assert check_advisor_message("dot nha").level == "end_session"
    for text in ("Chị ngủ ngon nhé.", "Các xe lớn đều đeo dây an toàn.", "Đồ điện chính hãng."):
        assert check_advisor_message(text).level == "ok"


@pytest.mark.parametrize(
    "message",
    [
        "Chị rảnh hôm nào cho em hẹn lái thử ạ?",
        "Chị cho anh số điện thoại nhé",
        "Bãi nào cũng đỗ được",
        "Chị sạc qua đêm tại nhà, cuối tuần đi lái thử với em nhé",
        "Chị cứ ngủ ngon, mai lái thử với em",
        "cac phien ban VF 6 deu co",
        "cop xe lon",
        "xe chay do dien",
        "VF 6 co hai phien ban Eco va Plus",
        "Gia xe duoc niem yet tai showroom",
        "Em gui chi bang gia chi tiet",
        "Pin xe co the sac tai nha",
        "Chi hen lai thu vao sang mai nhe",
        "Bao hanh theo chinh sach cua hang",
        "Cac thong so ky thuat deu co trong tai lieu",
        "Cop xe lon de du hanh ly gia dinh",
        "Chi can bao nhieu cho ngoi",
        "Xe chay do dien nen khong can xang",
        "Ben em ho tro ho so tra gop",
        "Buoi sang em gui thong tin sac pin",
        "Bai nao cung co cho do xe rong",
        "Khi nao cho em hen lai thu",
        "Chi cho anh so dien thoai nhe",
    ],
)
def test_guardrail_allows_accented_and_ascii_sales_regressions(message):
    assert check_advisor_message(message).level == "ok"


@pytest.mark.parametrize(
    "message", ["ngủ với anh", "qua đêm với em", "oc cho", "thieu nang", "bac ky", "vcl", "clgt", "cmm"]
)
def test_guardrail_keeps_unambiguous_abuse(message):
    assert check_advisor_message(message).level == "end_session"


@pytest.mark.asyncio
async def test_active_figure_free_objection_does_not_authorize_invented_price(scenario, state):
    state.active_objections = [UPSELL]
    state.messages = [RoleplayMessage(role="advisor", content="Chào chị, chị lấy Plus luôn nhé?")]
    model = CustomerModel(
        {"reply": "Plus đắt hơn gần 50 triệu", "raised_objection_id": UPSELL},
        {"reply": "Plus đắt hơn khá nhiều, chị cần cân nhắc.", "raised_objection_id": UPSELL},
    )
    turn = await CustomerAgent(model).generate_turn(scenario, state, mode="response")
    assert "50 triệu" not in turn.message.content
    assert model.calls == 2


def test_benefit_links_require_the_configured_need(scenario, state):
    state.revealed_facts = ["budget", "driving_experience"]
    analysis = TurnAnalysis(
        linked_benefits=[
            LinkedBenefit(benefit_id="adas", need_fact_key="budget"),
            LinkedBenefit(benefit_id="airbags_7", need_fact_key="visible_goals"),
        ]
    )
    updated = apply_turn_analysis(state, scenario, "Plus", analysis)
    assert updated.linked_benefits == []
    assert UPSELL not in updated.resolved_objections
    assert next(b for b in scenario.upsell_benefits if b.benefit_id == "airbags_7").linked_need_fact_keys == [
        "family_usage"
    ]


@pytest.mark.asyncio
async def test_accepted_eco_retires_upsell_without_credit_or_dropout():
    graph, _, _, _ = runtime(
        analyses=[{}, {"next_step_attempted": True}, {}, {}, {}],
        replies=[
            {"reply": "Plus có đáng không?", "raised_objection_id": UPSELL},
            {"reply": "Chị đồng ý lái thử Eco.", "accepted_next_step": True, "accepted_outcome_id": "close_eco"},
            {"reply": "Chị hẹn gặp em."},
            {"reply": "Chị cảm ơn."},
            {"reply": "Chị chào em."},
        ],
    )
    await graph.start("session", SCENARIO_ID)
    await graph.continue_session("session", "Chị xem Plus nhé.")
    await graph.continue_session("session", "Mình chốt Eco và hẹn lái thử nhé?")
    for _ in range(3):
        view = await graph.continue_session("session", "Em gửi lịch, cả thông tin Plus để tham khảo nhé.")
        assert view["termination_status"] == "active"
        assert view["closing_outcome"] == "close_eco"
    saved = await graph.get_session_state("session")
    assert UPSELL not in saved.active_objections
    assert UPSELL not in saved.resolved_objections


@pytest.mark.parametrize("scenario_id,address", [("SCENARIO_01_VF5_TAXI", "Anh"), (SCENARIO_ID, "Chị")])
@pytest.mark.asyncio
async def test_misconduct_reply_matches_persona(scenario_id, address):
    graph, _, _, _ = runtime()
    await graph.start("session", scenario_id)
    view = await graph.continue_session("session", "Đm đồ ngu")
    assert view["messages"][-1]["content"] == (
        f"{address} sẽ báo cáo em lên quản lý. {address} không có nhu cầu mua xe ở đây nữa."
    )


def test_model_disclosure_contract_has_no_unreachable_fields(scenario, state):
    from src.agents.roleplay.customer_agent import CustomerModelOutput
    from src.agents.roleplay.prompts import CUSTOMER_SYSTEM_PROMPT

    assert "disclosed_fact_keys" not in CustomerModelOutput.model_fields
    assert "pending_disclosures" not in CustomerAgent._build_context(scenario, state, mode="response")
    assert "disclosed_fact_keys" not in CUSTOMER_SYSTEM_PROMPT


@pytest.mark.parametrize("source", ["visible_context", "customer_goals"])
@pytest.mark.asyncio
async def test_customer_can_quote_visible_scenario_figures(scenario, state, source):
    scenario = scenario.model_copy(update={source: "Khách cân nhắc giá chênh 42 triệu."})
    model = CustomerModel({"reply": "Chênh 42 triệu thì chị cần cân nhắc."})
    turn = await CustomerAgent(model).generate_turn(scenario, state, mode="response")
    assert "42 triệu" in turn.message.content


@pytest.mark.asyncio
async def test_inactive_objection_does_not_authorize_figures(scenario, state):
    model = CustomerModel({"reply": "Plus đắt hơn gần 50 triệu"}, {"reply": "Chị cân nhắc thêm."})
    turn = await CustomerAgent(model).generate_turn(scenario, state, mode="response")
    assert turn.message.content == "Chị cân nhắc thêm."
    assert model.calls == 2


@pytest.mark.asyncio
async def test_guardrail_warning_is_logged_without_message_text(caplog):
    graph, _, _, analyzer = runtime(analyses=[{}], replies=[{"reply": "Chị xem thêm nhé."}])
    await graph.start("session", SCENARIO_ID)
    await graph.continue_session("session", "Chém gió chút thôi")
    assert "Advisor guardrail warning: session_id=session category=mild_unprofessional" in caplog.text
    assert "Chém gió" not in caplog.text
    assert analyzer.calls == 1


@pytest.mark.parametrize(
    "message",
    ["Chị cứ khi nao cho em lịch hẹn nhé", "Bãi bai nao cũng rộng", "Chị cho anh so điện thoại", "dap may sac se hu"],
)
def test_ambiguous_folded_phrases_do_not_terminate(message):
    assert check_advisor_message(message).level == "ok"
