"""Seed fictional Practice sample data for the manager dashboard and advisor Practice room.

Dry run: python scripts/seed_practice_showcase.py
Apply:   python scripts/seed_practice_showcase.py --apply
Refresh: python scripts/seed_practice_showcase.py --reset --apply

--reset deletes only rows with this seed prefix from the six sample-data
tables before inserting fresh data. Users and non-seed rows are preserved.
Without --apply, reset only previews the deletion and insertion counts.

Reuses advisor-demo and manager-demo (created from DEMO_ADVISOR_PASSWORD /
DEMO_MANAGER_PASSWORD when missing) and adds 7 data-only sample advisors with
random, unprinted passwords. Row ids are deterministic (showcase1_<hash>_...),
so a second --apply inserts nothing. Times are anchored to Asia/Ho_Chi_Minh at
first insertion. Everything here is fictional and must never be used as
evaluation evidence.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import math
import os
import re
import secrets
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from dotenv import load_dotenv
from sqlalchemy import create_engine, delete, insert, inspect, select, update

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.agents.roleplay.state import (  # noqa: E402
    AdvisorFactualClaim,
    ConversationStage,
    EvaluationStatus,
    RoleplayMessage,
    RoleplayState,
    TerminationStatus,
)
from src.config import get_settings  # noqa: E402
from src.integrations.auth_repository import SQLAuthRepository  # noqa: E402
from src.integrations.practice_persistence import SQLCheckpointRepository, normalize_database_url  # noqa: E402
from src.integrations.practice_records import SQLPracticeRecordsRepository  # noqa: E402
from src.models.auth import UserRole  # noqa: E402
from src.models.evaluation import (  # noqa: E402
    CheckVerdict,
    CriterionEvaluation,
    CriterionStatus,
    CriterionType,
    FactualClaimStatus,
    FactualFinding,
    ObservableCheckResult,
    RecommendedNextPractice,
    ReviewStatus,
    SessionEvaluationResult,
    TranscriptEvidence,
)
from src.services.auth import AuthService  # noqa: E402
from src.services.practice_records import (  # noqa: E402
    ManagerReviewDecision,
    ScoreOverride,
    approved_evaluation,
)

TZ = ZoneInfo("Asia/Ho_Chi_Minh")
PREFIX = "showcase1_" + hashlib.sha256(b"practice-showcase-v1").hexdigest()[:8] + "_"
MANAGER_ID = "manager-demo"
DEMO_ADVISOR_ID = "advisor-demo"
DEFAULT_DEMO_NAME = "Tư vấn viên Demo"
DEMO_ADVISOR_NAME = "Phạm Đình Duy"
# Earlier seed names for advisor-demo that a re-run may replace.
PREVIOUS_DEMO_NAMES = ("Trần Minh Khoa",)
DEFAULT_MANAGER_NAME = "Quản lý Demo"
DEMO_MANAGER_NAME = "Nguyễn Thu Trang"
RUBRIC_VERSION = "sales-rubric-v4"
CRITERIA = [c.value for c in CriterionType]
ND, PK, OH, PA, CL = CRITERIA
SCENARIO_FILE = Path(__file__).resolve().parents[1] / "data" / "scenarios" / "scenarios.json"

# slug, display name, attempts, per-criterion (start, end) mean score, days-ago of the newest attempt
ADVISORS = [
    ("demo", None, 18, {ND: (1.7, 2.9), PK: (1.6, 2.8), OH: (1.4, 2.7), PA: (1.2, 2.5), CL: (1.6, 2.9)}, None),
    ("ha", "Lê Thu Hà", 12, {ND: (2.7, 2.9), PK: (2.8, 3.0), OH: (2.6, 2.8), PA: (2.6, 2.8), CL: (2.8, 3.0)}, 0.3),
    ("bao", "Phạm Quốc Bảo", 11, {ND: (2.2, 2.2), PK: (2.0, 2.0), OH: (1.9, 1.9), PA: (1.8, 1.8), CL: (2.0, 2.0)}, 1.2),
    ("vy", "Nguyễn Thảo Vy", 11, {ND: (2.3, 2.3), PK: (2.9, 2.9), OH: (2.2, 2.2), PA: (1.4, 1.4), CL: (2.3, 2.3)}, 0.8),
    ("huy", "Đỗ Gia Huy", 10, {ND: (2.3, 2.3), PK: (2.3, 2.3), OH: (2.2, 2.2), PA: (2.1, 2.1), CL: (1.3, 1.3)}, 1.6),
    (
        "ngocanh",
        "Vũ Ngọc Anh",
        2,
        {ND: (2.0, 2.0), PK: (1.8, 1.8), OH: (1.8, 1.8), PA: (1.6, 1.6), CL: (1.6, 1.6)},
        3.4,
    ),
    (
        "tam",
        "Nguyễn Hữu Chương",
        8,
        {ND: (2.3, 2.5), PK: (1.7, 1.9), OH: (2.4, 2.6), PA: (1.9, 2.1), CL: (2.1, 2.3)},
        2.5,
    ),
    (
        "linh",
        "Bùi Phương Linh",
        8,
        {ND: (2.8, 2.8), PK: (2.6, 2.6), OH: (1.7, 1.7), PA: (2.4, 2.4), CL: (1.9, 1.9)},
        4.0,
    ),
]

# ---------------------------------------------------------------------------
# Hand-written Vietnamese transcript templates. Customer lines are fixed per
# scenario; advisor lines depend on the score tier (1, 2 or 3) of each criterion.
# No prices or policy figures appear; policy lines are verify-later or plainly
# overconfident (tier 1) so the evaluation reads as a realistic AI draft.
# ---------------------------------------------------------------------------
TEMPLATES = {
    "SCENARIO_01_VF5_TAXI": {
        "customer": [
            "VF 5 Plus lăn bánh bao nhiêu em? Anh đang chạy Vios dịch vụ tính đổi sang xe điện mà sợ không ăn thua.",
            "Anh chạy tầm 180 cây mỗi ngày, tiền xăng khoảng 8,5 triệu một tháng. Anh hay nghỉ trưa từ 12 rưỡi tới 2 giờ chiều.",
            "Anh nghe nói sạc ngoài lượt được ưu đãi vẫn tốn tiền, rồi còn trả góp nữa. Chạy nhiều như anh thì đổi từ Vios có đáng không em?",
            "Thế ưu đãi cho xe chạy dịch vụ thì sao em? Anh nghe nói có chương trình đổi xe xăng sang xe điện.",
            "Ừ, vậy giờ anh nên làm gì tiếp để biết có đáng đổi không?",
        ],
        "advisor": {
            ND: {
                1: "Chào anh, VF 5 Plus là mẫu xe rất hợp để chạy dịch vụ. Em gửi anh thông tin chung về xe nhé.",
                2: "Chào anh, em hỗ trợ anh ạ. Mỗi ngày anh chạy khoảng bao nhiêu km và tiền xăng mỗi tháng của xe hiện tại là bao nhiêu ạ?",
                3: "Chào anh, em hỗ trợ anh ạ. Để so sánh đúng với chiếc Vios, anh cho em xin quãng đường chạy mỗi ngày, tiền xăng thực tế mỗi tháng và khung giờ anh hay nghỉ ca để em tính chỗ sạc cho hợp lý ạ?",
            },
            PK: {
                1: "VF 5 Plus chạy được mọi cung đường, anh không cần lo gì về xe đâu ạ. Xe này tốt hơn Vios về mọi mặt.",
                2: "VF 5 Plus là xe điện cỡ nhỏ, hợp chạy trong phố và vận hành êm. Em sẽ gửi anh thông số quãng đường di chuyển chính thức của xe để anh đối chiếu ạ.",
                3: "Với quãng đường 180 cây mỗi ngày của anh thì quãng đường mỗi lần sạc là thông số quan trọng nhất. Em sẽ gửi anh thông số chính thức của hãng và mình tính xem một ngày anh cần sạc mấy lần, nhất là trong giờ nghỉ trưa của anh ạ.",
            },
            OH: {
                1: "Anh yên tâm, đổi sang xe điện chắc chắn lời hơn xe xăng ạ. Không cần tính toán gì nhiều đâu anh.",
                2: "Em hiểu anh lo về tiền sạc và khoản trả góp ạ. Mình nên tách riêng tiền năng lượng và tiền trả góp để so sánh với tiền xăng hiện tại của anh nhé.",
                3: "Em hiểu anh lo chi phí tổng thể chứ không riêng tiền sạc ạ. Mình tách ba phần là tiền năng lượng, khoản trả góp và thời gian dừng sạc ảnh hưởng đến cuốc chạy, rồi so với 8,5 triệu tiền xăng của anh; anh thấy phần nào anh lo nhất ạ?",
            },
            PA: {
                1: "Chương trình đổi xe thì anh được hết, không cần điều kiện gì đâu ạ. Ưu đãi sạc cũng không giới hạn gì cả.",
                2: "Em có nghe về chương trình ưu đãi chuyển đổi sang xe điện, nhưng điều kiện áp dụng cần kiểm tra theo chính sách hiện hành. Em sẽ xác nhận lại rồi báo anh chính xác ạ.",
                3: "Chương trình ưu đãi chuyển đổi thường có điều kiện về xe cũ và thời điểm áp dụng, nên em cần xác nhận xe Vios của anh có đủ điều kiện không trước khi nói con số nào. Em sẽ đối chiếu chính sách sạc và ưu đãi hiện hành rồi gửi anh bản tóm tắt có ghi rõ điều kiện ạ.",
            },
            CL: {
                1: "Anh cứ đặt cọc luôn hôm nay đi ạ, để lâu hết xe thì tiếc lắm.",
                2: "Anh có thể ghé showroom xem xe khi nào tiện ạ.",
                3: "Em đề xuất mình hẹn anh lái thử vào khung giờ nghỉ trưa thứ Bảy này, kèm bảng so sánh chi phí em chuẩn bị theo số liệu của anh. Anh thấy giờ đó có tiện không ạ?",
            },
        },
        "closing_reply": {
            1: "Anh chưa muốn đặt cọc gấp thế, để anh suy nghĩ thêm.",
            2: "Ừ, để anh sắp xếp rồi ghé xem sau nhé.",
            3: "Được, thứ Bảy anh rảnh buổi trưa. Em gửi anh bảng so sánh trước nhé.",
        },
        "next": "SCENARIO_03_VF6_APARTMENT",
    },
    "SCENARIO_02_VF7_VS_CX5": {
        "customer": [
            "Chị thấy VF 7 với CX-5 cũng như nhau, CX-5 nhìn quen mắt hơn mà sao VF 7 đắt hơn khá nhiều vậy em?",
            "Nhà chị bốn người, chị chủ yếu đi phố, cuối tuần thỉnh thoảng đi xa. Chồng chị cũng muốn xem xe cùng.",
            "Chị lo VF 7 mất giá nhanh hơn CX-5 nếu sau này bán lại. Em nói chị nghe xem sao.",
            "Vậy có ưu đãi gì cho xe điện không em, chị nghe nói đang có chương trình.",
            "Ừ, vậy chị với chồng nên làm gì tiếp?",
        ],
        "advisor": {
            ND: {
                1: "Chào chị, VF 7 có nhiều trang bị hơn nên giá cao hơn ạ. Em gửi chị bảng so sánh chung nhé.",
                2: "Chào chị, em hỗ trợ chị ạ. Gia đình mình mấy người và chị hay đi xe vào dịp nào để em so sánh cho đúng ạ?",
                3: "Chào chị, em hỗ trợ chị ạ. Trước khi so sánh, chị cho em biết nhà mình đi mấy người, chị hay đi phố hay đi xa và ai cùng quyết định mua xe để em chọn đúng điểm cần so ạ?",
            },
            PK: {
                1: "VF 7 thì chạy tốt hơn CX-5 ở mọi điểm ạ. CX-5 là xe cũ rồi, chị không nên cân nhắc.",
                2: "VF 7 là xe điện nên vận hành êm khi đi phố và không có tiếng động cơ. CX-5 là xe xăng đã quen thuộc nên mỗi xe có thế mạnh riêng ạ.",
                3: "Vì chị chủ yếu đi phố và nhà có bốn người, em sẽ so hai xe theo ba điểm là sự êm ái khi di chuyển trong phố, không gian cho cả nhà và chi phí sử dụng. Thông số cụ thể em sẽ lấy từ tài liệu chính thức của hai hãng, không nói theo cảm tính ạ.",
            },
            OH: {
                1: "Chị đừng lo, VF 7 chắc chắn giữ giá tốt hơn CX-5 ạ. Em đảm bảo luôn.",
                2: "Em hiểu chị lo về giá trị khi bán lại ạ. Việc giữ giá phụ thuộc nhiều yếu tố nên em không dám khẳng định, mình xem các yếu tố có thể kiểm chứng nhé.",
                3: "Em hiểu chị lo bán lại sau này, và đây là lo lắng hợp lý ạ. Em không hứa mức giữ giá cụ thể vì còn phụ thuộc thị trường, nhưng em có thể cùng chị xem chính sách bảo hành pin và chi phí sử dụng, rồi nhờ anh nhà cùng xem để quyết định dễ hơn; chị thấy phần nào chị muốn kiểm tra trước ạ?",
            },
            PA: {
                1: "Có chứ chị, ưu đãi lớn lắm và ai mua cũng được ạ. Chị cứ yên tâm, không phải điều kiện gì hết.",
                2: "Có chương trình ưu đãi nhưng điều kiện áp dụng cần xem theo chính sách hiện hành. Em sẽ kiểm tra rồi báo chị chính xác ạ.",
                3: "Em cần kiểm tra chị có thuộc đối tượng được áp dụng chương trình hiện hành không trước khi nêu bất kỳ con số nào ạ. Em sẽ đối chiếu điều kiện ưu đãi và chính sách bảo hành pin rồi gửi chị bản ghi rõ điều kiện và thời hạn.",
            },
            CL: {
                1: "Chị chuyển khoản cọc hôm nay giúp em để giữ xe nhé.",
                2: "Khi nào chị rảnh chị ghé showroom xem xe nhé.",
                3: "Em đề xuất hẹn chị và anh nhà cùng lái thử VF 7 cuối tuần này, em chuẩn bị sẵn bảng so sánh với CX-5 theo nhu cầu của gia đình. Chị cho em xin khung giờ phù hợp với cả hai vợ chồng ạ?",
            },
        },
        "closing_reply": {
            1: "Chị chưa quyết nhanh vậy được, để chị bàn lại với chồng.",
            2: "Ừ, để chị hỏi chồng rồi ghé sau.",
            3: "Được em, chiều Chủ nhật chị và chồng đi được. Em giữ lịch giúp chị nhé.",
        },
        "next": "SCENARIO_04_VF6_ECO_PLUS_UPSELL",
    },
    "SCENARIO_03_VF6_APARTMENT": {
        "customer": [
            "Nhà anh ở chung cư không có chỗ lắp sạc riêng thì mua VF 6 sạc kiểu gì em ơi?",
            "Anh gửi xe ở hầm chung của chung cư, đi làm mỗi ngày khoảng 30 cây. Ban quản lý chưa cho lắp trụ riêng.",
            "Anh vẫn lo sạc ở trạm công cộng thì phải chờ, rồi lỡ trạm hỏng hay đầy thì sao?",
            "Thế có chính sách hay ưu đãi sạc nào cho khách đi sạc công cộng không em?",
            "Ừ, vậy anh nên làm bước gì tiếp theo?",
        ],
        "advisor": {
            ND: {
                1: "Chào anh, VF 6 sạc rất dễ ạ, anh không phải lo gì đâu. Em gửi anh thông tin chung nhé.",
                2: "Chào anh, em hỗ trợ anh ạ. Chung cư nhà anh có bãi đỗ xe chung hay hầm gửi xe, và anh đi làm khoảng bao xa mỗi ngày ạ?",
                3: "Chào anh, em hỗ trợ anh ạ. Để chọn cách sạc phù hợp, anh cho em biết chỗ đỗ xe của anh là hầm chung hay ngoài trời, quãng đường đi làm mỗi ngày và quanh nhà có trạm sạc công cộng nào anh hay đi qua không ạ?",
            },
            PK: {
                1: "VF 6 chạy cực khỏe, anh chạy bao xa cũng không lo hết pin ạ. Xe này không có nhược điểm gì đâu.",
                2: "VF 6 là xe điện nên mình cần sạc định kỳ. Với quãng đường 30 cây mỗi ngày của anh, em sẽ gửi thông số quãng đường mỗi lần sạc chính thức để anh xem ạ.",
                3: "Với 30 cây mỗi ngày thì anh không cần sạc đầy mỗi ngày, mình có thể sạc theo chu kỳ vài ngày một lần. Em sẽ gửi thông số chính thức về quãng đường mỗi lần sạc và thời gian sạc của trạm công cộng để anh tự tính theo thói quen của mình ạ.",
            },
            OH: {
                1: "Anh đừng lo, trạm sạc ở đâu cũng có, không bao giờ đầy ạ. Cứ mua xe đi rồi tính sau.",
                2: "Em hiểu anh lo phải chờ hoặc gặp trạm bận ạ. Mình có thể xem các trạm quanh nhà và nơi làm của anh trước khi quyết định nhé.",
                3: "Em hiểu nỗi lo này của anh vì anh là người lần đầu dùng xe điện ạ. Mình thử lập danh sách vài trạm gần nhà và gần chỗ làm, cùng một phương án dự phòng khi trạm bận, rồi anh ghé trải nghiệm sạc thử một lần cho yên tâm; anh thấy cách đó ổn không ạ?",
            },
            PA: {
                1: "Sạc công cộng miễn phí hoàn toàn cho khách VF 6 nhé anh. Không giới hạn gì đâu ạ.",
                2: "Hãng có chính sách ưu đãi sạc nhưng điều kiện áp dụng cần xem theo quy định hiện hành. Em sẽ kiểm tra rồi báo anh chính xác ạ.",
                3: "Em cần xác nhận chính sách ưu đãi sạc hiện hành áp dụng cho mẫu VF 6 và trường hợp của anh thế nào, gồm điều kiện và giới hạn nếu có, trước khi nói cụ thể. Em sẽ gửi anh bản tóm tắt có ghi nguồn và thời hạn áp dụng ạ.",
            },
            CL: {
                1: "Anh đặt cọc ngay hôm nay giúp em, để lâu không còn xe đâu ạ.",
                2: "Anh cứ suy nghĩ thêm rồi liên hệ em khi nào sẵn sàng nhé.",
                3: "Em đề xuất anh ghé showroom cuối tuần này để xem xe và em chỉ anh vài trạm sạc gần nhà. Nếu anh muốn, mình thử sạc một lần ngay hôm đó. Anh có rảnh sáng thứ Bảy không ạ?",
            },
        },
        "closing_reply": {
            1: "Anh chưa muốn cọc gấp thế, anh còn lo chuyện sạc.",
            2: "Ừ, để anh nghĩ thêm rồi nhắn em sau.",
            3: "Được em, sáng thứ Bảy anh qua. Anh muốn thử sạc luôn cho yên tâm.",
        },
        "next": "SCENARIO_01_VF5_TAXI",
    },
    "SCENARIO_04_VF6_ECO_PLUS_UPSELL": {
        "customer": [
            "Chào em, chị đang tìm hiểu chiếc VF 6 Eco. Chị thấy giá đang có ưu đãi khá tốt nên muốn đến xem xe thực tế.",
            "Chị đi làm văn phòng, đi trong phố là chính. Cuối tuần thỉnh thoảng chở gia đình đi chơi gần.",
            "Chị chỉ định lấy Eco thôi, lên Plus chị thấy chưa cần lắm. Em thấy sao?",
            "Chị nghe nói giá ưu đãi đang áp dụng cho mọi người, có đúng không em?",
            "Ừ, vậy chị nên làm gì tiếp theo?",
        ],
        "advisor": {
            ND: {
                1: "Chào chị, bên em có bản Plus nhiều tiện nghi hơn Eco nhiều ạ. Chị nên lấy bản Plus cho đáng tiền.",
                2: "Chào chị, em hỗ trợ chị ạ. Chị đang đi xe gì và chị dùng xe chủ yếu cho việc gì ạ?",
                3: "Chào chị, em hỗ trợ chị ạ. Trước khi xem xe, chị cho em biết chị đang đi xe gì, mỗi ngày đi làm xa không, cuối tuần chị có hay đi chơi cùng gia đình, và chị ưu tiên điều gì nhất ở chiếc xe mới ạ?",
            },
            PK: {
                1: "Bản Eco và Plus khác nhau không đáng kể, chị cứ lấy bản nào cũng như nhau ạ. Em không rõ khác ở đâu.",
                2: "Eco và Plus khác nhau về trang bị. Em sẽ đối chiếu bảng so sánh chính thức giữa hai bản và gửi chị phần khác biệt ạ.",
                3: "Vì chị đi phố hằng ngày và thỉnh thoảng chở gia đình đi chơi gần, em sẽ chỉ so sánh những điểm chị dùng thật, như tiện nghi khi đi hằng ngày và cảm giác ngồi cho cả nhà. Phần thông số em lấy từ bảng so sánh chính thức để chị tự cân nhắc ạ.",
            },
            OH: {
                1: "Chị lấy Plus đi ạ, Eco thì thiếu nhiều thứ lắm, sau này chị sẽ hối hận đấy.",
                2: "Em hiểu chị muốn chọn Eco vì phù hợp nhu cầu hiện tại ạ. Nếu chị muốn, em chỉ ra vài điểm khác giữa hai bản để chị tự quyết.",
                3: "Em tôn trọng lựa chọn Eco của chị vì nhu cầu đi phố của chị khá rõ ạ. Em chỉ nêu những điểm khác biệt liên quan đến việc chị chở gia đình cuối tuần, nếu chị thấy chưa cần thì Eco hoàn toàn phù hợp; chị thấy phần nào trong đó có ích với chị không ạ?",
            },
            PA: {
                1: "Đúng rồi chị, ai mua cũng được ưu đãi, không cần điều kiện gì hết ạ.",
                2: "Em nghĩ ưu đãi có điều kiện áp dụng riêng, nên em sẽ kiểm tra theo chính sách hiện hành rồi báo chị chính xác ạ.",
                3: "Em cần kiểm tra chị có đủ điều kiện hưởng ưu đãi không trước khi nêu giá sau ưu đãi ạ. Em sẽ đối chiếu điều kiện hiện hành, thời hạn và cách tính rồi gửi chị bản tóm tắt có ghi rõ ạ.",
            },
            CL: {
                1: "Chị đặt cọc bản Plus ngay hôm nay cho em nhé, chậm là mất ưu đãi.",
                2: "Khi nào chị muốn thì liên hệ em để xem xe nhé.",
                3: "Em đề xuất chị lái thử bản Eco ngay hôm nay nếu tiện, rồi em gửi chị bảng so sánh Eco và Plus theo nhu cầu của chị. Chị có muốn mình đặt lịch lái thử sau giờ làm không ạ?",
            },
        },
        "closing_reply": {
            1: "Chị không thích bị giục như vậy, để chị suy nghĩ.",
            2: "Ừ, để khi nào chị rảnh chị liên hệ em.",
            3: "Được em, sau giờ làm chị ghé lái thử bản Eco. Em gửi bảng so sánh cho chị nhé.",
        },
        "next": "SCENARIO_02_VF7_VS_CX5",
    },
}

REASON = {
    ND: {
        1: "Tư vấn viên giới thiệu xe ngay mà chưa hỏi nhu cầu hay bối cảnh sử dụng của khách.",
        2: "Tư vấn viên đặt câu hỏi về nhu cầu sử dụng chính và dùng câu trả lời để tiếp tục tư vấn.",
        3: "Tư vấn viên hỏi nhiều khía cạnh liên quan đến quyết định của khách và điều chỉnh cách tư vấn theo bối cảnh đó.",
    },
    PK: {
        1: "Phát biểu về sản phẩm mang tính tuyệt đối, thiếu căn cứ và không trả lời đúng câu hỏi của khách.",
        2: "Nêu thông tin sản phẩm liên quan và hẹn bổ sung thông số chính thức.",
        3: "Chọn thông tin sản phẩm gắn với nhu cầu đã nghe từ khách và dẫn nguồn thông số chính thức.",
    },
    OH: {
        1: "Gạt đi băn khoăn của khách bằng lời trấn an chung chung, chưa ghi nhận lo ngại.",
        2: "Ghi nhận lo ngại của khách và đưa ra hướng xử lý phù hợp.",
        3: "Ghi nhận lo ngại, tìm nguyên nhân bên dưới, đề xuất cách kiểm chứng và hỏi lại khách.",
    },
    PA: {
        1: "Khẳng định chắc chắn về ưu đãi mà không nêu điều kiện hay nguồn xác nhận.",
        2: "Nêu rõ ưu đãi có điều kiện và hẹn kiểm tra theo chính sách hiện hành.",
        3: "Hỏi điều kiện của khách trước khi nêu con số và hẹn gửi bản tóm tắt có nguồn, điều kiện và thời hạn.",
    },
    CL: {
        1: "Thúc ép đặt cọc, chưa đề xuất bước tiếp theo phù hợp với mức sẵn sàng của khách.",
        2: "Mời khách đến xem xe nhưng chưa chốt thời gian cụ thể.",
        3: "Đề xuất bước tiếp theo cụ thể, phù hợp với mức sẵn sàng của khách và hỏi lịch cụ thể.",
    },
}
IMPROVE = {
    ND: {
        1: "Hỏi ít nhất một câu về bối cảnh sử dụng trước khi giới thiệu xe.",
        2: "Hỏi thêm về người cùng quyết định hoặc ưu tiên của khách để điều chỉnh tư vấn.",
    },
    PK: {
        1: "Chỉ nêu thông tin có nguồn và trả lời đúng câu hỏi của khách.",
        2: "Gắn thông tin sản phẩm với nhu cầu cụ thể mà khách vừa chia sẻ.",
    },
    OH: {
        1: "Ghi nhận lo ngại của khách trước khi đưa ra câu trả lời.",
        2: "Hỏi lại khách xem phần nào còn băn khoăn nhất sau khi trả lời.",
    },
    PA: {
        1: "Không khẳng định ưu đãi khi chưa kiểm tra điều kiện và nguồn hiện hành.",
        2: "Hỏi điều kiện của khách trước khi nêu ưu đãi, và gửi lại bản tóm tắt có nguồn.",
    },
    CL: {
        1: "Đề xuất một bước tiếp theo vừa sức thay vì thúc ép đặt cọc.",
        2: "Đề xuất thời điểm cụ thể và hỏi khách xác nhận.",
    },
}
CHECKS = {
    ND: ("Hỏi về bối cảnh sử dụng", "Xác định yếu tố ảnh hưởng đến quyết định"),
    PK: ("Thông tin sản phẩm đúng trọng tâm", "Gắn thông tin với nhu cầu của khách"),
    OH: ("Ghi nhận lo ngại của khách", "Đề xuất cách giải quyết hoặc kiểm chứng"),
    PA: ("Không khẳng định khi chưa có nguồn", "Nêu điều kiện áp dụng và hẹn kiểm tra"),
    CL: ("Đề xuất bước tiếp theo", "Bước tiếp theo cụ thể và phù hợp mức sẵn sàng"),
}
CHECK_MET = {1: (False, False), 2: (True, False), 3: (True, True)}
STRENGTH = {
    ND: "Khai thác nhu cầu của khách trước khi tư vấn.",
    PK: "Nêu thông tin sản phẩm đúng trọng tâm và dẫn nguồn chính thức.",
    OH: "Ghi nhận và xử lý lo ngại của khách một cách bình tĩnh.",
    PA: "Kiểm tra điều kiện ưu đãi thay vì khẳng định ngay.",
    CL: "Đề xuất bước tiếp theo cụ thể và phù hợp với khách.",
}
WEAKNESS = {
    ND: "Chưa hỏi đủ về nhu cầu của khách trước khi giới thiệu xe.",
    PK: "Thông tin sản phẩm chưa có căn cứ hoặc chưa đúng trọng tâm.",
    OH: "Chưa ghi nhận lo ngại của khách trước khi trả lời.",
    PA: "Khẳng định ưu đãi khi chưa kiểm tra điều kiện và nguồn.",
    CL: "Thúc ép chốt thay vì đề xuất bước tiếp theo vừa sức.",
}
OVERRIDE_REASONS_POLICY = [
    "Tư vấn viên nêu ưu đãi như áp dụng cho mọi khách, chưa kiểm tra điều kiện.",
    "Câu trả lời về ưu đãi chưa nêu nguồn và điều kiện áp dụng.",
    "Chưa hỏi điều kiện của khách trước khi nói về ưu đãi nên chưa đạt mức đúng chính sách.",
    "Lời hẹn kiểm tra chính sách chưa đủ cụ thể, cần nêu rõ điều kiện cần xác nhận.",
    "Ưu đãi được nhắc nhưng thiếu thời hạn và điều kiện, chưa đủ chính xác.",
    "Nên nói rõ ưu đãi còn phụ thuộc điều kiện, tư vấn viên mới chỉ nhắc chung chung.",
]
OTHER_OVERRIDES = [
    (CL, 3, 2, "Đề xuất lái thử đúng hướng nhưng chưa chốt giờ cụ thể với khách."),
    (ND, 2, 3, "Câu hỏi về người cùng quyết định rất đúng ngữ cảnh, đáng điểm tối đa."),
    (PK, 3, 2, "Thông số chưa được dẫn nguồn cụ thể nên chưa đạt mức cao nhất."),
]
GENERAL_COMMENTS = [
    "Giữ nhịp trao đổi tự nhiên, nên tiếp tục như vậy.",
    "Cần kiểm tra điều kiện ưu đãi trước khi nêu với khách.",
    "Bài làm gọn, đúng trọng tâm.",
    "Nên hỏi thêm về người cùng quyết định.",
    "Mở đầu tốt, phần chốt cần cụ thể hơn.",
    "Tiến bộ rõ so với các bài trước.",
]
TODOS = [
    ("Kèm Vy về điều kiện hưởng ưu đãi", False, 3),
    ("Đọc lại hội thoại VF 7 của Bảo", False, 2),
    ("Giao Huy bài luyện chốt lái thử", False, 1),
    ("Duyệt hết bài tồn trước thứ Sáu", True, 6),
]
SCENARIO_TITLES = {
    "SCENARIO_01_VF5_TAXI": "Luyện tình huống bác tài chạy dịch vụ cân nhắc VF 5",
    "SCENARIO_02_VF7_VS_CX5": "Luyện so sánh VF 7 với Mazda CX-5",
    "SCENARIO_03_VF6_APARTMENT": "Luyện tình huống sạc pin tại chung cư với VF 6",
    "SCENARIO_04_VF6_ECO_PLUS_UPSELL": "Luyện tư vấn VF 6 Eco và Plus",
}


def digest(value: str) -> int:
    return int(hashlib.sha256(value.encode()).hexdigest()[:12], 16)


def sentences(text: str) -> list[str]:
    return [part for part in re.split(r"(?<=[.?!])\s+", text) if part]


def quote_of(text: str) -> str:
    """The longest sentence, which is always an exact substring of the message."""
    return max(sentences(text), key=len)


def load_scenarios() -> dict[str, dict]:
    return {item["scenario_id"]: item for item in json.loads(SCENARIO_FILE.read_text(encoding="utf-8"))}


def tier_scores(slug: str, index: int, means: dict[str, tuple[float, float]], total: int) -> dict[str, int]:
    """Low-discrepancy sampling keeps each advisor's average close to the target mean."""
    progress = index / (total - 1) if total > 1 else 0.0
    scores = {}
    for criterion, (start, end) in means.items():
        mean = start + (end - start) * progress
        offset = digest(f"{slug}:{criterion}") / 16**12
        draw = (index * 0.6180339887498949 + offset) % 1.0
        low = math.floor(mean)
        scores[criterion] = max(1, min(3, low + (1 if draw < mean - low else 0)))
    return scores


