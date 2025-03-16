import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, ContextTypes, filters
from dotenv import load_dotenv
import logging
from database import Database
from config import config
import asyncio
from check_bot import SubscriptionChecker

# Загрузка переменных окружения
load_dotenv()

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(уровень)s - %(сообщение)s'
)
logger = logging.getLogger(__name__)

db = Database()
subscription_checker = SubscriptionChecker()

# Состояния пользователя
class States:
    WAITING_SCREENSHOT = "waiting_screenshot"
    NORMAL = "normal"
    ADMIN = "admin"
    WAITING_TASK_DESCRIPTION = "waiting_task_description"
    WAITING_TASK_REWARD = "waiting_task_reward"
    WAITING_CHANNEL_LINK = "waiting_channel_link"
    # Добавляем состояния редактирования
    EDIT_DESCRIPTION = "edit_description"
    EDIT_REWARD = "edit_reward"
    EDIT_LINK = "edit_link"
    EDIT_POSITION = "edit_position"

# Создание главной клавиатуры
def get_main_keyboard():
    keyboard = ReplyKeyboardMarkup([
        ["✅ Мои задания ✅"],
        [f"Баланс: 0 ₽", "Поддержка"]
    ], resize_keyboard=True)
    return keyboard

# Функция для создания главной клавиатуры с актуальным балансом
async def get_main_keyboard_with_balance(user_id: int):
    balance = await db.get_balance(user_id)
    keyboard = ReplyKeyboardMarkup([
        ["✅ Мои задания ✅"],
        [f"Баланс: {balance} ₽", "Поддержка"]
    ], resize_keyboard=True)
    return keyboard

# Обработчик команды /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        user_id = update.effective_user.id
        logger.info(f"Запущена команда /start пользователем {user_id}")
        
        # Добавляем отладочное логирование
        logger.info(f"Admin IDs: {config['admin_ids']}")
        logger.info(f"Current user ID: {user_id}")
        logger.info(f"Is admin check: {user_id in config['admin_ids']}")
        
        # Проверяем, админ ли это
        if user_id in config['admin_ids']:
            logger.info("Пользователь является админом, показываем админ-меню")
            await show_admin_menu(update, context)
            return
        else:
            logger.info("Пользователь не является админом, показываем обычное меню")

        # Создаем инлайн клавиатуру для обычного пользователя
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton(config["understand_button"], callback_data="understand")]
        ])
        
        await update.message.reply_text(
            text=config["welcome_message"],
            reply_markup=keyboard
        )
        context.user_data['state'] = States.NORMAL
        
    except Exception as e:
        logger.error(f"Ошибка в start: {e}", exc_info=True)

# Обработчик нажатия кнопки
async def button_click(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        query = update.callback_query
        user_id = query.from_user.id
        
        logger.info(f"Получен callback query от пользователя {user_id}")
        
        await query.answer()
        await query.message.delete()
        
        # Используем новую функцию
        keyboard = await get_main_keyboard_with_balance(user_id)
        
        await query.message.reply_text(
            "Выберите действие:",
            reply_markup=keyboard
        )
        
        logger.info(f"Отправлено главное меню пользователю {user_id}")
        
    except Exception as e:
        logger.error(f"Ошибка в button_click: {e}", exc_info=True)

# Обработчик кнопки "Мои задания"
async def show_tasks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        user_id = update.effective_user.id
        tasks = await db.get_available_tasks(user_id)
        
        if not tasks:
            await update.message.reply_text(
                "На данный момент нет доступных заданий 😔\n"
                "Попробуйте проверить позже!"
            )
            return

        # Сохраняем задания в контексте
        context.user_data['available_tasks'] = tasks
        context.user_data['task_index'] = 0

        # Показываем первое доступное задание
        task = tasks[0]
        
        # Добавляем проверку ссылок
        if task['type'] == 'subscribe':
            channel_link = task['extra_data'].get('channel_link', '')
            if not channel_link.startswith('https://'):
                channel_link = f"https://t.me/{channel_link.lstrip('@')}"
            
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("👉 Перейти в канал", url=channel_link)],
                [InlineKeyboardButton("✅ Проверить подписку", callback_data=f"check_sub_{task['id']}")],
                [InlineKeyboardButton("⏩ Следующее задание", callback_data="next_task")]
            ])
            
            message_text = (
                f"📋 Задание #{task['id']}\n\n"
                f"Тип: Подписка на канал\n"
                f"💎 Награда: {task['reward']} ₽\n\n"
                f"📝 Описание:\n{task['description']}\n\n"
                f"✅ Для выполнения задания:\n"
                f"1. Перейдите по ссылке\n"
                f"2. Подпишитесь на канал\n"
                f"3. Нажмите кнопку проверки"
            )
            
        elif task['type'] == 'register':
            reg_link = task['extra_data'].get('reg_link', '')
            if not reg_link.startswith(('http://', 'https://')):
                reg_link = f"https://{reg_link}"
                
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("👉 Перейти к регистрации", url=reg_link)],
                [InlineKeyboardButton("📸 Отправить скриншот", callback_data=f"send_screenshot_{task['id']}")]
            ])
            
            message_text = (
                f"📋 Задание #{task['id']}\n\n"
                f"Тип: Регистрация на сайте\n"
                f"💎 Награда: {task['reward']} ₽\n\n"
                f"📝 Описание:\n{task['description']}\n\n"
                f"✅ Для выполнения задания:\n"
                f"1. Перейдите по ссылке\n"
                f"2. Зарегистрируйтесь на сайте\n"
                f"3. Отправьте скриншот"
            )

        await update.message.reply_text(
            text=message_text,
            reply_markup=keyboard
        )

    except Exception as e:
        logger.error(f"Ошибка в show_tasks: {e}", exc_info=True)
        await update.message.reply_text("Произошла ошибка при загрузке заданий")

