import asyncio
from pathlib import Path

import telebot
from sqlalchemy import select
from telebot.util import quick_markup, update_types
from telethon import TelegramClient

from bot_meg.config import config
from bot_meg.database import Session
from bot_meg.models import Forward, Message, WelcomeMessage

bot = telebot.TeleBot(config['BOT_TOKEN'])
members_message = []


@bot.message_handler(commands=['help', 'start'])
def start(message):
    bot.send_message(
        message.chat.id,
        'Escolha uma opção',
        reply_markup=quick_markup(
            {
                'Encaminhar Mensagens': {'callback_data': 'forward_messages'},
                'Encaminhamentos': {'callback_data': 'show_forwards'},
                'Adicionar Mensagem de Boas Vindas': {
                    'callback_data': 'add_welcome_message'
                },
                'Mensagem de Boas Vindas': {
                    'callback_data': 'show_welcome_messages'
                },
                'Enviar Mensagens Para Membros': {
                    'callback_data': 'send_messages_for_members'
                },
            },
            row_width=1,
        ),
    )


@bot.callback_query_handler(func=lambda c: c.data == 'forward_messages')
def forward_messages(callback_query):
    bot.send_message(
        callback_query.message.chat.id,
        'Digite o titulo do Grupo/Canal de onde vai encaminhar as mensagens',
    )
    bot.register_next_step_handler(callback_query.message, on_from_chat)


def on_from_chat(message):
    bot.send_message(
        message.chat.id,
        'Digite o titulo do Grupo/Canal para onde vai encaminhar as mensagens',
    )
    bot.register_next_step_handler(
        message, lambda m: on_to_chat(m, message.text)
    )


def on_to_chat(message, from_chat):
    to_chat_id = None
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    to_chat_id = loop.run_until_complete(get_to_chat_id(message.text))
    loop.close()
    if to_chat_id is None:
        bot.send_message(message.chat.id, 'Titulo dos Canais/Grupos Errados')
        start(message)
        return
    with Session() as session:
        query = (
            select(Forward)
            .where(Forward.from_chat == from_chat)
            .where(Forward.to_chat == message.text)
        )
        forward_model = session.scalars(query).first()
        if forward_model is None:
            forward_model = Forward(
                from_chat=from_chat,
                to_chat=message.text,
                to_chat_id=str(to_chat_id),
            )
            session.add(forward_model)
            session.commit()
    bot.send_message(
        message.chat.id,
        'Deseja Encaminhar as Mensagens Antigas?',
        reply_markup=quick_markup(
            {
                'Sim': {
                    'callback_data': f'forward_old_messages:{from_chat}:{message.text}'
                },
                'Não': {'callback_data': 'return_to_main_menu'},
            }
        ),
    )


async def get_to_chat_id(to_chat):
    async with TelegramClient(
        'anon2', config['API_ID'], config['API_HASH']
    ) as client:
        to_chat_id = None
        async for dialog in client.iter_dialogs(limit=100):
            if not dialog.message.is_private:
                if dialog.message.chat.title == to_chat:
                    to_chat_id = dialog.message.chat.id
        return to_chat_id


@bot.callback_query_handler(func=lambda c: 'forward_old_messages:' in c.data)
def forward_old_messages(callback_query):
    from_chat, to_chat = callback_query.data.split(':')[1:]
    waiting_message = bot.send_message(
        callback_query.message.chat.id, 'Encaminhando Mensagens...'
    )
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    response = loop.run_until_complete(
        forward_messages_action(from_chat, to_chat)
    )
    loop.close()
    bot.delete_message(callback_query.message.chat.id, waiting_message.id)
    bot.send_message(callback_query.message.chat.id, response)
    start(callback_query.message)


async def forward_messages_action(from_chat, to_chat):
    async with TelegramClient(
        'anon2', config['API_ID'], config['API_HASH']
    ) as client:
        from_chat_id = to_chat_id = None
        async for dialog in client.iter_dialogs(limit=100):
            if not dialog.message.is_private:
                if dialog.message.chat.title == from_chat:
                    from_chat_id = dialog.message.chat.id
                elif dialog.message.chat.title == to_chat:
                    to_chat_id = dialog.message.chat.id
        if from_chat_id and to_chat_id:
            async for message in client.iter_messages(
                from_chat_id, reverse=True
            ):
                try:
                    await client.send_message(to_chat_id, message)
                except:
                    continue
                await asyncio.sleep(3)
            return 'Mensagens Encaminhadas!'
        else:
            with Session() as session:
                if from_chat_id is None:
                    query = select(Forward).where(
                        Forward.from_chat == from_chat
                    )
                else:
                    query = select(Forward).where(Forward.to_chat == to_chat)
                forward_model = session.scalars(query).first()
                session.delete(forward_model)
                session.commit()
            return 'Titulo dos Canais/Grupos Errados'


