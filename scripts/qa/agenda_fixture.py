"""Loopback UI QA: isolated SQLite and synthetic customers, no external AI requests."""
from datetime import UTC, datetime, timedelta
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.qa.shared_sales_copilot_fixture import app, repo, identity, graph
from src.models.sales_copilot import CustomerProfileSnapshot, FollowupTask
from src.services import copilot_query
from src.services.sales_agenda_service import SalesAgendaService, TZ

agenda = SalesAgendaService(repo)
today = datetime.now(TZ).replace(hour=9, minute=0, second=0, microsecond=0)
customer = repo.create_customer(name="Khách QA lịch hẹn", advisor_id=identity.user_id)
conversation = repo.get_or_create_conversation(customer)
repo.add_message(conversation, 'customer', 'Cần tư vấn lịch lái thử')
repo.save_facts_and_snapshot(customer, [], CustomerProfileSnapshot(interested_models=['VF 8'], unresolved_questions=['Sạc tại nhà', 'Phương án trả góp']))
for title, offset, minutes, kind, linked in [
    ('Tư vấn VF 8', 0, 60, 'task', True),
    ('Lái thử cùng khách', 30, 60, 'appointment', True),
    ('Họp nhóm sales', 120, 45, 'appointment', False),
    ('Qua nửa đêm', 870, 90, 'task', False),
    ('Sự kiện tuần tới', 7*1440, 60, 'appointment', False),
]:
    agenda.create(identity.user_id, {'title':title, 'description':'Dữ liệu QA tách biệt', 'starts_at':today+timedelta(minutes=offset),
        'ends_at':today+timedelta(minutes=offset+minutes), 'item_type':kind, 'priority':'high',
        'customer_id':customer if linked else None})
repo.save_tasks([FollowupTask(customer_id=customer, conversation_id=conversation, owner_sales_id=identity.user_id,
    task_type='follow_up', title='Đề xuất cần duyệt', description='', status='needs_review')])

async def slow_graph(state, **kwargs):
    import asyncio
    await asyncio.sleep(5)
    return await graph(state, **kwargs)
copilot_query.copilot_agent.ainvoke = slow_graph

if __name__ == '__main__':
    import uvicorn
    uvicorn.run(app, host='127.0.0.1', port=8004, log_level='warning')
