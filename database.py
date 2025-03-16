import sqlite3
from typing import List, Dict, Optional
import json

class Database:
    def __init__(self):
        self.conn = sqlite3.connect('bot.db')
        self.create_tables()

    def create_tables(self):
        cursor = self.conn.cursor()
        
        # Создаем таблицу tasks если её нет
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            type TEXT NOT NULL,
            description TEXT NOT NULL,
            reward REAL NOT NULL,
            order_num INTEGER,
            extra_data TEXT,
            is_active BOOLEAN DEFAULT 1
        )
        ''')

        # Таблица пользователей
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            balance REAL DEFAULT 0,
            current_task INTEGER DEFAULT NULL
        )
        ''')

        # Таблица выполненных заданий
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS completed_tasks (
            user_id INTEGER,
            task_id INTEGER,
            status TEXT,
            screenshot TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (user_id),
            FOREIGN KEY (task_id) REFERENCES tasks (id)
        )
        ''')

        self.conn.commit()

    async def is_admin(self, user_id: int) -> bool:
        cursor = self.conn.cursor()
        cursor.execute('SELECT 1 FROM admins WHERE user_id = ?', (user_id,))
        return cursor.fetchone() is not None

    async def add_task(self, type: str, description: str, reward: float, extra_data: dict) -> int:
        cursor = self.conn.cursor()
        cursor.execute(
            'INSERT INTO tasks (type, description, reward, order_num, extra_data) VALUES (?, ?, ?, ?, ?)',
            (type, description, reward, self.get_max_order() + 1, json.dumps(extra_data))
        )
        self.conn.commit()
        return cursor.lastrowid

    async def get_task(self, user_id: int) -> Optional[Dict]:
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT t.* FROM tasks t
            LEFT JOIN completed_tasks ct ON t.id = ct.task_id AND ct.user_id = ?
            WHERE t.is_active = 1 AND ct.task_id IS NULL
            ORDER BY t.order_num LIMIT 1
        ''', (user_id,))
        task = cursor.fetchone()
        
        if task:
            return {
                'id': task[0],
                'type': task[1],
                'description': task[2],
                'reward': task[3],
                'extra_data': json.loads(task[5]) if task[5] else {}
            }
        return None

    def get_max_order(self) -> int:
        cursor = self.conn.cursor()
        cursor.execute('SELECT MAX(order_num) FROM tasks')
        result = cursor.fetchone()[0]
        return result if result is not None else 0

    async def save_screenshot(self, user_id: int, task_id: int, screenshot_path: str):
        cursor = self.conn.cursor()
        cursor.execute(
            'INSERT INTO completed_tasks (user_id, task_id, screenshot, status) VALUES (?, ?, ?, ?)',
            (user_id, task_id, screenshot_path, 'pending')
        )
        self.conn.commit()

    async def update_balance(self, user_id: int, amount: float):
        cursor = self.conn.cursor()
        cursor.execute('''
            INSERT OR REPLACE INTO users (user_id, balance)
            VALUES (?, COALESCE((SELECT balance + ? FROM users WHERE user_id = ?), ?))
        ''', (user_id, amount, user_id, amount))
        self.conn.commit()

    async def get_all_users(self) -> List[int]:
        cursor = self.conn.cursor()
        cursor.execute('SELECT user_id FROM users')
        return [row[0] for row in cursor.fetchall()]

    async def get_task_by_id(self, task_id: int) -> Optional[Dict]:
        cursor = self.conn.cursor()
        cursor.execute('SELECT * FROM tasks WHERE id = ?', (task_id,))
        task = cursor.fetchone()
        
        if task:
            return {
                'id': task[0],
                'type': task[1],
                'description': task[2],
                'reward': task[3],
                'extra_data': json.loads(task[5]) if task[5] else {}
            }
        return None

    async def get_task_reward(self, task_id: int) -> float:
        cursor = self.conn.cursor()
        cursor.execute('SELECT reward FROM tasks WHERE id = ?', (task_id,))
        result = cursor.fetchone()
        return result[0] if result else 0.0

    async def get_all_tasks(self) -> List[Dict]:
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT id, type, description, reward, extra_data
            FROM tasks
            WHERE is_active = 1
            ORDER BY order_num
        ''')
        tasks = cursor.fetchall()
        
        return [{
            'id': task[0],
            'type': task[1],
            'description': task[2],
            'reward': task[3],
            'extra_data': json.loads(task[4]) if task[4] else {}
        } for task in tasks]

    async def get_available_tasks(self, user_id: int) -> List[Dict]:
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT t.* FROM tasks t
            LEFT JOIN completed_tasks ct 
            ON t.id = ct.task_id AND ct.user_id = ?
            WHERE t.is_active = 1 
            AND ct.task_id IS NULL
            ORDER BY t.order_num
        ''', (user_id,))
        
        tasks = cursor.fetchall()
        return [{
            'id': task[0],
            'type': task[1],
            'description': task[2],
            'reward': task[3],
            'extra_data': json.loads(task[5]) if task[5] else {}
        } for task in tasks]

    async def debug_print_tasks(self):
        """Выводит все задания для отладки"""
        cursor = self.conn.cursor()
        cursor.execute('SELECT * FROM tasks')
        tasks = cursor.fetchall()
        print("\nВсе задания в базе:")
        for task in tasks:
            print(f"ID: {task[0]}")
            print(f"Тип: {task[1]}")
            print(f"Описание: {task[2]}")
            print(f"Награда: {task[3]}")
            print(f"Порядок: {task[4]}")
            print(f"Доп. данные: {task[5]}")
            print(f"Активно: {task[6]}")
            print("---")

    async def mark_task_completed(self, user_id: int, task_id: int):
        """Отмечает задание как выполненное"""
        cursor = self.conn.cursor()
        cursor.execute(
            'INSERT INTO completed_tasks (user_id, task_id, status) VALUES (?, ?, ?)',
            (user_id, task_id, 'completed')
        )
        self.conn.commit()

    async def get_balance(self, user_id: int) -> float:
        """Получает баланс пользователя"""
        cursor = self.conn.cursor()
        cursor.execute('SELECT balance FROM users WHERE user_id = ?', (user_id,))
        result = cursor.fetchone()
        return result[0] if result else 0.0

    async def update_task(self, task_id: int, updates: dict) -> bool:
        """Оновлює задання за вказаним ID"""
        try:
            cursor = self.conn.cursor()
            update_fields = []
            values = []
            
            if 'description' in updates:
                update_fields.append('description = ?')
                values.append(updates['description'])
                
            if 'reward' in updates:
                update_fields.append('reward = ?')
                values.append(float(updates['reward']))
                
            if 'order_num' in updates:
                update_fields.append('order_num = ?')
                values.append(updates['order_num'])
                
            if 'extra_data' in updates:
                update_fields.append('extra_data = ?')
                values.append(json.dumps(updates['extra_data']))
            
            if update_fields:
                query = f"UPDATE tasks SET {', '.join(update_fields)} WHERE id = ?"
                values.append(task_id)
                cursor.execute(query, values)
                self.conn.commit()
                return True
            return False
            
        except Exception as e:
            logger.error(f"Ошибка при обновлении задания: {e}")
            return False

    async def delete_task(self, task_id: int) -> bool:
        """Видаляє задання з бази даних"""
        try:
            cursor = self.conn.cursor()
            # Видаляємо пов'язані записи
            cursor.execute('DELETE FROM completed_tasks WHERE task_id = ?', (task_id,))
            cursor.execute('DELETE FROM tasks WHERE id = ?', (task_id,))
            self.conn.commit()
            return True
        except Exception as e:
            logger.error(f"Ошибка при удалении задания: {e}")
            return False

    async def reorder_task(self, task_id: int, new_position: int) -> bool:
        """Змінює порядок завдань"""
        try:
            cursor = self.conn.cursor()
            # Отримуємо поточний порядок
            cursor.execute('SELECT order_num FROM tasks WHERE id = ?', (task_id,))
            current_order = cursor.fetchone()[0]
            
            if new_position > current_order:
                # Зсуваємо завдання вгору
                cursor.execute('''
                    UPDATE tasks 
                    SET order_num = order_num - 1 
                    WHERE order_num > ? AND order_num <= ?
                ''', (current_order, new_position))
            else:
                # Зсуваємо завдання вниз
                cursor.execute('''
                    UPDATE tasks 
                    SET order_num = order_num + 1 
                    WHERE order_num >= ? AND order_num < ?
                ''', (new_position, current_order))
            
            # Встановлюємо нову позицію для завдання
            cursor.execute('UPDATE tasks SET order_num = ? WHERE id = ?', 
                         (new_position, task_id))
            
            self.conn.commit()
            return True
            
        except Exception as e:
            logger.error(f"Ошибка при изменении порядка задания: {e}")
            return False

    def close(self):
        self.conn.close()