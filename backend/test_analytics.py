import asyncio
from app.db.session import async_session
from app.api.v1.analytics import analytics_summary

async def main():
    async with async_session() as db:
        res = await analytics_summary(db=db, user=None, date_range="week", source="all", confidence_threshold=85.0)
        print(res.model_dump_json(indent=2))

asyncio.run(main())
