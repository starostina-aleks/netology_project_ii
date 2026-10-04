import asyncio
import json
import logging

log=logging.getLogger(__name__)

POLL_INTERVAL=10.0

async  def drain_alert(
        bot,backend,admin_chat_id: int | None
)->None:
    while True:
        if admin_chat_id is None:
            await asyncio.sleep(60)
            continue
        try:
            alerts = await backend.fetch_pending_alerts()
            for a in alerts:
                payload_s = json.dumps(
                    a.get("payload",{}),ensure_ascii=False,indent=2
                )
                text=(
                    f"⚠️ <b>{a['kind']}</b>\n<pre>{payload_s}</pre>"
                )
                try:
                    await bot.send_message(chat_id=admin_chat_id,text=text,parse_mode="HTML")
                    await backend.ack_alert(a["id"])
                except Exception as e:
                    log.warning(
                        "alert delivery failed id=%s: %s", a.get("id"),e)
        except Exception as e:
            log.warning("alert drain loop: %s",e)
        await asyncio.sleep(POLL_INTERVAL)