def build_transcript(scenario_id: str, scores: dict[str, int]) -> list[dict]:
    template = TEMPLATES[scenario_id]
    customer = template["customer"]
    advisor = template["advisor"]
    texts = [customer[0]]
    for position, criterion in enumerate(CRITERIA):
        texts.append(advisor[criterion][scores[criterion]])
        texts.append(customer[position + 1] if position + 1 < len(customer) else template["closing_reply"][scores[CL]])
    return [
        {"message_id": f"msg-{number:02d}", "role": "customer" if number % 2 else "advisor", "content": content}
        for number, content in enumerate(texts, 1)
    ]


def build_evaluation(
    session_id: str, scenario_id: str, scores: dict[str, int], messages: list[dict]
) -> SessionEvaluationResult:
    by_slot = {criterion: messages[2 * position + 1] for position, criterion in enumerate(CRITERIA)}
    evaluations = []
    for criterion in CriterionType:
        key = criterion.value
        tier = scores[key]
        message = by_slot[key]
        quote = TranscriptEvidence(message_id=message["message_id"], quote=quote_of(message["content"]))
        evidence = [quote]
        checks = []
        for number, (label, met) in enumerate(zip(CHECKS[key], CHECK_MET[tier], strict=True), 1):
            checks.append(
                ObservableCheckResult(
                    check_id=f"{key}.{number}",
                    verdict=CheckVerdict.MET if met else CheckVerdict.MISSED,
                    evidence=[quote] if met else [],
                    reason=f"{label}: "
                    + ("có bằng chứng trong hội thoại." if met else "chưa thấy bằng chứng trong hội thoại."),
                )
            )
        evaluations.append(
            CriterionEvaluation(
                criterion=criterion,
                status=CriterionStatus.ASSESSED,
                score=tier,
                checks=checks,
                evidence=evidence,
                reason=REASON[key][tier],
                improvement_suggestion=IMPROVE[key].get(tier),
            )
        )
    overall = sum(scores.values()) / len(scores)
    best = max(CRITERIA, key=lambda c: (scores[c], -CRITERIA.index(c)))
    weak = [c for c in CRITERIA if scores[c] == 1][:2]
    findings = []
    if scores[PA] == 1:
        policy_message = by_slot[PA]
        findings.append(
            FactualFinding(
                claim=quote_of(policy_message["content"]),
                message_id=policy_message["message_id"],
                status=FactualClaimStatus.UNVERIFIABLE,
                severity="warning",
                reason="Chưa có nguồn xác nhận cho khẳng định ưu đãi áp dụng cho mọi khách, không cần điều kiện.",
            )
        )
    next_practice = None
    if weak:
        next_practice = RecommendedNextPractice(
            type="scenario",
            target_id=TEMPLATES[scenario_id]["next"],
            reason=f"Luyện thêm vì tiêu chí {weak[0]} đang ở mức thấp.",
        )
    closing = scores[CL] == 3
    return SessionEvaluationResult(
        session_id=session_id,
        scenario_id=scenario_id,
        judge_model="sample-seed",
        closing_outcome="next_step_agreed" if closing else "no_agreement",
        closing_outcome_label="Đã hẹn bước tiếp theo" if closing else "Chưa chốt bước tiếp theo",
        rubric_version=RUBRIC_VERSION,
        assessed_criteria_count=5,
        overall_score=overall,
        passed=overall >= 2.0,
        evaluations=evaluations,
        factual_findings=findings,
        summary_strengths=[STRENGTH[best]] if scores[best] >= 2 else [],
        summary_weaknesses=[WEAKNESS[c] for c in weak],
        recommended_next_practice=next_practice,
        review_status=ReviewStatus.AI_DRAFT,
    )


