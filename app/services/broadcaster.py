import asyncio
import logging

import httpx
log=logging.getLogger(__name__)

THROTTLE=0.04

async def broadcast(
        text:str,
        owners_ids:list[int],
        bot_url:str,
        internal_token:str,
        )->dict:
    sent=failed=0

    async with httpx.AsyncClient(timeout=5) as client:
        for owner_id in owners_ids:
            try:
                response = await client.post(
                    f"{bot_url}/notify",
                    json={"chat_id": f"{owner_id}", "text": text},
                    headers={"X-Internal-Token": internal_token},
                )
                response.raise_for_status()
                sent += 1
            except httpx.HTTPError as err:
                failed += 1
                log.warning("broadcast: failed for %s: %s",owner_id,err)
            await asyncio.sleep(THROTTLE)
        return {"sent":sent,"failed":failed}