import logging
import os
import time
from http import HTTPStatus

import requests
from dotenv import load_dotenv
from telebot import TeleBot

load_dotenv()


PRACTICUM_TOKEN = os.getenv('PRACTICUM_TOKEN')
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

RETRY_PERIOD = 600
ENDPOINT = 'https://practicum.yandex.ru/api/user_api/homework_statuses/'
HEADERS = {'Authorization': f'OAuth {PRACTICUM_TOKEN}'}


HOMEWORK_VERDICTS = {
    'approved': 'Работа проверена: ревьюеру всё понравилось. Ура!',
    'reviewing': 'Работа взята на проверку ревьюером.',
    'rejected': 'Работа проверена: у ревьюера есть замечания.'
}


logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')

file_handler = logging.FileHandler(
    filename='main.log',
    mode='w',
    encoding='utf-8'
)
file_handler.setFormatter(formatter)
logger.addHandler(file_handler)

terminal_handler = logging.StreamHandler()
terminal_handler.setLevel(logging.WARNING)
terminal_handler.setFormatter(formatter)
logger.addHandler(terminal_handler)


def check_tokens():
    """Функция проверяет доступность переменных окружения."""
    logger.info('Проверяет наличие токенов в окружении')
    tokens = {
        'PRACTICUM_TOKEN': PRACTICUM_TOKEN,
        'TELEGRAM_TOKEN': TELEGRAM_TOKEN,
        'TELEGRAM_CHAT_ID': TELEGRAM_CHAT_ID,
    }
    for token, value in tokens.items():
        if token in os.environ:
            if value is None:
                logger.critical(f'{token} не присвоено значение')
                raise SystemExit(f'{token} не присвоено значение')
        else:
            logger.critical(f'{token} не установлен в переменных окружения')
            raise SystemExit(f'{token} не установлен в переменных окружения')


def send_message(bot, message):
    """Функция отправляет сообщение в Telegram-чат."""
    logger.info('Вызывана функция send_message')
    try:
        bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=message)
        logger.debug(f'Сообщение {message} успешно отправлено')
    except Exception as error:
        logger.error(error, exc_info=True)


def get_api_answer(timestamp):
    """Функция делает запрос к единственному эндпоинту API-сервиса.

    В качестве параметра в функцию передаётся временная метка.
    В случае успешного запроса ответ API преобразуется из формата JSON
    к типам данных Python.
    """
    logger.info(f'get_api_answer вызвана с timestamp={timestamp}')
    try:
        response = requests.get(
            url=ENDPOINT,
            headers=HEADERS,
            params={'from_date': timestamp}
        )
        if response.status_code == HTTPStatus.NO_CONTENT:
            logger.error('Проблемы с соединением')
            raise
        else:
            response.raise_for_status()
        logger.info('Ответ от API получен. HTTP-статус 200.')
        return response.json()
    except requests.ConnectionError as error:
        logger.error(error, exc_info=True)
        raise
    except requests.HTTPError as error:
        logger.error(error, exc_info=True)
        raise
    except requests.TimeoutError as error:
        logger.error(error, exc_info=True)
        raise
    except requests.RequestException as error:
        logger.error(error, exc_info=True)
        raise
    except Exception as error:
        logger.error(error, exc_info=True)
        raise


def check_response(response):
    """Функция проверяет ответ API на соответствие ее документации."""
    if not isinstance(response, dict):
        logger.warning('response не преобразован в словарь')
        raise TypeError('Ответ API не словарь')

    if 'homeworks' in response:
        if not isinstance(response['homeworks'], list):
            logger.warning('Значение homeworks не список')
            raise TypeError('Ключ homeworks не список')
    else:
        logger.warning('Ключа homeworks нет в API ответа.')
        raise KeyError('Ключа homeworks нет в API ответа.')

    if 'current_date' in response:
        if not isinstance(response['current_date'], int):
            logger.warning('Значение current_date не целое число')
            raise TypeError('Ключ current_date не целое число')
    else:
        logger.warning('Ключа current_date нет в API ответа.')
        raise KeyError('Ключа current_date нет в API ответа.')


def parse_status(homework):
    """Функция извлекает статус последней домашней работы."""
    if 'homework_name' not in homework:
        logger.error('Домашка без имени')
        raise KeyError('Ключа homework_name нет в API ответа.')
    else:
        homework_name = homework.get('homework_name')

    if 'status' not in homework:
        logger.error('Домашка без статуса')
        raise KeyError('Ключа status нет в API ответа.')
    else:
        homework_status = homework.get('status')

    if homework_status not in HOMEWORK_VERDICTS:
        logger.error('API возвращает недокументированный статус домашки')
        raise KeyError('Ключа homework_status нет в API документации.')
    else:
        verdict = HOMEWORK_VERDICTS[homework_status]
        logger.info('Получение статуса прошло успешно. Message сформирован')
    return f'Изменился статус проверки работы "{homework_name}". {verdict}'


def main():
    """Основная логика работы бота."""
    logger.info('Бот запущен')
    check_tokens()
    # Создаем объект класса бота
    bot = TeleBot(token=TELEGRAM_TOKEN)
    timestamp = int(time.time())
    last_message = ''

    while True:
        try:
            logger.info('Делает запрос и получает информацию от API')
            response = get_api_answer(timestamp)
            check_response(response)
            if response['homeworks'] == []:
                logger.debug('Обновлений статуса нет. Список homeworks пуст.')
                message = last_message
            else:
                homework = response['homeworks'][-1]
                logger.info('Есть обновления. Получаю статус домашней работы')
                message = parse_status(homework)

            timestamp = response['current_date']
            logger.info('Проверяются сообщения о статусе домашки')
            if last_message != message:
                send_message(bot, message)
                last_message = message
            else:
                logger.info('Новых статусов нет')
        except Exception as error:
            logger.error(error, exc_info=True)
            message = f'Сбой в работе программы: {error}'
            send_message(bot, message)
            raise
        logger.info('Следующая итерация через 10 минут.')
        time.sleep(RETRY_PERIOD)


if __name__ == '__main__':
    main()