@bot.callback_query_handler(func=lambda c: c.data == 'show_forwards')
def show_forwards(callback_query):
    with Session() as session:
        reply_markup = {}
        for forward in session.scalars(select(Forward)).all():
            reply_markup[f'{forward.from_chat} - {forward.to_chat}'] = {
                'callback_data': f'show_forward_menu:{forward.id}'
            }
        reply_markup['Voltar'] = {'callback_data': 'return_to_main_menu'}
        bot.send_message(
            callback_query.message.chat.id,
            'Encaminhamentos',
            reply_markup=quick_markup(reply_markup, row_width=1),
        )


@bot.callback_query_handler(func=lambda c: 'show_forward_menu:' in c.data)
def show_forward_menu(callback_query):
    forward_id = int(callback_query.data.split(':')[-1])
    bot.send_message(
        callback_query.message.chat.id,
        'Escolha uma Opção',
        reply_markup=quick_markup(
            {
                'Excluir': {'callback_data': f'delete_forward:{forward_id}'},
                'Voltar': {'callback_data': 'show_forwards'},
            },
            row_width=1,
        ),
    )


@bot.callback_query_handler(func=lambda c: 'delete_forward:' in c.data)
def delete_forward(callback_query):
    forward_id = int(callback_query.data.split(':')[-1])
    with Session() as session:
        forward_model = session.get(Forward, forward_id)
        session.delete(forward_model)
        session.commit()
    bot.send_message(
        callback_query.message.chat.id, 'Encaminhamento Removido!'
    )
    start(callback_query.message)


@bot.callback_query_handler(
    func=lambda c: c.data == 'send_messages_for_members'
)
def send_messages_for_members(callback_query):
    bot.send_message(
        callback_query.message.chat.id,
        'Digite o titulo do Grupo/Canal para qual deseja enviar as mensagens para os membros',
    )
    bot.register_next_step_handler(callback_query.message, on_members_chat)


def on_members_chat(message):
    global members_message
    members_message = []
    bot.send_message(
        message.chat.id,
        'Envie as mensagens que deseja enviar para os membros, digite /enviar para enviar',
    )
    bot.register_next_step_handler(
        message, lambda m: on_members_message(m, message.text)
    )


def on_members_message(message, chat_title):
    global members_message
    if message.text == '/enviar':
        waiting_message = bot.send_message(
            message.chat.id, 'Enviando Mensagens...'
        )
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        response = loop.run_until_complete(send_members_message(chat_title))
        loop.close()
        bot.delete_message(message.chat.id, waiting_message.id)
        bot.send_message(message.chat.id, response)
        members_message = []
        start(message)
    else:
        file_path = file_info = None
        if message.photo:
            file_info = bot.get_file(message.photo[-1].file_id)
        elif message.video:
            file_info = bot.get_file(message.video.file_id)
        elif message.audio:
            file_info = bot.get_file(message.audio.file_id)
        elif message.voice:
            file_info = bot.get_file(message.voice.file_id)
        elif message.document:
            file_info = bot.get_file(message.document.file_id)
        if file_info:
            downloaded_file = bot.download_file(file_info.file_path)
            file_path = (
                Path('files')
                / f'{file_info.file_id}.{file_info.file_path.split(".")[-1]}'
            )
            with open(file_path, 'wb') as f:
                f.write(downloaded_file)
        if file_path:
            members_message.append({'type': 'file', 'content': file_path})
        else:
            members_message.append({'type': 'text', 'content': message.text})
        bot.register_next_step_handler(
            message, lambda m: on_members_message(m, chat_title)
        )