# Обработчик кнопки "Поддержка"
async def support(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"Служба поддержки: {config['support_link']}")

# Админ-панель
async def show_admin_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        if update.callback_query:
            message = update.callback_query.message
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("Добавить задание", callback_data="add_task")],
                [InlineKeyboardButton("Список заданий", callback_data="list_tasks")],
                [InlineKeyboardButton("📝 Редактировать задания", callback_data="edit_tasks")],
                [InlineKeyboardButton("Сделать рассылку", callback_data="broadcast")],
                [InlineKeyboardButton("👤 Режим пользователя", callback_data="user_mode")]
            ])
            
            await message.edit_text(
                "Админ-панель\nВыберите действие:",
                reply_markup=keyboard
            )
        else:
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("Добавить задание", callback_data="add_task")],
                [InlineKeyboardButton("Список заданий", callback_data="list_tasks")],
                [InlineKeyboardButton("Сделать рассылку", callback_data="broadcast")],
                [InlineKeyboardButton("👤 Режим пользователя", callback_data="user_mode")]
            ])
            
            await update.message.reply_text(
                "Админ-панель\nВыберите действие:",
                reply_markup=keyboard
            )
        
        context.user_data['state'] = States.ADMIN
        
    except Exception as e:
        logger.error(f"Ошибка в show_admin_menu: {e}", exc_info=True)

# Обработчик добавления задания
async def add_task_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        query = update.callback_query
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("Подписка на канал", callback_data="new_task_subscribe")],
            [InlineKeyboardButton("Регистрация на сайте", callback_data="new_task_register")],
            [InlineKeyboardButton("◀️ Назад", callback_data="back_to_admin")]
        ])
        
        await query.message.edit_text(
            "Выберите тип задания:",
            reply_markup=keyboard
        )
        await query.answer()
        
    except Exception as e:
        logger.error(f"Ошибка в add_task_start: {e}", exc_info=True)

# Обработчик скриншотов
async def handle_admin_task_response(update: Update, context: ContextTypes.DEFAULT_TYPE, approve: bool):
    try:
        query = update.callback_query
        data = query.data.split('_')
        user_id = int(data[1])
        task_id = int(data[2])
        
        if approve:
            reward = await db.get_task_reward(task_id)
            await db.update_balance(user_id, reward)
            
            # Обновляем клавиатуру с новым балансом
            new_keyboard = await get_main_keyboard_with_balance(user_id)
            await context.bot.send_message(
                user_id, 
                "✅ Ваше задание одобрено! Баланс обновлен", 
                reply_markup=new_keyboard
            )
        else:
            await context.bot.send_message(user_id, "❌ Ваше задание отклонено")
            
        await query.answer()
        await query.message.delete()
        
    except Exception as e:
        logger.error(f"Ошибка в handle_admin_task_response: {e}", exc_info=True)