def build_state(
    session_id: str, scenario: dict, messages: list[dict], draft: SessionEvaluationResult, started_at: datetime
) -> RoleplayState:
    scores = {item.criterion.value: item.score for item in draft.evaluations}
    resolved = [item["objection_id"] for item in scenario["objections"]] if scores[OH] >= 2 else []
    claims = []
    if scores[PA] == 1:
        policy_message = messages[2 * CRITERIA.index(PA) + 1]
        claims = [
            AdvisorFactualClaim(
                message_id=policy_message["message_id"], text=quote_of(policy_message["content"]), category="promotion"
            )
        ]
    return RoleplayState(
        session_id=session_id,
        created_at=started_at,
        scenario_id=scenario["scenario_id"],
        difficulty=scenario["difficulty"],
        sales_channel=scenario.get("sales_channel"),
        training_objective=scenario.get("training_objective"),
        persona=scenario["persona"],
        conversation_stage=ConversationStage.FINISHED,
        turn_count=len(CRITERIA),
        trust_level=min(5, 1 + scores[CL] + (1 if scores[OH] == 3 else 0)),
        interest_level=min(5, 1 + scores[CL] + (1 if scores[ND] == 3 else 0)),
        visible_context=scenario["visible_context"],
        hidden_facts=scenario["hidden_facts"],
        max_turns=scenario["termination_conditions"]["max_turns"],
        resolved_objections=resolved,
        unresolved_objections=[
            item["objection_id"] for item in scenario["objections"] if item["objection_id"] not in resolved
        ],
        customer_goals=scenario["customer_goals"],
        current_intent=scenario["buyer_intent"],
        termination_status=TerminationStatus.COMPLETED,
        termination_reason="Tư vấn viên kết thúc buổi luyện tập.",
        closing_outcome=draft.closing_outcome,
        evaluation_status=EvaluationStatus.COMPLETE,
        evaluation_result=draft,
        messages=[RoleplayMessage(**item) for item in messages],
        factual_claims=claims,
    )


