import asyncio
from aiogram import Bot, types
from aiogram.dispatcher import Dispatcher
from aiogram.utils import executor
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.dispatcher.filters import Text
from langchain.document_loaders import NewsURLLoader
from googletrans import Translator
import re
import os

from openai import OpenAI

# Configure bot and dispatcher
bot = Bot(token='6799661102:AAFPZS-sYon5h1XGymwILNV00Xhy4BabbSc')
dp = Dispatcher(bot)

# Save data for each user
data = {}

# Define the emojis pattern
emoji_pattern = r"[\U0001F600-\U0001F64F]+"

def split_message(text, max_length=4096):
    """
    Splits a long text into parts, each with a maximum specified length.
    """
    return [text[i:i+max_length] for i in range(0, len(text), max_length)]

def generate_post_content(choice, link, text, event):
    """
    Generates the content of the post based on user choices.
    """
    link_text = f'(Link - {link})' if choice == "link" else ''
    if event:
        # Generating event post content
        return f'''
        Generate a post fully in Ukrainian based on this article {link_text}.
        Here is the article:
         ```{text}```
        Use these rules for the post:
            - Emphasize the city name with leading emojis.
            - Clearly state the event name.
            - Include the date and time of the event.
            - Mention the venue name and address (if the 'link' choice is selected, include the provided link).
            - If a ticket link is available and 'link' choice is selected, include it in the post.
            - The main text of the post should describe the event, following the principles of the provided 'main text' template.
        '''
    else:
        # Generating general post content
        return f'''
            Generate markdown text for post post fully in Ukrainian based on this article {link_text}.
            Here is the article:
            ```{text}```
            Use these rules:
                Headline:
                    1. The title should convey the main idea of the post. (Maximum 5-10 words)
                    2. It is always bold(**).
                    3. 1-2 thematic emojis are always used at the beginning of the title.
                    4. A period is always placed at the end of the title.
                    5. The title should be in the very beginning of the post.

                Introduction:
                    1. There is always a blank line after the title.
                    2. Then there can be 1-2 sentences that mention an interesting fact from the material.
                    3. This text is written in italics, and emojis are not used.

                Main Text:
                    1. This is a maximum of 200-300 characters.
                    2. The text can be divided into 2-3 paragraphs.
                    3. Important parts of the text and words are ALWAYS highlighted in bold(**).
                    4. Thematic emojis are mandatory in the text. (6 emojis per paragraph)
                    5. At the end of a sentence, if there is an emoji, a period is not placed. Correct: "...the end✊". Incorrect: "...the end.✊".
                    6. If a list of something is enumerated, square emojis ▪️ are used in the beginning. Incorrect: "1. The beginning". Correct: "▪️The beginning".
                    7. The text never uses quotes “”, but instead uses «».
                    8. A period is always placed at the end of the main text.
                Source Reference:
                    ▪️source + link
            '''

# Menu buttons
text_button = InlineKeyboardButton('📝 Текст', callback_data='text')
link_button = InlineKeyboardButton('🔗 Посилання', callback_data='link')
emojis_button = InlineKeyboardButton('✨ З емодзі', callback_data='emojis')
no_emojis_button = InlineKeyboardButton('🚫 Без емодзі', callback_data='no_emojis')
event_button = InlineKeyboardButton('🎉 Подія', callback_data='event')
no_event_button = InlineKeyboardButton('🚫 Без події', callback_data='no_event')

# Start function with personalized greeting
@dp.message_handler(commands=['start'])
async def start(message: types.Message):
    user_name = message.from_user.first_name or "там"
    keyboard_markup = InlineKeyboardMarkup().add(text_button, link_button)
    await message.reply(f'Привіт, {user_name}!')
    await bot.send_message(message.from_user.id, f'🌟 Виберіть, як ви хочете ввести інформацію для публікації:', reply_markup=keyboard_markup)

# Handler for text or link input
@dp.callback_query_handler(lambda callback_query: callback_query.data in ('text', 'link'))
async def get_input_type(callback_query: types.CallbackQuery):
    await bot.delete_message(callback_query.from_user.id, callback_query.message.message_id)
    data[callback_query.from_user.id] = {'input_type': callback_query.data}
    keyboard_markup = InlineKeyboardMarkup().add(emojis_button, no_emojis_button)
    await bot.send_message(callback_query.from_user.id, 'Будуть емодзі в публікації?', reply_markup=keyboard_markup)

# Handler for emojis selection
@dp.callback_query_handler(lambda callback_query: callback_query.data in ('emojis', 'no_emojis'))
async def get_emojis(callback_query: types.CallbackQuery):
    await bot.delete_message(callback_query.from_user.id, callback_query.message.message_id)
    data[callback_query.from_user.id]['emojis'] = (callback_query.data == 'emojis')
    keyboard_markup = InlineKeyboardMarkup().add(event_button, no_event_button)
    await bot.send_message(callback_query.from_user.id, 'Буде подія в публікації?', reply_markup=keyboard_markup)

# Handler for event selection
@dp.callback_query_handler(lambda callback_query: callback_query.data in ('event', 'no_event'))
async def get_event(callback_query: types.CallbackQuery):
    await bot.delete_message(callback_query.from_user.id, callback_query.message.message_id)
    data[callback_query.from_user.id]['event'] = (callback_query.data == 'event')
    input_type = 'текст' if data[callback_query.from_user.id]['input_type'] == 'text' else 'посилання'
    await bot.send_message(callback_query.from_user.id, f'Введіть {input_type} для публікації:')

# Handler for receiving the publication text or link
@dp.message_handler(lambda message: message.text)
async def get_text_for_publication(message: types.Message):
    user_data = data[message.from_user.id]
    if user_data['input_type'] == 'text':
        user_data['text'] = message.text
        user_data['link'] = ''
    else:
        user_data['link'] = message.text
        try:
            loader = NewsURLLoader(urls=[user_data['link']])
            article = loader.load()
            user_data['text'] = article[0].page_content

        except Exception as e:
            print(e)
            await bot.send_message(message.from_user.id, 'Помилка при завантаженні даних. Перевірте правильність посилання.')
            return
    output = generate_post_content(user_data['input_type'], user_data['link'], user_data['text'], user_data['event'])
    data[message.from_user.id]['output'] = output
    if not user_data['emojis']:
        output = re.sub(emoji_pattern, '', output)

    await bot.send_message(message.from_user.id, 'Ось ваша публікація:')
    if len(output) > 4096:
        parts = split_message(output)
        for part in parts:
            await bot.send_message(message.from_user.id, part)
    else:
        await bot.send_message(message.from_user.id, output)

# Run the bot
if __name__ == '__main__':
    executor.start_polling(dp, skip_updates=True)
