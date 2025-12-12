import logging
import os
import time

import requests
from dotenv import load_dotenv
from telebot import TeleBot

from Exception import InvalidResponseCode

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
formatter = logging.Formatter(
    '%(asctime)s - %(levelname)s - %(message)s - %(funcName)s - %(lineno)d'
)

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
        if value is None:
            logger.critical(f'{token} не присвоено значение')
            raise SystemExit(f'{token} не присвоено значение')


def send_message(bot, message):
    """Функция отправляет сообщение в Telegram-чат."""
    logger.info('Вызывана функция send_message')
    try:
        bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=message)
    except Exception as error:
        logger.error(error, exc_info=True)
        return False
    logger.debug(f'Сообщение {message} успешно отправлено')
    return True


def get_api_answer(timestamp):
    """Функция делает запрос к единственному эндпоинту API-сервиса.

    В качестве параметра в функцию передаётся временная метка.
    В случае успешного запроса ответ API преобразуется из формата JSON
    к типам данных Python.
    """
    data_for_request = {
        'url': ENDPOINT,
        'headers': HEADERS,
        'params': {'from_date': timestamp}
    }
    logger.info(
        'Начали запрос к API: по адресу {url}, c headers={headers},'
        'params={params}.'.format(**data_for_request)
    )
    try:
        response = requests.get(**data_for_request)
        response.raise_for_status()
    except requests.RequestException():
        raise ConnectionError(
            'Запрос завершился ошибкой. URL: {url}, headers: {headers},'
            'params: {params}'.format(**data_for_request)
        )
    if response.status_code != 200:
        raise InvalidResponseCode(
            f'Неверный код ответа {response.status_code} {response.reason},'
            f'ответ: {response.text}'
        )
    logger.info('Ответ от API получен. HTTP-статус 200.')
    return response.json()


def check_response(response):
    """Функция проверяет ответ API на соответствие ее документации."""
    if not isinstance(response, dict):
        logger.warning('response не преобразован в словарь')
        raise TypeError('Ответ API не словарь')
    if 'homeworks' not in response:
        logger.warning('Ключа homeworks нет в API ответа.')
        raise KeyError('Ключа homeworks нет в API ответа.')
    if not isinstance(response['homeworks'], list):
        logger.warning('Значение homeworks не список')
        raise TypeError('Ключ homeworks не список')
    if not isinstance(response['current_date'], int):
        logger.warning('Значение current_date не целое число')
        raise TypeError('Ключ current_date не целое число')
    return response['homeworks']


def parse_status(homework):
    """Функция извлекает статус последней домашней работы."""
    if 'homework_name' not in homework:
        raise KeyError('Ключа homework_name нет в API ответа.')
    homework_name = homework.get('homework_name')
    if 'status' not in homework:
        raise KeyError('Ключа status нет в API ответа.')
    homework_status = homework.get('status')
    if homework_status not in HOMEWORK_VERDICTS:
        raise ValueError(
            'Неожиданный статус домашки, отсутствует в API документации.'
        )
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
            homeworks = check_response(response)
            if homeworks == []:
                logger.debug('Обновлений статуса нет. Список homeworks пуст.')
                continue
            else:
                homework = homeworks[0]
                logger.info('Есть обновления. Получаю статус домашней работы')
                message = parse_status(homework)
                logger.info('Проверяются сообщения о статусе домашки')
                if last_message != message:
                    if send_message(bot, message) is True:
                        last_message = message                  
        except Exception as error:
            logger.error(error, exc_info=True)
            message = f'Сбой в работе программы: {error}'
            send_message(bot, message)
            raise
        finally:
            timestamp = response.get('current_date')
            logger.info('Следующая итерация через 10 минут.')
            time.sleep(RETRY_PERIOD)


if __name__ == '__main__':
    main()