async def check_subscription(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        query = update.callback_query
        task_id = int(query.data.split('_')[2])
        user_id = query.from_user.id
        
        # Получаем задание
        task = await db.get_task_by_id(task_id)
        if not task:
            await query.answer("Задание не найдено!", show_alert=True)
            return
            
        # Получаем юзернейм канала из ссылки
        channel_link = task['extra_data'].get('channel_link', '')
        channel_username = channel_link.split('/')[-1].replace('@', '')
        
        # Проверяем подписку через второго бота
        is_subscribed = await subscription_checker.check_subscription(channel_username, user_id)
        
        if (is_subscribed):
            # Начисляем награду
            reward = task['reward']
            await db.update_balance(user_id, reward)
            
            # Отмечаем задание как выполненное
            await db.mark_task_completed(user_id, task_id)
            
            # Обновляем клавиатуру с новым балансом
            new_keyboard = await get_main_keyboard_with_balance(user_id)
            
            await query.message.edit_text(
                "✅ Подписка подтверждена!\n"
                f"💎 Получено: {reward} ₽\n"
                "Нажмите 'Мои задания' для следующего задания"
            )
            
            # Отправляем новое сообщение с обновленной клавиатурой
            await context.bot.send_message(
                user_id,
                "💰 Баланс обновлен!",
                reply_markup=new_keyboard
            )
        else:
            await query.answer("❌ Вы не подписаны на канал!", show_alert=True)
            
    except Exception as e:
        logger.error(f"Ошибка в check_subscription: {e}", exc_info=True)
        await query.answer("Произошла ошибка при проверке подписки", show_alert=True)

async def handle_screenshot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        user_id = update.effective_user.id
        if context.user_data.get('state') != States.WAITING_SCREENSHOT:
            return

        # Создаем директорию если её нет
        os.makedirs("screenshots", exist_ok=True)

        # Сохраняем скриншот
        photo = update.message.photo[-1]
        file = await context.bot.get_file(photo.file_id)
        task_id = context.user_data.get('current_task_id')
        file_path = f"screenshots/{user_id}_{task_id}.jpg"
        
        # Используем download_to_drive вместо download
        await file.download_to_drive(file_path)
        
        # Сохраняем в базу
        await db.save_screenshot(user_id, task_id, file_path)

        # Отправляем на проверку админам
        for admin_id in config['admin_ids']:
            keyboard = InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("✅ Принять", callback_data=f"approve_{user_id}_{task_id}"),
                    InlineKeyboardButton("❌ Отклонить", callback_data=f"reject_{user_id}_{task_id}")
                ]
            ])
            
            with open(file_path, 'rb') as photo:
                await context.bot.send_photo(
                    chat_id=admin_id,
                    photo=photo,
                    caption=f"📝 Новый скриншот\nПользователь: {user_id}\nЗадание #{task_id}\nНаграда: {context.user_data['current_task_reward']} ₽",
                    reply_markup=keyboard
                )

        await update.message.reply_text("✅ Скриншот отправлен на проверку! Ожидайте подтверждения.")
        context.user_data['state'] = States.NORMAL

    except Exception as e:
        logger.error(f"Ошибка в handle_screenshot: {e}", exc_info=True)
        await update.message.reply_text("❌ Произошла ошибка при обработке скриншота")

# Змінюємо функцію start_broadcast
async def start_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        query = update.callback_query
        await query.answer()
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("❌ Отменить", callback_data="cancel_broadcast")],
            [InlineKeyboardButton("◀️ Назад", callback_data="back_to_admin")]
        ])
        
        await query.message.edit_text(
            "📢 Режим рассылки\n\n"
            "Отправьте сообщение для рассылки:\n"
            "• Можно отправить текст\n"
            "• Можно отправить фото с подписью\n"
            "• Можно отправить видео с подписью\n\n"
            "❗️ Сообщение будет отправлено всем пользователям бота",
            reply_markup=keyboard
        )
        
        context.user_data['state'] = 'waiting_broadcast'
        
    except Exception as e:
        logger.error(f"Ошибка в start_broadcast: {e}", exc_info=True)