async def send_members_message(chat_title):
    async with TelegramClient(
        'anon2', config['API_ID'], config['API_HASH']
    ) as client:
        chat_id = None
        async for dialog in client.iter_dialogs(limit=100):
            if not dialog.message.is_private:
                if dialog.message.chat.title == chat_title:
                    chat_id = dialog.message.chat.id
        if chat_id:
            async for user in client.iter_participants(chat_id):
                for message in members_message:
                    if message['type'] == 'text':
                        await client.send_message(user, message['content'])
                    else:
                        await client.send_file(user, str(message['content']))
                    await asyncio.sleep(3)
            return 'Mensagens Enviadas!'
        else:
            return 'Titulo do Canal/Grupo Errado'


@bot.callback_query_handler(func=lambda c: c.data == 'add_welcome_message')
def add_welcome_message(callback_query):
    bot.send_message(
        callback_query.message.chat.id,
        'Digite o titulo do Grupo/Canal para qual deseja enviar as mensagens de boas vindas',
    )
    bot.register_next_step_handler(
        callback_query.message, on_welcome_message_chat
    )


def on_welcome_message_chat(message):
    with Session() as session:
        welcome_message = WelcomeMessage(chat=message.text)
        session.add(welcome_message)
        session.commit()
        session.flush()
        welcome_message_id = welcome_message.id
    bot.send_message(
        message.chat.id,
        'Envie as Mensagens de Boas Vindas, Digite /salvar para Salvar as Alterações',
    )
    bot.register_next_step_handler(
        message,
        lambda m: on_welcome_message(m, message.text, welcome_message_id),
    )


def on_welcome_message(message, chat, welcome_message_id):
    if message.text == '/salvar':
        bot.send_message(
            message.chat.id, 'Mensagem de Boas Vindas Adicionadas!'
        )
        start(message)
    else:
        file_path = file_info = None
        if message.photo:
            file_info = bot.get_file(message.photo[-1].file_id)
            message_type = 'photo'
        elif message.video:
            file_info = bot.get_file(message.photo[-1].file_id)
            message_type = 'video'
        elif message.audio:
            file_info = bot.get_file(message.audio.file_id)
            message_type = 'audio'
        elif message.voice:
            file_info = bot.get_file(message.voice.file_id)
            message_type = 'voice'
        elif message.document:
            file_info = bot.get_file(message.document.file_id)
            message_type = 'document'
        else:
            message_type = 'text'
        if file_info:
            downloaded_file = bot.download_file(file_info.file_path)
            file_path = (
                Path('files')
                / f'{file_info.file_id}.{file_info.file_path.split(".")[-1]}'
            )
            with open(file_path, 'wb') as f:
                f.write(downloaded_file)
        with Session() as session:
            welcome_message = session.get(WelcomeMessage, welcome_message_id)
            if file_path:
                message_model = Message(
                    welcome_message=welcome_message,
                    message_type=message_type,
                    content=str(file_path),
                )
                session.add(message_model)
            else:
                message_model = Message(
                    welcome_message=welcome_message,
                    message_type=message_type,
                    content=message.text,
                )
                session.add(message_model)
            session.commit()
        bot.register_next_step_handler(
            message, lambda m: on_welcome_message(m, chat, welcome_message_id)
        )


@bot.callback_query_handler(func=lambda c: c.data == 'show_welcome_messages')
def show_welcome_messages(callback_query):
    with Session() as session:
        reply_markup = {}
        for welcome_message in session.scalars(select(WelcomeMessage)).all():
            reply_markup[welcome_message.chat] = {
                'callback_data': f'show_welcome_message_menu:{welcome_message.id}'
            }
        reply_markup['Voltar'] = {'callback_data': 'return_to_main_menu'}
        bot.send_message(
            callback_query.message.chat.id,
            'Mensagem de Boas Vindas',
            reply_markup=quick_markup(reply_markup, row_width=1),
        )


@bot.callback_query_handler(
    func=lambda c: 'show_welcome_message_menu:' in c.data
)
def show_welcome_message_menu(callback_query):
    welcome_message_id = int(callback_query.data.split(':')[-1])
    bot.send_message(
        callback_query.message.chat.id,
        'Escolha uma Opção',
        reply_markup=quick_markup(
            {
                'Visualizar Mensagem': {
                    'callback_data': f'see_welcome_message:{welcome_message_id}'
                },
                'Excluir': {
                    'callback_data': f'delete_welcome_message:{welcome_message_id}'
                },
                'Voltar': {'callback_data': 'show_welcome_messages'},
            },
            row_width=1,
        ),
    )


