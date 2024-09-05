from sqlalchemy import select
from telethon import TelegramClient, events

from bot_meg.config import config
from bot_meg.database import Session
from bot_meg.models import Forward

client = TelegramClient('anon', config['API_ID'], config['API_HASH'])


@client.on(events.NewMessage(incoming=True))
async def on_message(event):
    if event.is_private:
        return
    with Session() as session:
        chat = await client.get_entity(event.chat_id)
        query = select(Forward).where(Forward.from_chat == chat.title)
        for forward_model in session.scalars(query).all():
            await client.send_message(
                int(forward_model.to_chat_id), event.message
            )


if __name__ == '__main__':
    client.start()
    client.run_until_disconnected()