# Змінюємо функцію handle_broadcast_message
async def handle_broadcast_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        if context.user_data.get('state') != 'waiting_broadcast':
            return

        message = update.message
        users = await db.get_all_users()
        
        # Статистика розсилки
        total_users = len(users)
        success = 0
        failed = 0
        failed_users = []  # Список користувачів, яким не вдалося відправити
        
        # Прогрес розсилки
        progress_msg = await message.reply_text(
            "📤 Начинаем рассылку...\n"
            f"Всего пользователей: {total_users}\n"
            "Успешно отправлено: 0\n"
            "Ошибок доставки: 0"
        )

        for i, user_id in enumerate(users, 1):
            try:
                if message.photo:
                    # Відправка фото з підписом
                    await context.bot.send_photo(
                        chat_id=user_id,
                        photo=message.photo[-1].file_id,
                        caption=message.caption,
                        parse_mode='HTML'
                    )
                elif message.video:
                    # Відправка відео з підписом
                    await context.bot.send_video(
                        chat_id=user_id,
                        video=message.video.file_id,
                        caption=message.caption,
                        parse_mode='HTML'
                    )
                else:
                    # Відправка текстового повідомлення
                    await context.bot.send_message(
                        chat_id=user_id,
                        text=message.text,
                        parse_mode='HTML'
                    )
                success += 1
                
                # Оновлюємо прогрес кожні 10 повідомлень
                if i % 10 == 0:
                    await progress_msg.edit_text(
                        "📤 Рассылка в процессе...\n"
                        f"Всего пользователей: {total_users}\n"
                        f"Успешно отправлено: {success}\n"
                        f"Ошибок доставки: {failed}"
                    )
                
                # Додаємо затримку щоб уникнути обмежень API
                await asyncio.sleep(0.05)
                
            except Exception as e:
                failed += 1
                failed_users.append(user_id)
                logger.error(f"Ошибка отправки пользователю {user_id}: {e}")

        # Фінальний звіт
        success_rate = (success / total_users) * 100 if total_users > 0 else 0
        
        # Формуємо текст результату
        result_text = (
            "✅ Рассылка завершена!\n\n"
            f"📊 Статистика:\n"
            f"• Всего пользователей: {total_users}\n"
            f"• Успешно доставлено: {success}\n"
            f"• Ошибок доставки: {failed}\n"
            f"• Процент успеха: {success_rate:.1f}%\n\n"
        )

        # Додаємо різні емодзі в залежності від успішності
        if success_rate == 100:
            result_text = "🚀 " + result_text + "Рассылка выполнена идеально!"
        elif success_rate >= 90:
            result_text = "✨ " + result_text + "Рассылка выполнена очень успешно!"
        elif success_rate >= 75:
            result_text = "👍 " + result_text + "Рассылка выполнена хорошо."
        elif success_rate >= 50:
            result_text = "⚠️ " + result_text + "Рассылка выполнена удовлетворительно."
        else:
            result_text = "❌ " + result_text + "Возникли проблемы с рассылкой."

        # Якщо є невдалі відправки, додаємо інформацію про них
        if failed_users:
            result_text += "\n⚠️ ID пользователей с ошибками:\n"
            result_text += ", ".join(map(str, failed_users[:10]))
            if len(failed_users) > 10:
                result_text += f"\nи еще {len(failed_users) - 10} пользователей..."

        # Оновлюємо прогрес-повідомлення з фінальним звітом
        await progress_msg.edit_text(result_text)

        # Повертаємось в адмін-меню
        context.user_data['state'] = States.ADMIN
        await show_admin_menu(update, context)
        
    except Exception as e:
        logger.error(f"Ошибка в handle_broadcast_message: {e}", exc_info=True)
        await update.message.reply_text(
            "❌ Произошла ошибка при рассылке сообщений.\n"
            "Пожалуйста, попробуйте позже или обратитесь к разработчику."
        )

# Додаємо обробник для кнопки скасування розсилки
async def cancel_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        query = update.callback_query
        await query.answer()
        
        context.user_data['state'] = States.ADMIN
        await show_admin_menu(update, context)
        
    except Exception as e:
        logger.error(f"Ошибка в cancel_broadcast: {e}", exc_info=True)

# Дополнительные админ-функции
async def handle_new_task_type(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        query = update.callback_query
        task_type = query.data.split('_')[2]
        
        context.user_data['new_task_type'] = task_type
        context.user_data['state'] = States.WAITING_TASK_DESCRIPTION
        
        await query.message.edit_text("Введите описание задания:")
        await query.answer()
        
    except Exception as e:
        logger.error(f"Ошибка в handle_new_task_type: {e}", exc_info=True)

async def handle_task_description(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get('state') != States.WAITING_TASK_DESCRIPTION:
        return
        
    context.user_data['new_task_description'] = update.message.text
    context.user_data['state'] = States.WAITING_TASK_REWARD
    
    await update.message.reply_text("Введите награду за задание (в рублях):")

async def handle_task_reward(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get('state') != States.WAITING_TASK_REWARD:
        return
        
    try:
        reward = float(update.message.text)
        context.user_data['new_task_reward'] = reward
        
        if context.user_data['new_task_type'] == 'subscribe':
            context.user_data['state'] = States.WAITING_CHANNEL_LINK
            await update.message.reply_text("Введите ссылку на канал:")
        else:
            context.user_data['state'] = States.WAITING_CHANNEL_LINK
            await update.message.reply_text("Введите ссылку для регистрации:")
            
    except ValueError:
        await update.message.reply_text("Пожалуйста, введите числовое значение")

async def list_tasks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        query = update.callback_query
        tasks = await db.get_all_tasks()  # Добавим эту функцию в database.py
        
        if not tasks:
            await query.message.edit_text("Список заданий пуст")
            return
            
        text = "📝 Список заданий:\n\n"
        for task in tasks:
            text += f"#{task['id']} - {task['description']}\n"
            text += f"Тип: {task['type']}\n"
            text += f"Награда: {task['reward']} ₽\n\n"
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("◀️ Назад", callback_data="back_to_admin")]
        ])
        
        await query.message.edit_text(text, reply_markup=keyboard)
        
    except Exception as e:
        logger.error(f"Ошибка в list_tasks: {e}", exc_info=True)