@bot.callback_query_handler(func=lambda c: 'see_welcome_message:' in c.data)
def see_welcome_message(callback_query):
    welcome_message_id = int(callback_query.data.split(':')[-1])
    with Session() as session:
        welcome_message = session.get(WelcomeMessage, welcome_message_id)
        for message in welcome_message.messages:
            if message.message_type == 'document':
                bot.send_document(
                    callback_query.message.chat.id, open(message.content, 'rb')
                )
            elif message.message_type == 'photo':
                bot.send_photo(
                    callback_query.message.chat.id, open(message.content, 'rb')
                )
            elif message.message_type == 'video':
                bot.send_video(
                    callback_query.message.chat.id, open(message.content, 'rb')
                )
            elif message.message_type == 'audio':
                bot.send_audio(
                    callback_query.message.chat.id, open(message.content, 'rb')
                )
            elif message.message_type == 'voice':
                bot.send_voice(
                    callback_query.message.chat.id, open(message.content, 'rb')
                )
            elif message.message_type == 'text':
                bot.send_message(
                    callback_query.message.chat.id, message.content
                )
    bot.send_message(
        callback_query.message.chat.id,
        'Escolha uma Opção',
        reply_markup=quick_markup(
            {
                'Visualizar Mensagem': {
                    'callback_data': f'see_welcome_message:{welcome_message_id}'
                },
                'Excluir': {
                    'callback_data': f'delete_welcome_message:{welcome_message_id}'
                },
                'Voltar': {'callback_data': 'show_welcome_messages'},
            },
            row_width=1,
        ),
    )


@bot.callback_query_handler(func=lambda c: 'delete_welcome_message:' in c.data)
def delete_welcome_message(callback_query):
    welcome_message_id = int(callback_query.data.split(':')[-1])
    with Session() as session:
        welcome_message_model = session.get(WelcomeMessage, welcome_message_id)
        session.delete(welcome_message_model)
        session.commit()
    bot.send_message(
        callback_query.message.chat.id, 'Mensagem de Boas Vindas Removida!'
    )
    start(callback_query.message)


@bot.callback_query_handler(func=lambda c: c.data == 'return_to_main_menu')
def return_to_main_menu(callback_query):
    start(callback_query.message)


@bot.message_handler(content_types=['new_chat_members'])
def on_new_group_member(message):
    with Session() as session:
        query = select(WelcomeMessage).where(
            WelcomeMessage.chat == message.chat.title
        )
        welcome_message = session.scalars(query).first()
        if welcome_message:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(
                send_welcome_message(welcome_message.id, message.from_user.id)
            )
            loop.close()


@bot.chat_join_request_handler()
def on_chat_join_request(request):
    with Session() as session:
        query = select(WelcomeMessage).where(
            WelcomeMessage.chat == request.chat.title
        )
        welcome_message = session.scalars(query).first()
        if welcome_message:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(
                send_welcome_message(welcome_message.id, request.from_user.id)
            )
            loop.close()


@bot.chat_member_handler()
def on_new_channel_member(update):
    if update.new_chat_member.status == 'member':
        with Session() as session:
            query = select(WelcomeMessage).where(
                WelcomeMessage.chat == update.chat.title
            )
            welcome_message = session.scalars(query).first()
            if welcome_message:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                loop.run_until_complete(
                    send_welcome_message(
                        welcome_message.id, update.from_user.id
                    )
                )
                loop.close()


async def send_welcome_message(welcome_message_id, user_id):
    async with TelegramClient(
        'anon2', config['API_ID'], config['API_HASH']
    ) as client:
        with Session() as session:
            welcome_message = session.get(WelcomeMessage, welcome_message_id)
            async for dialog in client.iter_dialogs(limit=100):
                if not dialog.message.is_private and dialog.message.chat.title == welcome_message.chat:
                    async for user in client.iter_participants(dialog.message.chat.id):
                        if user.id == user_id:
                            for message in welcome_message.messages:
                                if message.message_type == 'text':
                                    await client.send_message(user, message.content)
                                else:
                                    await client.send_file(user, message.content)


if __name__ == '__main__':
    bot.infinity_polling(allowed_updates=update_types)