def attempt_week(index: int, total: int) -> int:
    """Spread each advisor across the same eight calendar weeks as the dashboard."""
    return round(index * 7 / (total - 1)) if total > 1 else 7


def completion_time(slug: str, index: int, total: int, newest_days: float, now: datetime) -> datetime:
    local_now = now.astimezone(TZ)
    week_start = (local_now - timedelta(days=local_now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
    week = attempt_week(index, total)
    if week == 7:
        # Keep recent pending work at most four days old, even on Sundays.
        age = min(newest_days, max(0, (local_now - week_start).total_seconds() / 86400 * 0.95))
        return max(week_start.astimezone(UTC), now - timedelta(days=age, minutes=25))
    seed = digest(f"{slug}:{index}:time")
    moment = (
        week_start - timedelta(weeks=7 - week) + timedelta(days=seed % 7, hours=9 + seed % 9, minutes=(seed // 9) % 60)
    )
    return moment.astimezone(UTC)


def demo_scores(week: int, index: int) -> dict[str, int]:
    """Integer criterion scores with explicit weekly means from 1.6 to 2.8."""
    points = (8, 8, 9, 10, 11, 12, 13, 14)[week]
    base, extra = divmod(points, len(CRITERIA))
    return {
        criterion: base + ((position - index) % len(CRITERIA) < extra) for position, criterion in enumerate(CRITERIA)
    }


def build_dataset(now: datetime, advisor_ids: dict[str, str]) -> dict[str, list[dict]]:
    scenarios = load_scenarios()
    scenario_ids = list(TEMPLATES)
    local_now = now.astimezone(TZ)
    rows: dict[str, list[dict]] = {
        name: [] for name in ("attempts", "checkpoints", "reviews", "assignments", "assignment_sessions", "todos")
    }
    attempts: list[dict] = []
    for advisor_index, (slug, _, total, means, newest_days) in enumerate(ADVISORS):
        for index in range(total):
            session_id = f"{PREFIX}s_{slug}_{index + 1:02d}"
            scenario_id = scenario_ids[(index + advisor_index) % len(scenario_ids)]
            completed = completion_time(slug, index, total, newest_days if newest_days is not None else 0.5, now)
            scores = (
                demo_scores(attempt_week(index, total), index)
                if slug == "demo"
                else tier_scores(slug, index, means, total)
            )
            messages = build_transcript(scenario_id, scores)
            started = completed - timedelta(minutes=12 + digest(session_id) % 14)
            draft = build_evaluation(session_id, scenario_id, scores, messages)
            state = build_state(session_id, scenarios[scenario_id], messages, draft, started)
            RoleplayState.model_validate(state.model_dump(mode="json"))
            age = now - completed
            pending = slug != "ha" and index == total - 1 and age < timedelta(days=5)
            attempt = {
                "session_id": session_id,
                "advisor": advisor_ids[slug],
                "slug": slug,
                "scenario_id": scenario_id,
                "completed": completed,
                "draft": draft,
                "pending": pending,
            }
            attempts.append(attempt)
            rows["attempts"].append(
                {
                    "session_id": session_id,
                    "scenario_id": scenario_id,
                    "advisor_id": advisor_ids[slug],
                    "started_at": started,
                    "completed_at": completed,
                    "evaluation_status": EvaluationStatus.COMPLETE.value,
                    "ai_draft_json": draft.model_dump_json(),
                }
            )
            rows["checkpoints"].append(
                {
                    "session_id": session_id,
                    "state_json": json.dumps(
                        state.model_dump(mode="json"), ensure_ascii=False, separators=(",", ":"), sort_keys=True
                    ),
                    "updated_at": completed,
                }
            )

    approved = [item for item in attempts if not item["pending"]]
    policy_pool = [
        item
        for item in approved
        if item["slug"] != "demo"
        and next(e for e in item["draft"].evaluations if e.criterion is CriterionType.POLICY_ACCURACY).score == 2
        and digest(item["session_id"]) % 2 == 0
    ]
    overrides: dict[str, tuple[str, int, str]] = {}
    for position, item in enumerate(policy_pool[: len(OVERRIDE_REASONS_POLICY)]):
        overrides[item["session_id"]] = (PA, 1, OVERRIDE_REASONS_POLICY[position])
    for criterion, before, after, reason in OTHER_OVERRIDES:
        for item in approved:
            if item["slug"] == "demo" or item["session_id"] in overrides:
                continue
            if next(e for e in item["draft"].evaluations if e.criterion.value == criterion).score == before:
                overrides[item["session_id"]] = (criterion, after, reason)
                break
    for item in approved:
        override = overrides.get(item["session_id"])
        comment = None
        if override or digest(item["session_id"] + "comment") % 6 == 0:
            comment = GENERAL_COMMENTS[digest(item["session_id"] + "text") % len(GENERAL_COMMENTS)]
        decision = ManagerReviewDecision(
            score_overrides={override[0]: ScoreOverride(score=override[1], reason=override[2])} if override else {},
            general_comment=comment,
        )
        result = approved_evaluation(item["draft"], decision)
        reviewed = min(
            item["completed"] + timedelta(hours=3 + digest(item["session_id"] + "review") % 27),
            now - timedelta(minutes=5),
        )
        rows["reviews"].append(
            {
                "session_id": item["session_id"],
                "manager_id": MANAGER_ID,
                "reviewed_at": reviewed,
                "change_reason": decision.stored_comment(),
                "approved_result_json": result.model_dump_json(),
            }
        )

    def latest_attempt(slug: str, scenario_id: str):
        matches = [a for a in attempts if a["slug"] == slug and a["scenario_id"] == scenario_id]
        return max(matches, key=lambda a: a["completed"]) if matches else None

    today = local_now.date()
    assignments = [
        # slug, scenario, due offset in days, linked
        ("bao", "SCENARIO_02_VF7_VS_CX5", -4, False),
        ("huy", "SCENARIO_04_VF6_ECO_PLUS_UPSELL", -2, False),
        ("vy", "SCENARIO_03_VF6_APARTMENT", 3, False),
        ("huy", "SCENARIO_01_VF5_TAXI", 5, False),
        ("ngocanh", "SCENARIO_03_VF6_APARTMENT", 7, False),
        ("demo", "SCENARIO_02_VF7_VS_CX5", None, True),
        ("ha", "SCENARIO_01_VF5_TAXI", None, True),
        ("tam", "SCENARIO_03_VF6_APARTMENT", None, True),
        ("linh", "SCENARIO_04_VF6_ECO_PLUS_UPSELL", None, True),
        ("vy", "SCENARIO_02_VF7_VS_CX5", None, True),
        ("demo", "SCENARIO_03_VF6_APARTMENT", 2, False),
        ("demo", "SCENARIO_04_VF6_ECO_PLUS_UPSELL", 7, False),
    ]
    for number, (slug, scenario_id, due_offset, linked) in enumerate(assignments, 1):
        assignment_id = f"{PREFIX}asg_{number:02d}"
        session = latest_attempt(slug, scenario_id) if linked else None
        if linked and session is None:
            session = max((a for a in attempts if a["slug"] == slug), key=lambda a: a["completed"])
            scenario_id = session["scenario_id"]
        if session is not None:
            created = session["completed"] - timedelta(days=4)
            due = (session["completed"].astimezone(TZ) + timedelta(days=2)).date()
        else:
            created = now - timedelta(days=max(1, 9 - number))
            due = today + timedelta(days=due_offset)
        rows["assignments"].append(
            {
                "assignment_id": assignment_id,
                "manager_id": MANAGER_ID,
                "advisor_id": advisor_ids[slug],
                "scenario_id": scenario_id,
                "title": SCENARIO_TITLES[scenario_id],
                "due_date": due,
                "created_at": created,
            }
        )
        if session is not None:
            rows["assignment_sessions"].append({"session_id": session["session_id"], "assignment_id": assignment_id})

    for number, (text, done, days_ago) in enumerate(TODOS, 1):
        created = now - timedelta(days=days_ago)
        rows["todos"].append(
            {
                "todo_id": f"{PREFIX}todo_{number}",
                "manager_id": MANAGER_ID,
                "text": text,
                "done": done,
                "created_at": created,
                "done_at": now - timedelta(days=1) if done else None,
            }
        )
    return rows


def existing_keys(engine, table, column) -> set[str]:
    if not inspect(engine).has_table(table.name):
        return set()
    with engine.connect() as connection:
        return set(connection.execute(select(column).where(column.startswith(PREFIX, autoescape=True))).scalars())


async def ensure_users(engine, auth_repo, apply: bool) -> dict[str, int | str]:
    service = AuthService(auth_repo)
    summary: dict[str, int | str] = {"created": 0, "existing": 0, "renamed": 0}
    has_users = inspect(engine).has_table("users")

    def current(user_id):
        if not has_users:
            return None
        with engine.connect() as connection:
            return connection.execute(
                select(auth_repo._users.c.display_name).where(auth_repo._users.c.user_id == user_id)
            ).scalar_one_or_none()

    wanted = [
        (DEMO_ADVISOR_ID, "advisor.demo", DEFAULT_DEMO_NAME, UserRole.ADVISOR, "DEMO_ADVISOR_PASSWORD"),
        (MANAGER_ID, "manager.demo", DEFAULT_MANAGER_NAME, UserRole.MANAGER, "DEMO_MANAGER_PASSWORD"),
    ]
    for user_id, username, display_name, role, variable in wanted:
        name = current(user_id)
        if name is None:
            password = os.getenv(variable, "")
            if not password:
                raise SystemExit(f"{user_id} does not exist. Set {variable} so the seed script can create it.")
            if apply:
                await service.seed_user(
                    user_id=user_id, username=username, display_name=display_name, role=role, password=password
                )
            summary["created"] += 1
        else:
            summary["existing"] += 1
        # Only replace names the seed itself gave; a name someone set by hand is kept.
        renames = {
            DEMO_ADVISOR_ID: (DEMO_ADVISOR_NAME, (None, DEFAULT_DEMO_NAME, *PREVIOUS_DEMO_NAMES)),
            MANAGER_ID: (DEMO_MANAGER_NAME, (None, DEFAULT_MANAGER_NAME)),
        }
        new_name, replaceable = renames[user_id]
        if name in replaceable:
            summary["renamed"] += 1
            if apply:
                with engine.begin() as connection:
                    connection.execute(
                        update(auth_repo._users)
                        .where(auth_repo._users.c.user_id == user_id)
                        .values(display_name=new_name)
                    )
    return summary


async def seed(database_url: str, *, apply: bool = False, reset: bool = False, now: datetime | None = None) -> dict:
    now = (now or datetime.now(UTC)).astimezone(TZ).replace(second=0, microsecond=0).astimezone(UTC)
    engine = create_engine(normalize_database_url(database_url), pool_pre_ping=True)
    try:
        auth_repo = SQLAuthRepository(database_url, engine=engine)
        records = SQLPracticeRecordsRepository(database_url, engine=engine)
        checkpoints = SQLCheckpointRepository(database_url, engine=engine)
        users = await ensure_users(engine, auth_repo, apply)
        advisor_ids = {
            slug: (DEMO_ADVISOR_ID if slug == "demo" else f"{PREFIX}advisor_{slug}") for slug, *_ in ADVISORS
        }
        sample_users = 0
        if apply:
            service = AuthService(auth_repo)
            for slug, name, *_ in ADVISORS:
                if slug == "demo":
                    continue
                if await service.active_advisor(advisor_ids[slug]) is not None:
                    # Sample advisors belong to the seed, so keep their names in step with ADVISORS.
                    with engine.begin() as connection:
                        connection.execute(
                            update(auth_repo._users)
                            .where(auth_repo._users.c.user_id == advisor_ids[slug])
                            .values(display_name=name)
                        )
                    continue
                await service.seed_user(
                    user_id=advisor_ids[slug],
                    username=f"showcase.{slug}",
                    display_name=name,
                    role=UserRole.ADVISOR,
                    password=secrets.token_urlsafe(24),
                )
                sample_users += 1
        else:
            existing_users: set[str] = set()
            if inspect(engine).has_table("users"):
                with engine.connect() as connection:
                    existing_users = set(connection.execute(select(auth_repo._users.c.user_id)).scalars())
            sample_users = sum(1 for slug, *_ in ADVISORS if slug != "demo" and advisor_ids[slug] not in existing_users)

        rows = build_dataset(now, advisor_ids)
        tables = {
            "attempts": (records._attempts, records._attempts.c.session_id),
            "checkpoints": (checkpoints._table, checkpoints._table.c.session_id),
            "reviews": (records._reviews, records._reviews.c.session_id),
            "assignments": (records._assignments, records._assignments.c.assignment_id),
            "assignment_sessions": (records._assignment_sessions, records._assignment_sessions.c.session_id),
            "todos": (records._todos, records._todos.c.todo_id),
        }
        key_names = {
            "attempts": "session_id",
            "checkpoints": "session_id",
            "reviews": "session_id",
            "assignments": "assignment_id",
            "assignment_sessions": "session_id",
            "todos": "todo_id",
        }
        reset_counts = {
            name: len(existing_keys(engine, table, column)) if reset else 0 for name, (table, column) in tables.items()
        }
        pending_insert = {}
        for name, (table, column) in tables.items():
            have = set() if reset else existing_keys(engine, table, column)
            pending_insert[name] = [row for row in rows[name] if row[key_names[name]] not in have]
        if apply:
            records._ensure_schema()
            checkpoints._ensure_schema()
            with engine.begin() as connection:
                if reset:
                    # Delete children before parents; match literal underscores in PREFIX.
                    for name in ("assignment_sessions", "reviews", "checkpoints", "todos", "assignments", "attempts"):
                        table, column = tables[name]
                        connection.execute(delete(table).where(column.startswith(PREFIX, autoescape=True)))
                for name in ("attempts", "checkpoints", "assignments", "reviews", "assignment_sessions", "todos"):
                    if pending_insert[name]:
                        connection.execute(insert(tables[name][0]), pending_insert[name])
        approved = len(rows["reviews"])
        total = len(rows["attempts"])
        return {
            "applied": apply,
            "reset": reset,
            "rows_deleted" if apply else "rows_would_delete": reset_counts,
            "batch": PREFIX,
            "demo_users": users,
            "sample_advisors_created": sample_users,
            "rows_planned": {name: len(values) for name, values in rows.items()},
            "rows_inserted" if apply else "rows_would_insert": {
                name: len(values) for name, values in pending_insert.items()
            },
            "attempts_approved": approved,
            "attempts_pending": total - approved,
            "approved_with_overrides": sum(
                1 for r in rows["reviews"] if '"manager_reason":"' in r["approved_result_json"]
            ),
            "approved_with_comment": sum(1 for r in rows["reviews"] if r["change_reason"]),
        }
    finally:
        engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--apply", action="store_true", help="write rows; without it nothing is changed")
    parser.add_argument(
        "--reset",
        action="store_true",
        help="refresh seed-prefixed rows only; preserves users and non-seed rows; requires --apply to write",
    )
    args = parser.parse_args()
    load_dotenv()
    result = asyncio.run(seed(get_settings().database_url, apply=args.apply, reset=args.reset))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if not args.apply:
        print("Dry run only. Re-run with --apply to write.")


if __name__ == "__main__":
    main()