async def handle_channel_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get('state') != States.WAITING_CHANNEL_LINK:
        return
        
    try:
        link = update.message.text
        task_type = context.user_data['new_task_type']
        
        # Форматируем ссылку если это канал
        if task_type == 'subscribe':
            link = format_channel_link(link)
                
        task_data = {
            'type': task_type,
            'description': context.user_data['new_task_description'],
            'reward': float(context.user_data['new_task_reward']),
            'extra_data': {
                'channel_link' if task_type == 'subscribe' else 'reg_link': link
            }
        }
        
        logger.info(f"Создание задания с данными: {task_data}")
        task_id = await db.add_task(**task_data)
        
        await update.message.reply_text(
            f"✅ Задание успешно создано!\n"
            f"ID: {task_id}\n"
            f"Тип: {task_data['type']}\n"
            f"Награда: {task_data['reward']} ₽"
        )
        
        context.user_data['state'] = States.ADMIN
        await show_admin_menu(update, context)
        
    except Exception as e:
        logger.error(f"Ошибка в handle_channel_link: {e}", exc_info=True)
        await update.message.reply_text("Произошла ошибка при создании задания")

# Добавьте новую функцию:
async def next_task(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        query = update.callback_query
        tasks = context.user_data.get('available_tasks', [])
        current_index = context.user_data.get('task_index', 0)
        
        # Если это последнее задание, начинаем сначала
        next_index = (current_index + 1) % len(tasks)
        task = tasks[next_index]
        
        # Обновляем индекс
        context.user_data['task_index'] = next_index
        
        # Формируем сообщение и клавиатуру как в show_tasks
        if task['type'] == 'subscribe':
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("👉 Перейти в канал", url=task['extra_data']['channel_link'])],
                [InlineKeyboardButton("✅ Проверить подписку", callback_data=f"check_sub_{task['id']}")],
                [InlineKeyboardButton("⏩ Следующее задание", callback_data="next_task")]
            ])
            
            message_text = (
                f"📋 Задание #{task['id']}\n\n"
                f"Тип: Подписка на канал\n"
                f"💎 Награда: {task['reward']} ₽\n\n"
                f"📝 Описание:\n{task['description']}\n\n"
                f"✅ Для выполнения задания:\n"
                f"1. Перейдите по ссылке\n"
                f"2. Подпишитесь на канал\n"
                f"3. Нажмите кнопку проверки"
            )
        else:
            # Аналогично для register
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("👉 Перейти к регистрации", url=task['extra_data']['reg_link'])],
                [InlineKeyboardButton("📸 Отправить скриншот", callback_data=f"send_screenshot_{task['id']}")],
                [InlineKeyboardButton("⏩ Следующее задание", callback_data="next_task")]
            ])
            
            message_text = (
                f"📋 Задание #{task['id']}\n\n"
                f"Тип: Регистрация на сайте\n"
                f"💎 Награда: {task['reward']} ₽\n\n"
                f"📝 Описание:\н{task['description']}\n\n"
                f"✅ Для выполнения задания:\н"
                f"1. Перейдите по ссылке\n"
                f"2. Зарегистрируйтесь на сайте\n"
                f"3. Отправьте скриншот"
            )
        
        # Обновляем сообщение
        await query.message.edit_text(
            text=message_text,
            reply_markup=keyboard
        )
        await query.answer()
        
    except Exception as e:
        logger.error(f"Ошибка в next_task: {e}", exc_info=True)

def format_channel_link(link: str) -> str:
    """Форматирует ссылку на канал в правильный формат"""
    if not link:
        return ''
    
    # Убираем пробелы
    link = link.strip()
    
    # Если это уже полная ссылка
    if link.startswith(('https://', 'http://')):
        return link
        
    # Если это юзернейм с @ или без
    username = link.lstrip('@')
    return f"https://t.me/{username}"

# Добавьте эту функцию перед функцией run_bot()
async def handle_send_screenshot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        query = update.callback_query
        await query.answer()
        
        # Получаем id задания из callback_data
        task_id = int(query.data.split('_')[2])
        
        # Сохраняем id задания в контексте
        context.user_data['current_task_id'] = task_id
        
        # Получаем информацию о задании
        task = await db.get_task_by_id(task_id)
        if task:
            context.user_data['current_task_reward'] = task['reward']
        
        # Переводим пользователя в состояние ожидания скриншота
        context.user_data['state'] = States.WAITING_SCREENSHOT
        await query.message.edit_text(
            "📸 Пожалуйста, отправьте скриншот выполненного задания.\n\n"
            "❗️ Убедитесь, что на скриншоте видно:\н"
            "- Дату и время\n"
            "- Подтверждение выполнения задания"
        )
        
    except Exception as e:
        logger.error(f"Ошибка в handle_send_screenshot: {e}", exc_info=True)
        await query.answer("Произошла ошибка при обработке запроса", show_alert=True)

# Замените функцию main() на:

def run_bot():
    # Создаем приложение
    application = Application.builder().token(os.getenv('BOT_TOKEN')).build()
    
    # Базовые команды
    application.add_handler(CommandHandler('start', start))
    
    # Callback handlers
    application.add_handler(CallbackQueryHandler(button_click, pattern='^understand$'))
    application.add_handler(CallbackQueryHandler(add_task_start, pattern="^add_task$"))
    application.add_handler(CallbackQueryHandler(handle_new_task_type, pattern="^new_task_"))  # Убедитесь, что эта строка есть
    application.add_handler(CallbackQueryHandler(list_tasks, pattern="^list_tasks$"))
    application.add_handler(CallbackQueryHandler(show_admin_menu, pattern="^back_to_admin$"))
    application.add_handler(CallbackQueryHandler(start_broadcast, pattern="^broadcast$"))
    application.add_handler(CallbackQueryHandler(switch_to_user_mode, pattern="^user_mode$"))
    application.add_handler(CallbackQueryHandler(
        lambda u, c: handle_admin_task_response(u, c, True), 
        pattern="^approve_"
    ))
    application.add_handler(CallbackQueryHandler(
        lambda u, c: handle_admin_task_response(u, c, False), 
        pattern="^reject_"
    ))
    application.add_handler(CallbackQueryHandler(check_subscription, pattern="^check_sub_"))
    application.add_handler(CallbackQueryHandler(next_task, pattern="^next_task$"))
    application.add_handler(CallbackQueryHandler(handle_send_screenshot, pattern="^send_screenshot_"))
    application.add_handler(CallbackQueryHandler(cancel_broadcast, pattern="^cancel_broadcast$"))
    
    # Обработчики текстовых сообщений с высоким приоритетом
    application.add_handler(MessageHandler(
        filters.Text(["👑 Админ-панель"]) & filters.User(config['admin_ids']),
        admin_button_handler
    ))

    # Остальные обработчики текстовых сообщений
    application.add_handler(MessageHandler(
        filters.Text(["✅ Мои задания ✅"]), 
        show_tasks
    ))
    application.add_handler(MessageHandler(
        filters.Text(["Поддержка"]), 
        support
    ))
    application.add_handler(MessageHandler(filters.PHOTO, handle_screenshot))
    
    # Обработчики состояний админа
    application.add_handler(MessageHandler(
        filters.TEXT & filters.User(config['admin_ids']),
        handle_admin_input
    ))
    
    # Додаємо обробник для скасування розсилки
    application.add_handler(CallbackQueryHandler(
        cancel_broadcast, 
        pattern="^cancel_broadcast$"
    ))
    
    # Додаємо обробники для редагування завдань
    application.add_handler(CallbackQueryHandler(edit_task_menu, pattern="^edit_tasks$"))
    application.add_handler(CallbackQueryHandler(show_task_edit_options, pattern="^edit_task_"))
    application.add_handler(CallbackQueryHandler(handle_delete_task, pattern="^delete_task_"))
    application.add_handler(CallbackQueryHandler(confirm_delete_task, pattern="^confirm_delete_"))
    
    # Додаємо обробники станів редагування
    application.add_handler(CallbackQueryHandler(
        lambda u, c: set_edit_state(u, c, 'edit_description'), 
        pattern="^edit_desc_"
    ))
    application.add_handler(CallbackQueryHandler(
        lambda u, c: set_edit_state(u, c, 'edit_reward'), 
        pattern="^edit_reward_"
    ))
    application.add_handler(CallbackQueryHandler(
        lambda u, c: set_edit_state(u, c, 'edit_link'), 
        pattern="^edit_link_"
    ))
    application.add_handler(CallbackQueryHandler(
        lambda u, c: set_edit_state(u, c, 'edit_position'), 
        pattern="^edit_position_"
    ))
    
    # Додаємо обробник введення для редагування
    application.add_handler(MessageHandler(
        filters.TEXT & filters.User(config['admin_ids']) & 
        filters.StateFilter('edit_description', 'edit_reward', 'edit_link', 'edit_position'),
        handle_edit_input
    ))
    
    # Заменяем проблемный обработчик
    application.add_handler(MessageHandler(
        filters.TEXT 
        & filters.User(config['admin_ids']) 
        & (
            filters.create(
                lambda _, ctx: ctx.user_data.get('edit_state') in [
                    'edit_description', 
                    'edit_reward', 
                    'edit_link', 
                    'edit_position'
                ]
            )
        ),
        handle_edit_input
    ))

    # Удаляем дублирующий обработчик
    # application.add_handler(MessageHandler(
    #     filters.TEXT 
    #     & filters.User(config['admin_ids']) 
    #     & filters.StateFilter(...),
    #     handle_edit_input
    # ))
    
    # Запускаем бота
    logger.info("Бот запущен")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

# Добавьте новую функцию для обработки админ-ввода:
async def handle_admin_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        # Добавим логирование для отладки
        state = context.user_data.get('state')
        text = update.message.text
        
        if state == States.WAITING_TASK_DESCRIPTION:
            context.user_data['new_task_description'] = text
            context.user_data['state'] = States.WAITING_TASK_REWARD
            await update.message.reply_text("Введите награду за задание (в рублях):")
            logger.info("Запрошена награда за задание")
            
        elif state == States.WAITING_TASK_REWARD:
            try:
                reward = float(text)
                context.user_data['new_task_reward'] = reward
                context.user_data['state'] = States.WAITING_CHANNEL_LINK
                
                if context.user_data.get('new_task_type') == 'subscribe':
                    await update.message.reply_text("Введите ссылку на канал:")
                else:
                    await update.message.reply_text("Введите ссылку для регистрации:")
                logger.info("Запрошена ссылка")
                    
            except ValueError:
                await update.message.reply_text("Пожалуйста, введите числовое значение")
                
        elif state == States.WAITING_CHANNEL_LINK:
            link = text
            task_type = context.user_data.get('new_task_type', '')
            
            task_data = {
                'type': task_type,
                'description': context.user_data.get('new_task_description', ''),
                'reward': float(context.user_data.get('new_task_reward', 0)),
                'extra_data': {
                    'channel_link' if task_type == 'subscribe' else 'reg_link': link
                }
            }
            
            logger.info(f"Создание задания с данными: {task_data}")
            task_id = await db.add_task(**task_data)
            
            await update.message.reply_text(
                f"✅ Задание успешно создано!\н"
                f"ID: {task_id}\n"
                f"Тип: {task_data['type']}\n"
                f"Награда: {task_data['reward']} ₽"
            )
            
            context.user_data['state'] = States.ADMIN
            await show_admin_menu(update, context)
            
    except Exception as e:
        logger.error(f"Ошибка в handle_admin_input: {e}", exc_info=True)
        await update.message.reply_text("Произошла ошибка при обработке ввода")

# Добавьте новую функцию:

async def switch_to_user_mode(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        query = update.callback_query
        await query.answer()
        
        # Получаем баланс пользователя
        balance = await db.get_balance(query.from_user.id) or 0
        
        # Создаем клавиатуру пользователя с кнопкой возврата
        keyboard = ReplyKeyboardMarkup([
            ["✅ Мои задания ✅"],
            [f"Баланс: {balance} ₽", "Поддержка"],
            ["👑 Админ-панель"]  # Кнопка возврата в админ-панель
        ], resize_keyboard=True)
        
        await query.message.delete()
        await query.message.reply_text(
            "👤 Режим пользователя активирован",
            reply_markup=keyboard
        )
        
        # Устанавливаем состояние
        context.user_data['state'] = States.NORMAL
        
    except Exception as e:
        logger.error(f"Ошибка в switch_to_user_mode: {e}", exc_info=True)

# Добавим новую функцию для обработки кнопки возврата в админ-панель
async def admin_button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        user_id = update.effective_user.id
        if user_id in config['admin_ids']:
            logger.info(f"Возврат в админ-панель пользователем {user_id}")
            # Показываем админ-меню
            await show_admin_menu(update, context)
        
    except Exception as e:
        logger.error(f"Ошибка в admin_button_handler: {e}", exc_info=True)

async def edit_task_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показує меню редагування завдань"""
    try:
        query = update.callback_query
        tasks = await db.get_all_tasks()
        
        if not tasks:
            await query.message.edit_text(
                "Нет доступных заданий для редактирования",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("◀️ Назад", callback_data="back_to_admin")
                ]])
            )
            return
            
        keyboard = []
        for task in tasks:
            keyboard.append([
                InlineKeyboardButton(
                    f"#{task['id']} - {task['description'][:30]}...", 
                    callback_data=f"edit_task_{task['id']}"
                )
            ])
            
        keyboard.append([InlineKeyboardButton("◀️ Назад", callback_data="back_to_admin")])
        
        await query.message.edit_text(
            "📝 Выберите задание для редактирования:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        
    except Exception as e:
        logger.error(f"Ошибка в edit_task_menu: {e}")

async def show_task_edit_options(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показує опції редагування для конкретного завдання"""
    try:
        query = update.callback_query
        task_id = int(query.data.split('_')[2])
        task = await db.get_task_by_id(task_id)
        
        if not task:
            await query.answer("Задание не найдено!")
            return
            
        context.user_data['editing_task_id'] = task_id
        
        keyboard = [
            [InlineKeyboardButton("📝 Изменить описание", callback_data=f"edit_desc_{task_id}")],
            [InlineKeyboardButton("💰 Изменить награду", callback_data=f"edit_reward_{task_id}")],
            [InlineKeyboardButton("🔗 Изменить ссылку", callback_data=f"edit_link_{task_id}")],
            [InlineKeyboardButton("📊 Изменить позицию", callback_data=f"edit_position_{task_id}")],
            [InlineKeyboardButton("❌ Удалить задание", callback_data=f"delete_task_{task_id}")],
            [InlineKeyboardButton("◀️ Назад", callback_data="edit_tasks")]
        ]
        
        message_text = (
            f"📋 Задание #{task['id']}\n\n"
            f"Тип: {task['type']}\n"
            f"Описание: {task['description']}\n"
            f"Награда: {task['reward']} ₽\n"
            f"Ссылка: {task['extra_data'].get('channel_link' if task['type'] == 'subscribe' else 'reg_link', '')}"
        )
        
        await query.message.edit_text(
            message_text,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        
    except Exception as e:
        logger.error(f"Ошибка в show_task_edit_options: {e}")

async def handle_edit_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обробляє введені дані для редагування"""
    try:
        user_id = update.effective_user.id
        if user_id not in config['admin_ids']:
            return
            
        state = context.user_data.get('edit_state')
        task_id = context.user_data.get('editing_task_id')
        
        if not state or not task_id:
            return
            
        task = await db.get_task_by_id(task_id)
        if not task:
            await update.message.reply_text("Задание не найдено!")
            return
            
        updates = {}
        
        if state == 'edit_description':
            updates['description'] = update.message.text
        elif state == 'edit_reward':
            try:
                reward = float(update.message.text)
                updates['reward'] = reward
            except ValueError:
                await update.message.reply_text("Пожалуйста, введите числовое значение")
                return
        elif state == 'edit_link':
            link = update.message.text
            if task['type'] == 'subscribe':
                link = format_channel_link(link)
            updates['extra_data'] = {
                'channel_link' if task['type'] == 'subscribe' else 'reg_link': link
            }
        elif state == 'edit_position':
            try:
                new_position = int(update.message.text)
                if new_position < 1:
                    await update.message.reply_text("Позиция должна быть больше 0")
                    return
                await db.reorder_task(task_id, new_position)
                await update.message.reply_text("✅ Позиция задания изменена!")
                context.user_data.pop('edit_state', None)
                await show_task_edit_options(update, context)
                return
            except ValueError:
                await update.message.reply_text("Пожалуйста, введите целое число")
                return
                
        if updates:
            success = await db.update_task(task_id, updates)
            if success:
                await update.message.reply_text("✅ Изменения сохранены!")
            else:
                await update.message.reply_text("❌ Ошибка при сохранении изменений")
                
        context.user_data.pop('edit_state', None)
        await show_task_edit_options(update, context)
        
    except Exception as e:
        logger.error(f"Ошибка в handle_edit_input: {e}")

async def handle_delete_task(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обробляє видалення завдання"""
    try:
        query = update.callback_query
        task_id = int(query.data.split('_')[2])
        
        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton("✅ Да", callback_data=f"confirm_delete_{task_id}"),
            InlineKeyboardButton("❌ Нет", callback_data=f"edit_task_{task_id}")
        ]])
        
        await query.message.edit_text(
            "❗️ Вы уверены, что хотите удалить это задание?\н"
            "Это действие нельзя отменить!",
            reply_markup=keyboard
        )
        
    except Exception as e:
        logger.error(f"Ошибка в handle_delete_task: {e}")

async def confirm_delete_task(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Підтверджує видалення завдання"""
    try:
        query = update.callback_query
        task_id = int(query.data.split('_')[2])
        
        success = await db.delete_task(task_id)
        if success:
            await query.answer("✅ Задание успешно удалено!")
            await edit_task_menu(update, context)
        else:
            await query.answer("❌ Ошибка при удалении задания", show_alert=True)
        
    except Exception as e:
        logger.error(f"Ошибка в confirm_delete_task: {e}")

async def set_edit_state(update: Update, context: ContextTypes.DEFAULT_TYPE, state: str):
    """Встановлює стан редагування та запитує нове значення"""
    try:
        query = update.callback_query
        task_id = int(query.data.split('_')[2])
        
        context.user_data['edit_state'] = state
        context.user_data['editing_task_id'] = task_id
        
        messages = {
            'edit_description': "Введите новое описание задания:",
            'edit_reward': "Введите новую награду (в рублях):",
            'edit_link': "Введите новую ссылку:",
            'edit_position': "Введите новую позицию (число):"
        }
        
        await query.message.edit_text(
            messages[state],
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("◀️ Отмена", callback_data=f"edit_task_{task_id}")]
            ])
        )
        
    except Exception as e:
        logger.error(f"Ошибка в set_edit_state: {e}")
        
if __name__ == '__main__':
    run_bot()
